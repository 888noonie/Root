# Contracts Finder verification provenance

## Received handover (2026-09-15)

The user's handover reports: `/Published/Notices` returned 400 on all attempted retrieval variations; the live path is `/Published/Notices/OCDS/Search`; OCDS 1.1, OGL v3.0, cursor pagination and five-minute backoff after 403 were confirmed with a live fetch of 14 September tender notices.

No raw response or earlier verification log was present in the workspace when this tranche started. These live-fetch results are attributed to the handover, not represented as a new measurement by this implementation. The old route is not used or probed.

## Documentation checked in this tranche

- [Official API index](https://www.contractsfinder.service.gov.uk/apidocumentation): lists the OCDS search retrieval route. It also documents `POST Published/Notices` for retrieving a collection by provided identities; failures of the attempted GET variants do not establish that every use of that path is dead.
- [Official OCDS search documentation](https://www.contractsfinder.service.gov.uk/apidocumentation/Notices/1/GET-Published-Notice-OCDS-Search): documents ISO 8601 date bounds, stages, a page limit from 1 to 100, cursor pagination, a version 1.1 sample with OGL v3, and waiting five minutes after 403.

Checked through indexed official documentation on 2026-09-15. Direct documentation-page retrieval returned 403 through the browsing tool; indexed documentation was accessible. This is separate from an API collector request and no retry storm was attempted.

The collector retains the returned package's version, license, publisher and timestamps verbatim. Sample fixtures are clearly synthetic and use `fixture` provenance. Mock-HTTP tests do not constitute a live-fetch verification.

## New implementation smoke attempt

At 2026-09-15 22:31 UTC, ran the CLI against the live search endpoint with publication bounds 2026-09-14T00:00:00Z through 2026-09-14T23:59:59Z, stages=tender and limit=1, using examples/live-smoke-policy.json.

Result: temporary DNS-resolution failure in the shell network sandbox; no response body or live observations were received. The failed attempt is durably counted: requests=1, downloaded_bytes=0, packages=0. The required rerun outside the sandbox was stopped by the unchanged policy with `Request budget reached` before sending any request. The resource allowance was not increased.

State is retained in `.root/live.sqlite3`. This implementation's live retrieval is unverified. The earlier successful fetch remains the user's handover evidence, separate from the new implementation. Pagination, cooldown and import behavior were verified using mock HTTP only.

## Follow-up verification (2026-09-15, parent session)

The collector's live path was re-exercised outside the failed sandbox, on a fresh portfolio (`/tmp/root_live2.sqlite3`) with the same one-request, 2 MiB, £0 policy. Result: success. One request, 5,842 downloaded bytes, one live observation imported (ocid `ocds-b5fd17-3cba68f1-7d49-4d80-9cc9-815a406f6346`, release `392859ec-...-914058`, source date 2026-09-14T19:03:37+01:00) and a pagination checkpoint with `links.next` cursor persisted. The ocid matches the tender release fetched by the earlier manual verification, cross-confirming both paths. Live transport through the engine is now a measured fact, not handover evidence. Retrieval remains read-only; no other engine component was exercised live.

## GitHub capability demonstration (2026-09-16 Europe/London)

The first live capability goal searched GitHub and stopped after zero results (one request, 55 bytes). A separately prebudgeted second goal, with an explicit query fallback, performed two searches and retrieved repository metadata, a commit, README, license and source: seven requests, 96,676 bytes.

Live upstream: [urllib3 source](https://github.com/urllib3/urllib3/blob/b1d30ab61fe0db8f11092805e8c5ac43e091064a/src/urllib3/util/retry.py), pinned to `b1d30ab61fe0db8f11092805e8c5ac43e091064a`. REST metadata identified MIT and the retained license text contained the expected grant. Source, license, README and search responses are stored with live retrieval provenance in `.root/self-improve-live2.sqlite3`; a passing restricted parser is stored and enabled in its `components` table. No fixture supplied the live source. Development/holdout comparison and rollback verification are recorded in SELF_IMPROVEMENT_RESULT.md.

Local model metadata was measured directly from the existing GGUFs. CPU output validation did not pass, and no model-review result is asserted as verified evidence. [Ollama import documentation](https://docs.ollama.com/import) and [llama.cpp](https://github.com/ggml-org/llama.cpp) were considered; the actual runtime was the already-present llama.cpp CLI build 10182, not a new Ollama service or downloaded binary.
