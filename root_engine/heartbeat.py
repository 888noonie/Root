"""Heartbeat-once: run at most one deterministic due job per window. No daemon.

Task F of the phase-2 plan: ARCHITECTURE minimal sequential slice (durable store + collector
+ replay; heartbeat + status). `tick_once` selects at most one safe local job (screen) and
reports `collect` as due-but-gated (collect needs explicit published bounds + network auth,
so it is never auto-started). Idempotency is a per-window key: a second invocation in the same
cooldown window records no duplicate work.
"""

from .store import BudgetError, RootError
from .screen import screen

COOLDOWN_SECONDS = 300


def _ensure_heartbeat_schema(store):
    store.db.execute(
        "CREATE TABLE IF NOT EXISTS heartbeat_runs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " window_start REAL NOT NULL,"
        " task TEXT NOT NULL,"
        " ran_at REAL NOT NULL,"
        " payload TEXT NOT NULL)"
    )
    store.db.execute(
        "CREATE TABLE IF NOT EXISTS heartbeat_state ("
        " id INTEGER PRIMARY KEY CHECK(id=1),"
        " last_run REAL,"
        " last_task TEXT)"
    )


def _window(now):
    return int(now // COOLDOWN_SECONDS)


def _last_run(store):
    row = store.db.execute("SELECT last_run,last_task FROM heartbeat_state WHERE id=1").fetchone()
    return (row[0], row[1]) if row else (None, None)


def tick_once(store, *, run_screen=True):
    """Run at most one deterministic due job in the current cooldown window.

    Returns a dict describing what was due, what ran, and whether a second call in the same
    window was suppressed. Raises BudgetError if the portfolio deadline has passed. Never
    starts a daemon or background process, and never auto-fetches network.
    """
    _ensure_heartbeat_schema(store)
    now = store.now()
    store.check()  # BudgetError on expired portfolio; also enforces storage budget.
    window = _window(now)
    last_tick, last_task = _last_run(store)
    ran_this_window = (last_tick is not None and _window(last_tick) == window)

    ran = None
    already = 1 if ran_this_window else 0

    if not ran_this_window and run_screen:
        # Deterministic offline job: re-screen stored opportunities (no network).
        opportunities = store.opportunities()
        if opportunities:
            rows = [screen(store, o) for o in opportunities]
            ran = "screen"
            store.db.execute("INSERT INTO heartbeat_runs(window_start,task,ran_at,payload) VALUES(?,?,?,?)",
                             (window * COOLDOWN_SECONDS, ran, now, __import__("json").dumps({"count": len(rows)})))
        else:
            ran = None  # nothing due; still a valid idle tick once per window

    # collect is reported as due-but-gated: it needs explicit published bounds + network auth.
    collect_due = not ran_this_window and ran is None

    if not ran_this_window:
        store.db.execute(
            "INSERT INTO heartbeat_state(id,last_run,last_task) VALUES(1,?,?)"
            " ON CONFLICT(id) DO UPDATE SET last_run=excluded.last_run, last_task=excluded.last_task",
            (now, ran))

    return {
        "tick": True,
        "window": window,
        "ran": ran,
        "already_run_in_window": already,
        "collect_due_gated": collect_due,
        "note": "at most one job per window; no daemon, no auto network",
    }


def run_collect_explicit(store, published_from, published_to, *, opener=None):
    """Explicitly gated collect: only invoked when the operator supplies live bounds.

    This is the *only* path that touches the network for heartbeats, and `tick_once` never
    calls it. Mirrors the shared collector budgets/allowlist.
    """
    from .collector import Collector, search_url, validate_package

    url = search_url(published_from, published_to, 20)
    collector = Collector(store, opener=opener)
    package = collector.fetch(url)
    validate_package(package)
    _ensure_heartbeat_schema(store)
    now = store.now()
    store.db.execute("INSERT INTO heartbeat_runs(window_start,task,ran_at,payload) VALUES(?,?,?,?)",
                     (_window(now) * COOLDOWN_SECONDS, "collect", now, __import__("json").dumps({"releases": len(package.get("releases", []))})))
    store.db.execute("INSERT INTO heartbeat_state(id,last_run,last_task) VALUES(1,?,?)"
                     " ON CONFLICT(id) DO UPDATE SET last_run=excluded.last_run, last_task=excluded.last_task",
                     (now, "collect"))
    return {"tick": True, "ran": "collect", "releases": len(package.get("releases", []))}