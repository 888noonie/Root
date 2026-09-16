"""Optional Hermes notification for pending promotions.

Task 6 contract: promote-notify sends via the existing `hermes send` CLI after
the pending promotion row already exists. It is non-authoritative: a send
failure never promotes, denies, or retries automatically.
"""

import json
import subprocess
from pathlib import Path

from .constitution import trusted_manifest
from .store import RootError, encode


def notify_message(store, promotion_id):
    row = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
    if not row:
        raise RootError("Unknown promotion")
    manifest = trusted_manifest()  # recompute at send time to detect drift
    stored = json.loads(row["trusted_manifest"])
    if manifest != stored:
        raise RootError("Trusted code changed since promotion was opened; notification suppressed")
    return {
        "promotion_id": promotion_id,
        "target": row["target"],
        "artifact_sha256": row["artifact_sha256"],
        "source_url": row["source_url"],
        "upstream_revision": row["upstream_revision"],
        "baseline_component_id": row["baseline_component_id"],
        "expires": row["expires"],
        "evaluation_receipt": json.loads(row["evaluation_receipt"]),
    }


def send_hermes_notification(store, promotion_id, target, *, actor, hermes_bin=None, timeout=15):
    if not isinstance(target, str) or not target.strip() or len(target) > 256:
        raise RootError("--to is required")
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 128:
        raise RootError("actor must be a non-empty label of at most 128 characters")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise RootError("timeout must be positive")
    if not isinstance(hermes_bin, str) or not hermes_bin:
        raise RootError("--hermes-bin must name an absolute executable path")

    row = store.db.execute("SELECT state, mode FROM promotions WHERE id=?", (promotion_id,)).fetchone()
    if not row or row["state"] != "pending" or row["mode"] != "live":
        raise RootError("Notification requires a pending live promotion")

    message = notify_message(store, promotion_id)
    bounds = encode(message)
    if len(bounds.encode("utf-8")) > 16 * 1024:
        raise RootError("Notification message exceeds bounded size")

    supplied = Path(hermes_bin)
    if not supplied.is_absolute() or not supplied.is_file() or supplied.is_symlink() or not supplied.stat().st_mode & 0o111:
        raise RootError(f"Hermes CLI must be an executable regular file at an absolute path: {hermes_bin}")
    exe = str(supplied)

    event_payload = {
        "stage": "notify_attempt",
        "actor": actor,
        "target": target,
        "message_bytes": len(bounds.encode("utf-8")),
    }
    with store.transaction():
        _check_event_storage(store, event_payload)
        store.db.execute(
            "INSERT INTO promotion_events(promotion_id, created, stage, payload) VALUES(?,?,?,?)",
            (promotion_id, store.now(), "notify_attempt", encode(event_payload)),
        )

    argv = [exe, "send", "--to", target, "--json", bounds]
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        _record_result(store, promotion_id, target, "uncertain", "timeout")
        raise RootError("Hermes send timed out after %s seconds" % timeout)
    except OSError as exc:
        _record_result(store, promotion_id, target, "failed", type(exc).__name__)
        raise RootError(f"Hermes send failed: {exc}")

    tail = (result.stderr or "")[-200:]
    if result.returncode != 0:
        _record_result(store, promotion_id, target, "failed", tail)
        raise RootError(f"Hermes send failed (exit {result.returncode}); notification not delivered")
    try:
        receipt = json.loads(result.stdout)
    except json.JSONDecodeError:
        _record_result(store, promotion_id, target, "uncertain", "malformed JSON receipt")
        raise RootError("Hermes send returned malformed JSON; delivery is uncertain")
    if not isinstance(receipt, dict):
        _record_result(store, promotion_id, target, "uncertain", "non-object JSON receipt")
        raise RootError("Hermes send returned invalid JSON receipt; delivery is uncertain")
    if receipt.get("success") is True:
        _record_result(store, promotion_id, target, "sent", "")
    elif receipt.get("skipped") is True:
        _record_result(store, promotion_id, target, "skipped", "")
        return {"status": "skipped", "promotion_id": promotion_id, "target": target, "attempt": "recorded"}
    else:
        _record_result(store, promotion_id, target, "uncertain", "negative JSON receipt")
        raise RootError("Hermes send did not confirm delivery; delivery is uncertain")
    # Attempt honesty: success does not change promotion state; delivery may be duplicated on retry.
    return {"status": "sent", "promotion_id": promotion_id, "target": target, "attempt": "recorded"}


def _record_result(store, promotion_id, target, status, detail):
    """Record delivery outcome only; it must not mutate promotion authority."""
    with store.transaction():
        payload = {"status": status, "detail": detail[-200:], "target": target}
        _check_event_storage(store, payload)
        store.db.execute(
            "INSERT INTO promotion_events(promotion_id, created, stage, payload) VALUES(?,?,?,?)",
            (promotion_id, store.now(), "notify_result", encode(payload)),
        )


def _check_event_storage(store, payload):
    """Reserve bounded audit storage without treating notification as new work.

    A notification is permitted for an already-created pending row even if the
    portfolio deadline elapsed; its state remains subject to promotion expiry.
    """
    pages = store.db.execute("PRAGMA page_count").fetchone()[0]
    page_size = store.db.execute("PRAGMA page_size").fetchone()[0]
    limit = store.portfolio()["policy"]["max_storage_bytes"]
    if pages * page_size + len(encode(payload).encode("utf-8")) + 1024 > limit:
        raise RootError("SQLite storage budget reached for notification audit event")
