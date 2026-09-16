# First-publication manifest

Independent review: Terra, 16 September 2026. Supersedes Hermes's earlier counts and
sensitive-content sweep. The initial publication includes **62 files**: Python source,
regression tests, synthetic fixtures/policies, documentation and five portable evidence files.
The Git index is the authoritative inclusion list (`git ls-files`).

## Exclusions

| excluded | reason |
|---|---|
| `.root/` | Machine-local runtime state and saved adoption databases; not available in a fresh clone. |
| All SQLite databases and journals/WAL/SHM files | Raw publisher payloads contain personal contact data; model databases retain machine-local state. |
| GGUF weights | Large external assets; no model weights are published. |
| `.env`, `.env.*` | Potential credentials and environment-specific settings. |
| Python caches and KDE `.directory` | Generated machine-local metadata. |

## Evidence included

- Original Gemma control and four-case JSON exports preserve real inference outcomes and
  verbatim local paths. The benchmark used synthetic candidate packets; it is not proof
  of real Requests integration. Exports are unchanged by the independent audit.
- `TENDER_BRIEF.json` and `TENDER_PREVIEW.md` are timestamped historical outputs, not a live offer.
- `tenders_live.export.json` is an allowlisted metadata projection of 32 retained live
  observations. Parties, contacts and free-text descriptions are omitted. It cannot
  reproduce requirement extraction; the original database remains excluded.

## Content checks

The publication candidates contain no detected token/private-key patterns or UK phone-number
patterns. Email-like matches were inspected: synthetic `example.invalid` fixture contacts and
a deliberate URL-userinfo rejection test. Regex checks are supplementary to the structured
allowlist and file review, not proof that arbitrary personal data can always be detected.
All included JSON files parse. No model weights, runtime state or database binaries are staged.

## Provenance and licence

Contracts Finder data is attributed to the UK Government under OGL v3.0 in the evidence
projection and README. Parser fixtures are synthetic; fetched upstream modules are not vendored.
The separate local urllib3 adoption record retains its upstream MIT licence in the excluded
local database. No project licence has been selected; publication does not assert one.

See PUBLICATION_AUDIT.md for code corrections, measured limits and verification results.
