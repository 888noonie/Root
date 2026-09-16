"""Contracts Finder release collector; read-only HTTP, bounded and resumable."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .store import BudgetError, RootError
from .retry_component import active_delay

ENDPOINT = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
SOURCE = "contracts_finder"
LOCAL_INPUT_LIMIT = 2 * 1024 * 1024


def read_json(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(LOCAL_INPUT_LIMIT + 1)
    if len(raw) > LOCAL_INPUT_LIMIT:
        raise RootError("Local input exceeds 2 MiB")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise RootError("Invalid JSON input") from exc


def search_url(published_from, published_to, limit=100):
    try:
        start = datetime.fromisoformat(published_from)
        end = datetime.fromisoformat(published_to)
        if start > end:
            raise ValueError()
    except (ValueError, TypeError):
        raise RootError("Publication bounds must be ordered ISO 8601 timestamps") from None
    if not 1 <= limit <= 100:
        raise RootError("Page limit must be between 1 and 100")
    return ENDPOINT + "?" + urllib.parse.urlencode({"publishedFrom": published_from, "publishedTo": published_to, "stages": "tender", "limit": limit})


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    expected = urllib.parse.urlsplit(ENDPOINT)
    if (parsed.scheme, parsed.netloc, parsed.path) != (expected.scheme, expected.netloc, expected.path) or parsed.fragment:
        raise RootError("Pagination must stay on the exact HTTPS Contracts Finder search endpoint")
    return url


def validate_package(package):
    if not isinstance(package, dict) or package.get("version") != "1.1" or not isinstance(package.get("releases"), list):
        raise RootError("Expected an OCDS 1.1 release package")
    if not isinstance(package.get("uri"), str) or not isinstance(package.get("license"), str):
        raise RootError("Package must retain source URI and license")
    for release in package["releases"]:
        if not isinstance(release, dict) or any(not isinstance(release.get(key), str) or not release[key] for key in ("ocid", "id")):
            raise RootError("Every release needs an OCID and release id; import is atomic")
    links = package.get("links", {})
    if not isinstance(links, dict):
        raise RootError("Invalid package links")
    next_url = links.get("next")
    if next_url is not None:
        if not isinstance(next_url, str):
            raise RootError("Invalid pagination link")
        validate_url(next_url)
    return next_url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RootError("HTTP redirects are disabled; verify endpoint changes explicitly")


class Collector:
    def __init__(self, store, opener=None):
        self.store = store
        self.opener = opener or urllib.request.build_opener(NoRedirect()).open

    def fixture(self, path, source_url=ENDPOINT):
        package = read_json(path)
        validate_package(package)
        with self.store.collector_lease():
            return self.store.save_package(package, source_url, "fixture")

    def fetch(self, url, invocation_deadline=None):
        validate_url(url)
        self.store.ready(SOURCE)
        self.store.reserve_request()  # Failed requests consume allowance too.
        req = urllib.request.Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "ROOT/0.1 read-only research"})
        remaining_time = self.store.portfolio()["deadline"] - self.store.now()
        try:
            with self.opener(req, timeout=max(0.01, min(10, remaining_time))) as response:
                chunks = []
                while True:
                    if invocation_deadline is not None and time.monotonic() >= invocation_deadline:
                        raise BudgetError("Collector invocation reached its 30-second limit")
                    remaining = self.store.remaining_bytes()
                    if remaining <= 0:
                        raise BudgetError("Download budget exhausted; partial response discarded")
                    # read1 avoids waiting for a whole chunk on a trickling source.
                    read = getattr(response, "read1", response.read)
                    data = read(min(65536, remaining))
                    if not data:
                        break
                    self.store.charge_bytes(len(data))
                    chunks.append(data)
                try:
                    return json.loads(b"".join(chunks))
                except (ValueError, UnicodeError) as exc:
                    raise RootError("Source returned invalid JSON; response not imported") from exc
        except urllib.error.HTTPError as exc:
            exc.close()
            delay = 300
            if exc.code in (403, 429):
                try:
                    delay = active_delay(self.store, exc.headers.get("Retry-After"))
                except RootError:
                    self.store.cooldown(SOURCE, 86400)
                    raise RootError("Unsupported Retry-After instruction; source paused for 24 hours pending review") from exc
            if exc.code == 403:
                self.store.cooldown(SOURCE, delay)
                raise RootError("HTTP 403: at least five-minute source cooldown persisted; no retry sent") from exc
            if exc.code == 429:
                self.store.cooldown(SOURCE, delay)
            raise RootError(f"Source returned HTTP {exc.code}; no automatic retry") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RootError(f"Source request failed: {exc.reason if isinstance(exc, urllib.error.URLError) else str(exc)}") from exc

    def live(self, url, max_pages=1):
        validate_url(url)
        if not 1 <= max_pages <= 3:
            raise RootError("One invocation can fetch at most three pages")
        results = []
        started = time.monotonic()
        with self.store.collector_lease():
            checkpoint = self.store.db.execute("SELECT next_url FROM checkpoints WHERE query=?", (url,)).fetchone()
            current = checkpoint[0] if checkpoint else url
            seen = set()
            while current and len(results) < max_pages:
                if current in seen:
                    raise RootError("Pagination cycle detected")
                if time.monotonic() - started >= 30:
                    raise BudgetError("Collector invocation reached its 30-second limit")
                seen.add(current)
                package = self.fetch(current, invocation_deadline=started + 30)
                next_url = validate_package(package)
                if next_url in seen:
                    raise RootError("Pagination cycle detected; page not imported")
                results.append(self.store.save_package(package, current, "live", query=url, next_url=next_url))
                current = next_url
        return {"pages": results, "next_url": current, "complete": current is None}
