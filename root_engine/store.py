"""Durable records and immutable, locally configured resource limits."""

import hashlib
import json
import math
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class RootError(Exception):
    pass


class BudgetError(RootError):
    pass


DEFAULT_POLICY = {
    "max_money_gbp": 0,
    "max_requests": 3,
    "max_download_bytes": 2 * 1024 * 1024,
    "max_storage_bytes": 16 * 1024 * 1024,
    "max_inference_tokens": 0,
    "max_elapsed_seconds": 3600,
    "max_concurrent_jobs": 1,
}


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def validate_policy(policy):
    if set(policy) != set(DEFAULT_POLICY):
        raise RootError("Policy must specify exactly: " + ", ".join(DEFAULT_POLICY))
    for key, value in policy.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise RootError(f"Invalid non-negative budget: {key}")
        if key != "max_money_gbp" and (not isinstance(value, int)):
            raise RootError(f"Budget must be an integer: {key}")
    if policy["max_money_gbp"] != 0:
        raise RootError("This implementation supports zero spending only; local inference needs explicit token allowance")
    if policy["max_concurrent_jobs"] != 1:
        raise RootError("This tranche supports exactly one collector job")
    if policy["max_elapsed_seconds"] <= 0 or policy["max_storage_bytes"] < 65536:
        raise RootError("Positive elapsed budget and at least 64 KiB storage required")


SCHEMA = """
CREATE TABLE portfolio (id INTEGER PRIMARY KEY CHECK(id=1), objective TEXT NOT NULL,
    policy TEXT NOT NULL, created REAL NOT NULL, deadline REAL NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0, downloaded_bytes INTEGER NOT NULL DEFAULT 0);
CREATE TABLE opportunities (id TEXT PRIMARY KEY, revision TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE packages (id TEXT PRIMARY KEY, source_url TEXT NOT NULL, mode TEXT NOT NULL,
    retrieved REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE observations (id TEXT PRIMARY KEY, package_id TEXT NOT NULL REFERENCES packages(id),
    ocid TEXT NOT NULL, release_id TEXT NOT NULL, source_date TEXT, payload TEXT NOT NULL);
CREATE TABLE screens (id INTEGER PRIMARY KEY, opportunity_id TEXT NOT NULL,
    revision TEXT NOT NULL, created REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE source_state (source TEXT PRIMARY KEY, not_before REAL NOT NULL DEFAULT 0);
CREATE TABLE checkpoints (query TEXT PRIMARY KEY, next_url TEXT);
CREATE TABLE lease (id INTEGER PRIMARY KEY CHECK(id=1), expires REAL NOT NULL, token TEXT NOT NULL);
PRAGMA user_version = 1;
"""


class Store:
    def __init__(self, path, *, create=False, objective=None, policy=None, now=time.time):
        self.path = Path(path)
        self.now = now
        if create:
            if self.path.exists():
                raise RootError("Database already exists; initialization never overwrites it")
            policy = DEFAULT_POLICY.copy() if policy is None else policy
            validate_policy(policy)
            if not isinstance(objective, str) or not objective.strip():
                raise RootError("Portfolio objective is required")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents accidental overwrite during concurrent init.
            with self.path.open("xb"):
                pass
        elif not self.path.is_file():
            raise RootError("Initialize a portfolio first")
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        if create:
            self.db.executescript(SCHEMA)
            created = self.now()
            self.db.execute("INSERT INTO portfolio(id, objective, policy, created, deadline) VALUES(1,?,?,?,?)",
                            (objective, encode(policy), created, created + policy["max_elapsed_seconds"]))
        if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise RootError("Unsupported database schema version")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def portfolio(self):
        row = dict(self.db.execute("SELECT * FROM portfolio WHERE id=1").fetchone())
        row["policy"] = json.loads(row["policy"])
        return row

    def check(self, extra_storage=0):
        row = self.portfolio()
        if self.now() >= row["deadline"]:
            raise BudgetError("Portfolio deadline reached; stop and evaluate before a new experiment")
        pages = self.db.execute("PRAGMA page_count").fetchone()[0]
        page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
        # Reserve space conservatively before writes, then check the actual DB size.
        if pages * page_size + extra_storage > row["policy"]["max_storage_bytes"]:
            raise BudgetError("SQLite storage budget reached")
        return row

    def reserve_request(self):
        with self.transaction():
            row = self.check()
            if row["requests"] >= row["policy"]["max_requests"]:
                raise BudgetError("Request budget reached")
            if row["downloaded_bytes"] >= row["policy"]["max_download_bytes"]:
                raise BudgetError("Download budget reached")
            self.db.execute("UPDATE portfolio SET requests=requests+1 WHERE id=1")

    def remaining_bytes(self):
        row = self.check()
        return row["policy"]["max_download_bytes"] - row["downloaded_bytes"]

    def charge_bytes(self, count):
        with self.transaction():
            # Account bytes already received even when time expired during a read.
            row = self.portfolio()
            if count < 0 or row["downloaded_bytes"] + count > row["policy"]["max_download_bytes"]:
                raise BudgetError("Download budget reached")
            self.db.execute("UPDATE portfolio SET downloaded_bytes=downloaded_bytes+? WHERE id=1", (count,))
        self.check()

    def put_opportunity(self, value):
        if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"].strip():
            raise RootError("Opportunity requires a nonempty string id")
        payload = encode(value)
        with self.transaction():
            self.check(len(payload.encode()) * 2 + 8192)
            self.db.execute("INSERT INTO opportunities VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, payload=excluded.payload",
                            (value["id"], digest(value), payload))
            self.check()
        return value["id"]

    def opportunities(self):
        return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM opportunities ORDER BY id")]

    def observation(self, observation_id):
        row = self.db.execute("SELECT o.*, p.mode, p.source_url FROM observations o JOIN packages p ON o.package_id=p.id WHERE o.id=?", (observation_id,)).fetchone()
        return dict(row) if row else None

    def save_package(self, package, source_url, mode, query=None, next_url=None):
        payload = encode(package)
        package_id = digest([source_url, mode, package])
        inserted = 0
        with self.transaction():
            self.check(len(payload.encode()) * 4 + 16384)
            self.db.execute("INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?)",
                            (package_id, source_url, mode, self.now(), payload))
            for release in package["releases"]:
                observation_id = digest([mode, release["ocid"], release["id"], release])
                cur = self.db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?)",
                                      (observation_id, package_id, release["ocid"], release["id"], release.get("date"), encode(release)))
                inserted += cur.rowcount
            if query:
                self.db.execute("INSERT INTO checkpoints VALUES(?,?) ON CONFLICT(query) DO UPDATE SET next_url=excluded.next_url", (query, next_url))
            self.check()
        return {"package_id": package_id, "inserted": inserted, "mode": mode}

    def save_screen(self, value):
        with self.transaction():
            self.check(len(encode(value).encode()) + 8192)
            self.db.execute("INSERT INTO screens(opportunity_id, revision, created, payload) VALUES(?,?,?,?)",
                            (value["opportunity_id"], value["revision"], self.now(), encode(value)))
            self.check()

    def cooldown(self, source, seconds):
        # Safety state must persist even if a deadline expires during a failed request.
        self.db.execute("INSERT INTO source_state VALUES(?,?) ON CONFLICT(source) DO UPDATE SET not_before=max(not_before,excluded.not_before)",
                        (source, self.now() + seconds))

    def ready(self, source):
        row = self.db.execute("SELECT not_before FROM source_state WHERE source=?", (source,)).fetchone()
        if row and self.now() < row[0]:
            raise RootError(f"Source cooldown active; retry after epoch {row[0]:.0f}")

    @contextmanager
    def collector_lease(self, seconds=60):
        import uuid
        token = uuid.uuid4().hex
        with self.transaction():
            self.check()
            row = self.db.execute("SELECT expires FROM lease WHERE id=1").fetchone()
            if row and row[0] > self.now():
                raise RootError("A collector is already running")
            self.db.execute("INSERT INTO lease VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET expires=excluded.expires, token=excluded.token",
                            (self.now() + seconds, token))
        try:
            yield
        finally:
            self.db.execute("DELETE FROM lease WHERE id=1 AND token=?", (token,))

    def status(self):
        result = self.portfolio()
        result["counts"] = {table: self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                            for table in ("opportunities", "packages", "observations", "screens")}
        result["cooldowns"] = [dict(row) for row in self.db.execute("SELECT * FROM source_state")]
        result["checkpoint"] = [dict(row) for row in self.db.execute("SELECT * FROM checkpoints")]
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='goals'").fetchone():
            result["goals"] = [dict(row) for row in self.db.execute("SELECT id,state,requests,downloaded_bytes,inference_reserved FROM goals")]
        result["budget_state"] = "expired" if self.now() >= result["deadline"] else "active"
        result["engine_state"] = "local CLI; no scheduler or businesses deployed"
        return result
