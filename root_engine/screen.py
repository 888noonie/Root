"""Transparent eligibility checks, independent of any model or opportunity score."""

import math
import re

from .store import RootError, digest


def screen(store, candidate):
    reasons = []
    evidence_snapshot = []
    policy = store.portfolio()["policy"]

    def defer(code, detail):
        reasons.append({"kind": "missing", "code": code, "detail": detail})

    for field in ("beneficiary", "problem", "deliverable", "alternative", "advantage", "stop_procedure"):
        if not isinstance(candidate.get(field), str) or not candidate[field].strip():
            defer(field, f"Define {field}")

    distribution = candidate.get("distribution", {})
    if not isinstance(distribution, dict):
        distribution = {}
    if not distribution.get("channel") or not distribution.get("steps"):
        defer("distribution_channel", "Name a reachable channel and actionable acquisition steps")
    if distribution.get("autonomy") not in ("agent", "hybrid", "human"):
        defer("distribution_autonomy", "Declare agent, hybrid or human distribution")
    if distribution.get("within_policy") is not True:
        defer("distribution_policy", "Demonstrate that channel operation fits resource and action bounds")
    if distribution.get("autonomy") in ("hybrid", "human") and not distribution.get("owner_steps"):
        defer("owner_distribution_steps", "Record trust-building and other owner acquisition work")

    costs = candidate.get("costs", {})
    if not isinstance(costs, dict):
        costs = {}
    for field in ("setup_gbp", "recurring_gbp", "marginal_gbp", "owner_minutes_per_week", "owner_capacity_minutes_per_week"):
        value = costs.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            defer(field, f"Measure or explicitly estimate {field}; unknowns cannot be zero-filled")
        elif field.endswith("gbp") and value > policy["max_money_gbp"]:
            reasons.append({"kind": "ineligible", "code": field, "detail": "Exceeds the current zero-spending mode"})
    minutes, capacity = costs.get("owner_minutes_per_week"), costs.get("owner_capacity_minutes_per_week")
    if isinstance(minutes, (int, float)) and isinstance(capacity, (int, float)) and minutes > capacity:
        reasons.append({"kind": "ineligible", "code": "owner_capacity", "detail": "Owner workload exceeds declared capacity"})
    if not candidate.get("support_obligations"):
        defer("support_obligations", "Describe support duties, including an explicit none if applicable")

    experiment = candidate.get("experiment", {})
    if not isinstance(experiment, dict):
        experiment = {}
    for field in ("hypothesis", "weakest_assumption", "metric", "pass_criterion", "fail_criterion", "end_condition", "external_deliverable", "external_evidence_method"):
        if not isinstance(experiment.get(field), str) or not experiment[field].strip():
            defer("experiment_" + field, f"Define experiment {field}")
    for field, cap in (("max_money_gbp", policy["max_money_gbp"]), ("max_requests", policy["max_requests"]), ("max_download_bytes", policy["max_download_bytes"]), ("max_elapsed_seconds", policy["max_elapsed_seconds"])):
        value = experiment.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            defer("experiment_" + field, "Set a finite non-negative experiment allowance")
        elif value > cap:
            reasons.append({"kind": "ineligible", "code": "experiment_" + field, "detail": "Exceeds portfolio allowance"})

    refs = candidate.get("evidence_refs", [])
    if not isinstance(refs, list):
        refs = []
    external = False
    for ref in refs:
        observation = store.observation(ref) if isinstance(ref, str) else None
        if observation is None:
            defer("missing_evidence_reference", "Evidence reference does not resolve in the local store")
        else:
            evidence_snapshot.append({"id": ref, "mode": observation["mode"], "source_url": observation["source_url"], "source_date": observation["source_date"]})
            if observation["mode"] == "live":
                external = True
    if not external:
        defer("external_evidence", "Provide a live sourced observation; fixtures cannot establish external facts")

    claims = candidate.get("claims", [])
    if not isinstance(claims, list):
        claims = []
        defer("claims", "Claims must be a structured list")
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("status") not in ("hypothesis", "estimate", "unknown", "observed"):
            defer("claim_status", "Label each claim hypothesis, estimate, unknown or observed")
        elif claim["status"] == "observed":
            observation = store.observation(claim.get("observation_id", "")) if isinstance(claim.get("observation_id", ""), str) else None
            if not observation or observation["mode"] != "live":
                defer("unsupported_observed_claim", "An observed claim must reference live evidence; semantic support still needs research review")
    decision = "reject" if any(r["kind"] == "ineligible" for r in reasons) else "gather_evidence" if reasons else "eligible_for_review"
    result = {"opportunity_id": candidate["id"], "revision": digest(candidate), "screen_version": 1,
              "decision": decision, "reasons": reasons, "evidence": evidence_snapshot,
              "qualification_scope": "research eligibility only; no demand, profit, action authorization or deployment approval established"}
    store.save_screen(result)
    return result


# --- Deterministic keyword PREFILTER for research candidate packets -------------
#
# What this is: a cheap, model-free keyword prefilter that runs before any inference so
# obviously irrelevant candidates cost nothing. It is NOT a capability test.
#
# What it can and cannot establish:
#   * Presence of a keyword ("retry", "backoff") does NOT prove a component implements the
#     capability. A README can promise retries it does not implement.
#   * Absence of a keyword does NOT prove a component lacks the capability. A library can
#     implement exponential backoff without ever using the word "retry"; it can be an HTTP
#     client without saying "HTTP".
#   * Domain words ("image", "desktop", "wallpaper") do NOT establish incompatibility. A
#     desktop wallpaper tool can legitimately contain a robust HTTP client.
# Every refusal here is recorded as a PREFILTER ABSTENTION (keyword level), never as a
# capability finding. Independent functional evaluation - the component benchmark - remains
# the only thing that can establish usefulness or its absence. Both error directions are
# measured by measure_prefilter() and reported separately, because they cost different things.

# Signals that a component plausibly deals with request retry/backoff semantics. Chosen to be
# capability-relevant: generic words like "http" are deliberately EXCLUDED because every
# web-adjacent library mentions HTTP and it carries almost no information about retry logic.
_CAPABILITY_MARKERS = (
    re.compile(r"\bretry[-_ ]?after\b", re.I),
    re.compile(r"\bretr(?:y|ies|ying)\b", re.I),
    re.compile(r"\bback[-_ ]?off\b", re.I),
    re.compile(r"\bexponential\b", re.I),
    re.compile(r"\bjitter\b", re.I),
    re.compile(r"\bidempoten\w*\b", re.I),
    re.compile(r"\brate[-_ ]?limit\w*\b", re.I),
    re.compile(r"\bcircuit[-_ ]?breaker\b", re.I),
    re.compile(r"\bthrottl\w*\b", re.I),
)

# Words that merely SUGGEST a different domain. Recorded as context for a human reviewer;
# they never by themselves justify refusal when capability evidence is present.
_DOMAIN_HINTS = (
    re.compile(r"\bwallpaper\b", re.I),
    re.compile(r"\bimage[ds]?\b", re.I),
    re.compile(r"\bvoice[- ]?clon\w*\b", re.I),
    re.compile(r"\bdesktop\b", re.I),
)


def screen_packet(packet):
    """Keyword prefilter for a research candidate packet.

    Returns {"decision": "refuse"|"eligible", "confidence": "low"|"none", "reason",
    "signals_found", "domain_hints", "establishes": "nothing about actual capability"}.

    "refuse" means only: no retry/backoff-relevant keyword appears in the supplied excerpts,
    so there is nothing for a model to work from. It is a prefilter abstention at keyword
    level, not a finding that the component lacks the capability - a component may implement
    backoff without naming it, and excerpts may be partial. Independent functional evaluation
    remains essential for every candidate that proceeds.
    """
    if not isinstance(packet, dict):
        raise RootError("Candidate packet must be a dict")
    readme = str(packet.get("readme_excerpt", packet.get("readme", "")) or "")
    source = str(packet.get("source_excerpt", packet.get("source", "")) or "")
    haystack = readme + "\n" + source
    signals = [pat.pattern for pat in _CAPABILITY_MARKERS if pat.search(haystack)]
    hints = [pat.pattern for pat in _DOMAIN_HINTS if pat.search(haystack)]
    if not signals:
        reason = ("no retry/backoff-relevant keyword in the supplied excerpts; prefilter "
                  "abstention only (excerpts may be partial and a component may implement "
                  "backoff without naming it)")
        if hints:
            reason += f"; domain hints present: {', '.join(hints)}"
        return {"decision": "refuse", "confidence": "none", "reason": reason,
                "signals_found": [], "domain_hints": hints,
                "establishes": "nothing about actual capability; independent evaluation decides"}
    return {"decision": "eligible", "confidence": "low", "signals_found": signals,
            "domain_hints": hints,
            "reason": "retry/backoff-relevant keyword present; model review and independent "
                      "evaluation proceed (the keyword itself proves nothing)",
            "establishes": "nothing about actual capability; independent evaluation decides"}


def measure_prefilter(cases):
    """Measure prefilter behaviour on a labelled corpus and return the exact confusion matrix.

    ``cases``: iterable of {"id", "packet", "expect", "kind"} where ``kind`` is the TRUTH
    (does the component implement retry/backoff semantics: "legitimate" / "mismatch") and
    ``expect`` is merely what the keyword prefilter is expected to decide on this text.

    Truth and expectation diverge by design, in both directions:
      * a mismatch whose prose mentions retry/backoff (the prefilter cannot tell), and
      * a legitimate component whose excerpts never name the capability (also untellable).

    Confusion matrix over truth x prediction:

                      | truth legit | truth mismatch
        proceed       |     tp      |      fp         <- fp = mismatch let through (costs review time)
        abstain       |     fn      |      tn         <- fn = legitimate component refused
                                                         (danger: usable component discarded)

    Rates are returned separately because the two errors have different costs. Cases marked
    ``"set": "challenge"`` are counted in their own set so a change that only improves the
    headline numbers cannot hide behind them. No expectation is ever rewritten to improve a metric.
    """
    m = {"tp": [], "fp": [], "fn": [], "tn": []}
    expectation_divergence = []
    kinds = {"legitimate": 0, "mismatch": 0}
    challenge_set = {"total": 0, "proceeded": 0}
    combined = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for case in cases:
        if case.get("kind") not in ("legitimate", "mismatch"):
            raise RootError("Prefilter corpus requires explicit legitimate/mismatch truth labels")
        decision = screen_packet(case["packet"])["decision"]
        truth = case["kind"]
        proceeded = decision == "eligible"
        key = ("tp" if proceeded else "fn") if truth == "legitimate" else ("fp" if proceeded else "tn")
        combined[key] += 1
        if case.get("expect") and case["expect"] != decision:
            expectation_divergence.append({"id": case["id"], "expected": case["expect"], "decided": decision})
        if case.get("set") == "challenge":
            challenge_set["total"] += 1
            if screen_packet(case["packet"])["decision"] == "eligible":
                challenge_set["proceeded"] += 1
            continue
        truth = "legitimate" if case.get("kind", "legitimate") == "legitimate" else "mismatch"
        kinds[truth] += 1
        decision = screen_packet(case["packet"])["decision"]
        proceeded = decision == "eligible"
        key = ("tp" if proceeded else "fn") if truth == "legitimate" else ("fp" if proceeded else "tn")
        m[key].append(case["id"])
    legit, mism = kinds["legitimate"], kinds["mismatch"]
    return {
        "cases": sum(kinds.values()) + challenge_set["total"],
        "confusion": m,
        "counts": {k: len(v) for k, v in m.items()},
        "legitimate_total": legit,
        "mismatch_total": mism,
        "truth_definition": ("truth = does the component implement retry/backoff semantics; "
                             "prediction = did the prefilter let it proceed. The matrix is truth x prediction, "
                             "NOT agreement with any expected label."),
        "legitimate_refusal_rate": (len(m["fn"]) / legit) if legit else None,
        "mismatch_proceed_rate": (len(m["fp"]) / mism) if mism else None,
        "expectation_divergence": expectation_divergence,
        "challenge_set": challenge_set,
        "combined_counts": combined,
        "combined_mismatch_proceed_rate": combined["fp"] / (combined["fp"] + combined["tn"]) if combined["fp"] + combined["tn"] else None,
        "reported_as": ("separate counts per error type; a single accuracy figure would hide that "
                        "the prefilter's only unrecoverable error is refusing a usable component"),
    }
