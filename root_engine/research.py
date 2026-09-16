"""Advisory research-role output validation.

The proposing model returns either a structured component proposal with exactly the five
keys below (all non-empty strings, pinned URL restricted to exact GitHub repository URLs,
mirroring the discovery host restriction), or a refusal {"refuse": reason}. Enforcement is
post-hoc: the schema is validated by this module, never by a sampler flag, because the
grammar sampler is unreliable at the pinned llama.cpp build.
"""

import re

from .store import RootError

PROPOSAL_KEYS = ("pinned_source_url", "license_spdx", "integration_proposal", "measurable_benefit", "rejection_conditions")
_REPO_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")
_SPDX_LIMIT = 64
_FIELD_LIMIT = 2000
_REFUSE_LIMIT = 400


def validate_research_output(value):
    """Accept exactly a proposal dict or a refusal dict; raise RootError otherwise."""
    if not isinstance(value, dict):
        raise RootError("Research output must be a JSON object")
    if "refuse" in value:
        if set(value) != {"refuse"} or not isinstance(value["refuse"], str) or not value["refuse"].strip() or len(value["refuse"]) > _REFUSE_LIMIT:
            raise RootError("A refusal must contain only a short nonempty 'refuse' reason")
        return value
    if sorted(value) != sorted(PROPOSAL_KEYS):
        raise RootError("A proposal must contain exactly the five proposal keys, nothing else")
    for key in PROPOSAL_KEYS:
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > _FIELD_LIMIT:
            raise RootError(f"Proposal field {key} must be a nonempty bounded string")
    if not _REPO_URL.fullmatch(value["pinned_source_url"].strip()):
        raise RootError("pinned_source_url must be an exact https://github.com/<owner>/<repo> URL")
    if len(value["license_spdx"].strip()) > _SPDX_LIMIT or not re.fullmatch(r"[A-Za-z0-9.:+-]+", value["license_spdx"].strip()):
        raise RootError("license_spdx must be a bounded SPDX-style identifier")
    return value


def validate_research_proposal(value, packet):
    """Ground a proposal in the collector-supplied candidate packet: the repository URL and licence must
    equal the packet's values. Grading is fidelity to the packet, not recall of a hidden gold
    answer: the model may refuse if the packet does not fit the task, and must never invent."""
    value = validate_research_output(value)
    if "refuse" in value:
        return value
    if value["pinned_source_url"].rstrip("/") != packet.get("repository", "").rstrip("/"):
        raise RootError("pinned_source_url does not match the supplied candidate packet")
    if value["license_spdx"].strip() != packet["license_spdx"]:
        raise RootError("license_spdx does not match the supplied candidate packet")
    # Only identity fields are compared here. Free-text claims and optional revision
    # citations are not semantically validated; usefulness requires independent tests.
    return value
