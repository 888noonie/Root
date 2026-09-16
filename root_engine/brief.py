"""Deterministic tender-intelligence brief generation (phase 2).

Turns live OCDS observations into one evidence-backed preview for a narrowly defined
buyer: small transport operators (1-8 seat vehicles) serving East Sussex County Council
school/passenger-transport routes.

Design rules, in order of importance:

1. Resolve to the latest release. Multiple observations can share an ``ocid``; the brief
   scores only the latest applicable release so a revised deadline is used and a
   cancelled/withdrawn notice is dropped rather than reported from a stale copy.
2. Scope is mandatory, not additive. A notice is eligible only if it is both an active
   East Sussex County Council tender and in the transport family. Everything else is out.
3. Expiry is stated precisely (absolute instant plus hours remaining), never as a coarse
   window: a bid deadline is the single fact an operator acts on.
4. Publisher flags are reported as flags. ``tender.suitability.sme`` is the *publisher's*
   declaration; it does not establish that a 1-8 vehicle operator is eligible to bid.
5. Missing information is marked as missing. Unknowns are never zero-filled or inferred
   silently, and derived values are labelled as derived.

All scoring is deterministic and model-free: the same input yields the same score.
The brief is an advisory artifact; distribution requires separate explicit authorization.
"""

import json
import re
from datetime import datetime, timezone

from .store import RootError

# --- Buyer definition (narrow) ------------------------------------------------
BUYER_NAME = "east sussex county council"
KEYWORDS = ("taxi", "mpv", "passenger assistant", "school", "home to school", "sen transport", "special educational")
CPV_TRANSPORT_PREFIX = "60"          # CPV 60000000 family: transport services
SCORE_THRESHOLD = 40                 # deterministic: below this the notice is not in the preview
DEADLINE_SOON_HOURS = 48
DEADLINE_WINDOW_DAYS = 14
NON_BIDDABLE_STATUS = ("cancelled", "unsuccessful", "withdrawn", "closed")

# Fields an operator needs that these notices demonstrably do not publish. Listed so the
# preview can state what is still unknown instead of implying the notice is complete.
UNKNOWN_FIELDS = (
    "estimated contract value",
    "award criteria and weightings",
    "lot structure (whether this notice is one route or a batch)",
    "insurance, vehicle licence and safeguarding/DBS requirements",
    "submission documents beyond the opportunity notice",
    "detailed collection/delivery addresses (beyond postcodes and venue names)",
)


def parse_deadline(value):
    """Parse an ISO endDate to a timezone-aware datetime; None if absent/unparseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def hours_until(deadline, now):
    """Hours from ``now`` to ``deadline``; None when the deadline is unknown."""
    if deadline is None:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (deadline - now).total_seconds() / 3600.0


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else None


def _release_date(payload, source_date=None):
    """Best available timestamp for ordering releases: the release's own date, else the
    observation's source_date. Returns a tz-aware datetime or a sortable string."""
    candidate = payload.get("date") or source_date
    parsed = parse_deadline(candidate) if isinstance(candidate, str) else None
    return parsed or datetime.min.replace(tzinfo=timezone.utc)


def _merge_carry_forward(latest, earlier_payloads):
    """Merge nested objects newest-first, retaining null tombstones until finished.

    This is a limited preview resolver, not an OCDS compiled-release implementation:
    arrays supplied in a later release replace earlier arrays. Schema-aware identifier
    merging for arrays is not implemented. Omitted fields retain visible provenance.
    """
    from copy import deepcopy
    merged = deepcopy(latest)
    carried = []

    def inherit(target, previous, prefix, release_id):
        for key, value in previous.items():
            field = f"{prefix}.{key}" if prefix else key
            if key not in target:
                target[key] = deepcopy(value)
                if value is not None:
                    carried.append({"field": field, "from_release": release_id,
                                    "scope": "tender" if field.startswith("tender.") else "release"})
            elif isinstance(target[key], dict) and isinstance(value, dict):
                inherit(target[key], value, field, release_id)

    for earlier in earlier_payloads:
        inherit(merged, earlier, "", earlier.get("id"))

    def remove_nulls(value):
        if isinstance(value, dict):
            return {key: remove_nulls(item) for key, item in value.items() if item is not None}
        if isinstance(value, list):
            return [remove_nulls(item) for item in value]
        return value

    return remove_nulls(merged), carried


def resolve_latest(observations):
    """Resolve observations to the latest applicable release per ``ocid``.

    Accepts (ocid, source_date, payload) rows. Returns a list of dicts ordered by
    resolution date ascending, each:

        {"ocid", "source_date", "release_id", "payload", "superseded", "tags",
         "carried_forward", "excluded_reason"}

    Semantics, verified against the live publisher: releases sharing an ``ocid`` are distinct
    immutable releases, and an amendment arrives as a further release tagged ``tenderAmendment``.
    Selection is by release date with the release id as a deterministic tiebreak, so ordering
    never depends on observation or query order. Fields stated by an earlier release but not
    repeated in the latest are carried forward and listed (never silently discarded) - see
    ``_merge_carry_forward``.

    ``excluded_reason`` is set (and the payload kept for audit) when the latest release is
    cancelled, withdrawn, unsuccessful or closed, or carries such a tag, so a cancellation is
    reported rather than dropped or overwritten by a stale live deadline.
    """
    if not isinstance(observations, list):
        raise RootError("Observations must be a list")
    best = {}
    counts = {}
    for ocid, source_date, payload in observations:
        try:
            release = json.loads(payload) if isinstance(payload, str) else payload
        except (ValueError, TypeError) as exc:
            raise RootError("Observation payload is not valid JSON") from exc
        if not isinstance(release, dict):
            raise RootError("Observation payload must be a JSON object")
        counts[ocid] = counts.get(ocid, 0) + 1
        key = (_release_date(release, source_date), str(release.get("id") or ""))
        current = best.get(ocid)
        if current is None or key > current[0]:
            best[ocid] = (key, source_date, release)

    resolved = []
    for ocid, (_key, source_date, release) in best.items():
        tender = release.get("tender") or {}
        status = str(tender.get("status") or "").lower()
        tags = [str(t).lower() for t in (release.get("tag") or [])]
        excluded = None
        if status in NON_BIDDABLE_STATUS:
            excluded = f"latest release status is '{status}'"
        elif any(tag in tags for tag in ("cancelled", "withdrawn", "tendercancellation")):
            excluded = "latest release carries a cancellation tag"
        earlier_pairs = []
        for obs_ocid, _sd, obs_payload in observations:
            if obs_ocid != ocid:
                continue
            if isinstance(obs_payload, str):
                try:
                    obs_payload = json.loads(obs_payload)
                except ValueError:
                    continue
            if not isinstance(obs_payload, dict) or obs_payload is release:
                continue
            earlier_pairs.append((_release_date(obs_payload, _sd), str(obs_payload.get("id") or ""), obs_payload))
        earlier = [pair[2] for pair in sorted(earlier_pairs, key=lambda pair: pair[:2], reverse=True)]
        merged, carried = _merge_carry_forward(release, earlier)
        merged_status = str((merged.get("tender") or {}).get("status") or "").lower()
        if merged_status in NON_BIDDABLE_STATUS:
            excluded = f"resolved release status is '{merged_status}'"
        resolved.append({
            "ocid": ocid,
            "source_date": source_date,
            "release_id": release.get("id"),
            "payload": merged,
            "superseded": counts[ocid] - 1,
            "tags": [str(tag) for tag in (release.get("tag") or [])],
            "carried_forward": carried,
            "excluded_reason": excluded,
        })
    resolved.sort(key=lambda item: str(item["source_date"] or ""))
    return resolved


# --- Requirement extraction ---------------------------------------------------

_PA_CONDITIONAL = re.compile(r"\bif\b.{0,40}\balone\b", re.I)
_POSTCODE = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b", re.I)


def _clean(text):
    return str(text or "").replace("\r", "\n")


def _labelled(text, label):
    """Value following 'Label:' on its own line, else any inline 'Label: value'."""
    match = re.search(rf"^[ \t]*{re.escape(label)}[ \t]*:[ \t]*([^\n]+)$", _clean(text), re.I | re.M)
    if match:
        return match.group(1).strip() or None
    match = re.search(rf"{re.escape(label)}[ \t]*:[ \t]*([^\n]+)", _clean(text), re.I)
    return (match.group(1).strip() or None) if match else None


def _normalise_pa(raw):
    if not raw:
        return "unknown"
    if _PA_CONDITIONAL.search(raw):
        return "conditional (as stated in the notice)"
    if re.search(r"^\s*no\b", raw, re.I) or re.search(r"\bnot required\b", raw, re.I):
        return "not required"
    if re.search(r"^\s*yes\b", raw, re.I) or re.search(r"\brequired\b", raw, re.I):
        return "required"
    return "unknown"


def _postcode_in(text):
    match = _POSTCODE.search(text or "")
    if not match:
        return None
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def extract_requirements(payload):
    """Extract operator-actionable requirements from a notice's free text.

    Returns a dict of actionable fields (value or None) plus:
      * ``missing``      - fields this notice does not publish (see UNKNOWN_FIELDS plus any
                           free-text field absent from this particular notice)
      * ``derived``      - values that were derived rather than stated
      * ``operator_flags`` - free-text conditions an operator must meet (harness, space, etc.)
    """
    tender = payload.get("tender") or {}
    description = _clean(tender.get("description"))
    title = str(tender.get("title") or "")

    vehicle_raw = _labelled(description, "Vehicle type")
    from_raw = _labelled(description, "From")
    to_raw = _labelled(description, "To")
    pa_raw = _labelled(description, "Passenger Assistant Required")
    frequency = _labelled(description, "Frequency")
    times = _labelled(description, "Daily School Time")
    comments = _labelled(description, "Comments for Operator")

    # Seat count: take it from the notice's own vehicle line only. Never from the title's
    # "(1-8 seats)" range, which describes the framework's permissible band, not this route's
    # vehicle - reading "8" from "1-8" would misstate the requirement to an operator.
    seats = None
    seat_range = None
    range_pattern = r"(\d+)\s*(?:[-–]|to)\s*(\d+)\s*seats?"
    band = re.search(range_pattern, title, re.I)
    if band:
        seat_range = f"{band.group(1)}-{band.group(2)} seats (band stated in the notice title)"
    seat_match = re.search(r"(\d+)\s*(?:seat|seater)s?\b", vehicle_raw or "", re.I)
    if seat_match and not re.search(range_pattern, vehicle_raw or "", re.I):
        seats = int(seat_match.group(1))

    flag_terms = ("harness", "space needed", "wheelchair", "mobility", "nonverbal", "hearing impairment",
                  "asd", "adhd", "sensory", "behaviour", "hoist", "escort")
    lowered = description.lower()
    operator_flags = [term for term in flag_terms if term in lowered]

    route_to_venue = None
    if to_raw:
        venue = _POSTCODE.sub("", to_raw).strip(" ,")
        route_to_venue = venue or None

    from_pc = _postcode_in(from_raw or "")
    to_pc = _postcode_in(to_raw or "")

    documents = tender.get("documents") or []
    notice_doc_url = None
    portal_urls = []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        url = str(doc.get("url") or "")
        if doc.get("documentType") == "tenderNotice" and url and notice_doc_url is None:
            notice_doc_url = url
        elif url and "contractsfinder.service.gov.uk" not in url:
            portal_urls.append(url)

    method_detail = str(tender.get("procurementMethodDetails") or "").strip() or None
    period = tender.get("tenderPeriod") or {}
    contract_period = tender.get("contractPeriod") or {}

    registration = None
    portal_mentioned = any("sproc.net" in url.lower() for url in portal_urls) or "sproc.net" in description.lower()
    if not any("sproc.net" in url.lower() for url in portal_urls) and "sproc.net" in description.lower():
        portal_urls.append("https://www.sproc.net")
    if portal_mentioned:
        registration = ("This opportunity is distributed on SProc.net; the notice states the "
                        "opportunity has been distributed there, so supplier registration on that "
                        "portal should be checked for registration and invitation requirements; "
                        "distribution alone does not establish eligibility or a registration condition")
    if method_detail and "restricted" in method_detail.lower():
        registration = ((registration + "; " if registration else "") +
                        f"procedure is '{method_detail}', which restricts who can be invited to bid")

    missing = []
    if not tender.get("value"):
        missing.append("estimated contract value")
    if not tender.get("awardCriteria"):
        missing.append("award criteria and weightings")
    if not tender.get("lots"):
        missing.append("lot structure (whether this notice is one route or a batch)")
    if not tender.get("submissionMethod"):
        missing.append("submission method")
    if len([d for d in documents if isinstance(d, dict) and d.get("documentType") == "tenderNotice"]) <= 1:
        missing.append("submission documents beyond the opportunity notice")
    missing.append("insurance, vehicle licence and safeguarding/DBS requirements")
    if from_pc and to_pc:
        missing.append("detailed collection/delivery addresses (notice states postcodes and venue names only)")
    else:
        missing.append("detailed collection/delivery addresses (beyond postcodes and venue names)")
    if not period.get("endDate"):
        missing.append("bid deadline")

    derived = []
    if seats:
        derived.append(f"seat count {seats} read from the notice's vehicle line")
    if seat_range:
        derived.append(seat_range)
    if from_pc or to_pc:
        derived.append("route geography taken from postcodes stated in the notice")

    return {
        "notice_title": title or None,
        "route": {"from_text": from_raw, "from_postcode": from_pc,
                  "to_text": to_raw, "to_postcode": to_pc, "venue": route_to_venue},
        "vehicle": {"type_text": vehicle_raw, "seats": seats, "seat_band": seat_range,
                    "operator_notes": comments},
        "passenger_assistant": {"stated_text": pa_raw, "requirement": _normalise_pa(pa_raw)},
        "frequency": frequency,
        "daily_times": times,
        "operator_flags": operator_flags,
        "supplier_registration_requirement": registration,
        "bidding_access": {"notice_url": notice_url(payload), "portals": portal_urls,
                           "access_note": "open the notice URL to confirm current submission requirements"},
        "contract": {"method": method_detail,
                     "period_start": contract_period.get("startDate"),
                     "period_end": contract_period.get("endDate")},
        "missing": missing,
        "derived": derived,
    }


def notice_url(payload):
    """First tenderNotice document URL, else the notice/ID path."""
    tender = payload.get("tender") or {}
    documents = tender.get("documents")
    if isinstance(documents, list):
        for doc in documents:
            if isinstance(doc, dict) and doc.get("documentType") in ("tenderNotice", None) and doc.get("url"):
                return str(doc["url"])
    ocid = payload.get("ocid")
    if ocid:
        return "https://www.contractsfinder.service.gov.uk/Notice/" + ocid.replace("ocds-b5fd17-", "")
    return ""


def score_release(payload, now=None):
    """Deterministic relevance + urgency assessment for one resolved OCDS release.

    Scope is mandatory: eligible only if it is both an active East Sussex County Council
    tender and in the transport family (CPV 60xxxx or transport keywords). A passed
    deadline is not biddable and is never relevant. Within scope the score ranks by
    deadline proximity and keyword fit. ``suitability.sme`` is reported as a publisher
    flag and deliberately does not contribute to the score.
    """
    if not isinstance(payload, dict):
        raise RootError("Release payload must be a dict")
    now = now or datetime.now(timezone.utc)
    tender = payload.get("tender") or {}
    if not isinstance(tender, dict):
        raise RootError("Tender must be a JSON object")
    if tender.get("status") != "active":
        return {"score": 0, "reasons": ["not an explicitly active tender"],
                "relevant": False, "publisher_flags": {}}

    reasons = []
    classification = tender.get("classification") or {}
    cpv = str(classification.get("id") or "")
    title = str(tender.get("title") or "")
    description = str(tender.get("description") or "")
    text = (title + " " + description).lower()
    keyword_hits = [kw for kw in KEYWORDS if re.search(re.escape(kw), text)]
    transport_signal = cpv.startswith(CPV_TRANSPORT_PREFIX) or bool(keyword_hits)
    buyer = str((payload.get("buyer") or {}).get("name") or "").lower()
    escc_buyer = BUYER_NAME in buyer

    if not escc_buyer:
        return {"score": 0, "reasons": ["buyer not the named East Sussex County Council"],
                "relevant": False, "publisher_flags": {}}
    if not transport_signal:
        return {"score": 0, "reasons": ["not a transport-family notice (CPV 60xxxx or transport keywords)"],
                "relevant": False, "publisher_flags": {}}

    score = 30  # in-scope base
    reasons.append("named buyer")
    if cpv.startswith(CPV_TRANSPORT_PREFIX):
        score += 15
        reasons.append(f"CPV {CPV_TRANSPORT_PREFIX}xxxx: transport services")
    score += min(len(keyword_hits), 3) * 5
    reasons.extend(f"keyword '{kw}'" for kw in keyword_hits[:3])

    deadline = parse_deadline((tender.get("tenderPeriod") or {}).get("endDate"))
    hours = hours_until(deadline, now)
    urgency = "unknown"
    if hours is not None:
        if hours <= 0:
            return {"score": 0, "reasons": ["deadline passed; not biddable"],
                    "relevant": False, "publisher_flags": _flags(tender), "hours_remaining": hours, "deadline": _iso(deadline)}
        if hours <= DEADLINE_SOON_HOURS:
            score += 10
            urgency = "expires_within_48h"
            reasons.append(f"expires within {DEADLINE_SOON_HOURS}h ({hours:.1f}h remaining)")
        elif hours <= DEADLINE_WINDOW_DAYS * 24:
            score += 5
            urgency = "expires_within_14d"
            reasons.append(f"expires within {DEADLINE_WINDOW_DAYS} days ({hours / 24:.1f} days remaining)")
        else:
            urgency = "later"

    if payload.get("initiationType") == "tender":
        score += 5
        reasons.append("tender initiation")

    return {"score": score, "reasons": reasons, "relevant": score >= SCORE_THRESHOLD,
            "publisher_flags": _flags(tender), "hours_remaining": hours, "urgency": urgency,
            "deadline": _iso(deadline)}


def _flags(tender):
    """Publisher declarations, reported as flags rather than eligibility facts."""
    suitability = tender.get("suitability") or {}
    flags = {}
    if "sme" in suitability:
        flags["sme_declared_by_publisher"] = suitability.get("sme")
        flags["sme_note"] = ("publisher flag: states the buyer welcomes SMEs; it does not establish "
                             "that a 1-8 vehicle operator meets the route's own requirements")
    if "vcse" in suitability:
        flags["vcse_declared_by_publisher"] = suitability.get("vcse")
    return flags


def generate_brief(observations, now=None):
    """Build a preview from (ocid, source_date, payload) rows, resolving to latest releases."""
    now = now or datetime.now(timezone.utc)
    resolved = resolve_latest(observations)
    notices = []
    excluded = []
    expired = []
    for item in resolved:
        payload = item["payload"]
        if item["excluded_reason"]:
            excluded.append({"ocid": item["ocid"], "release_id": item["release_id"],
                             "reason": item["excluded_reason"]})
            continue
        result = score_release(payload, now=now)
        if not result["relevant"]:
            if result.get("hours_remaining") is not None and result["hours_remaining"] <= 0:
                expired.append({"ocid": item["ocid"], "release_id": item["release_id"],
                                "title": str((payload.get("tender") or {}).get("title") or "")[:160],
                                "deadline": result.get("deadline"),
                                "expired_hours_ago": -result["hours_remaining"]})
            continue
        tender = payload.get("tender") or {}
        requirements = extract_requirements(payload)
        notices.append({
            "ocid": item["ocid"],
            "release_id": item["release_id"],
            "source_date": item["source_date"],
            "superseded_observations": item["superseded"],
            "release_tags": item.get("tags") or [],
            "carried_forward": item.get("carried_forward") or [],
            "title": str(tender.get("title") or "Untitled notice")[:160],
            "buyer": str((payload.get("buyer") or {}).get("name") or "Unknown buyer"),
            "cpv": ((tender.get("classification") or {}).get("id") or ""),
            "deadline": result.get("deadline"),
            "hours_remaining": result.get("hours_remaining"),
            "urgency": result.get("urgency"),
            "url": notice_url(payload),
            "score": result["score"],
            "reasons": result["reasons"],
            "publisher_flags": result["publisher_flags"],
            "published": (tender.get("datePublished") or ""),
            "requirements": requirements,
        })
    notices.sort(key=lambda item: (item["hours_remaining"] is None, item["hours_remaining"] if item["hours_remaining"] is not None else 1e9))
    return {
        "generated": now.isoformat(),
        "snapshot_note": ("Timestamped historical snapshot of the publisher's records at 'generated'. "
                          "Not a live feed: notices are amended and cancelled, so re-query before acting. "
                          "Hours-remaining values are recomputed at render time from each stored deadline."),
        "buyer_definition": BUYER_NAME,
        "operator_profile": "small transport operators with 1-8 seat vehicles serving East Sussex school/passenger transport routes",
        "distribution_state": "prepared preview; not distributed - distribution requires explicit authorization",
        "notices": notices,
        "relevant_count": len(notices),
        "excluded": excluded,
        "expired": expired,
        "observations_total": len(observations),
        "unique_ocids": len(resolved),
    }


def _fmt_hours(hours):
    if hours is None:
        return "deadline not stated"
    if hours <= 0:
        return f"expired {-hours:.1f}h ago"
    if hours < 48:
        return f"{hours:.1f}h remaining"
    return f"{hours / 24:.1f} days remaining"


def render_preview(brief, now=None):
    """Render the operator-facing preview as markdown.

    Remaining time is RECOMPUTED at render time from each stored deadline, so a preview
    rendered later than it was generated shows the true remaining time rather than the value
    captured at generation. Opportunities whose deadline has passed are excluded from the
    current actionable list and reported separately: expired items are not actionable, and
    listing them as opportunities would mislead.
    """
    now = now or datetime.now(timezone.utc)
    lines = [
        "# Tender preview - East Sussex school/passenger transport",
        "",
        f"Generated: {brief['generated']} | Rendered: {now.isoformat()}",
        f"Buyer: {brief['buyer_definition']}",
        f"Operator profile: {brief['operator_profile']}",
        f"State: {brief['distribution_state']}",
        "",
        brief["snapshot_note"],
        "",
    ]
    actionable, elapsed, unknown_deadlines = [], [], []
    for notice in brief["notices"]:
        deadline = parse_deadline(notice.get("deadline"))
        hours = hours_until(deadline, now)
        notice = dict(notice)
        notice["hours_remaining"] = hours
        if hours is not None and hours <= 0:
            elapsed.append(notice)
        elif hours is None:
            unknown_deadlines.append(notice)
        else:
            actionable.append(notice)
    actionable.sort(key=lambda n: (n["hours_remaining"] is None,
                                   n["hours_remaining"] if n["hours_remaining"] is not None else 1e9))
    lines.insert(7, (f"{len(actionable)} of {brief['relevant_count']} in-scope notices are still actionable,"
                     f" ordered by time remaining (from {brief['observations_total']} observations covering "
                     f"{brief['unique_ocids']} notices, resolved to each notice's latest release)."
                     " Expired notices are listed separately and are not actionable."))
    for notice in actionable:
        req = notice["requirements"]
        route = req["route"]
        vehicle = req["vehicle"]
        pa = req["passenger_assistant"]
        lines += [
            f"## {notice['title']}",
            "",
            f"- **Expires:** {notice['deadline']} ({_fmt_hours(notice['hours_remaining'])})",
            f"- **Buyer:** {notice['buyer']}  |  **CPV:** {notice['cpv']}  |  **Score:** {notice['score']}",
            f"- **Notice:** {notice['url']}",
            f"- **Route:** {route['from_text'] or 'not stated'} -> {route['to_text'] or 'not stated'}"
            + (f"  (venue: {route['venue']})" if route["venue"] else ""),
            f"- **Vehicle:** {vehicle['type_text'] or 'not stated'}"
            + (f"  | seats: {vehicle['seats']}" if vehicle["seats"] else "")
            + (f"  | framework band: {vehicle['seat_band']}" if vehicle.get("seat_band") else ""),
            f"- **Passenger assistant:** {pa['requirement']}"
            + (f"  (notice states: {pa['stated_text']})" if pa["stated_text"] else ""),
            f"- **Frequency:** {req['frequency'] or 'not stated'}  |  **Times:** {req['daily_times'] or 'not stated'}",
            f"- **Operator notes:** {vehicle['operator_notes'] or 'not stated'}",
        ]
        if req["operator_flags"]:
            lines.append(f"- **Conditions seen in the notice text:** {', '.join(req['operator_flags'])}")
        if req["supplier_registration_requirement"]:
            lines.append(f"- **Registration/access:** {req['supplier_registration_requirement']}")
        lines.append(f"- **Bidding access:** {req['bidding_access']['access_note']}")
        if req["bidding_access"]["portals"]:
            lines.append(f"- **Portal(s):** {', '.join(req['bidding_access']['portals'])}")
        lines.append("**Facts stated in the notice:** " + "; ".join(
            f"{k}={v}" for k, v in (("route_from", req["route"]["from_text"]), ("route_to", req["route"]["to_text"]),
                                    ("vehicle", vehicle["type_text"]), ("frequency", req["frequency"]))
            if v))
        if req["supplier_registration_requirement"]:
            lines.append("**Registration condition (does not establish invitation eligibility):** "
                         "the notice states a distribution/registration route; being registered does not mean "
                         "the buyer will invite this operator to bid, particularly under a restricted procedure.")
        if notice["publisher_flags"]:
            for key, value in notice["publisher_flags"].items():
                if key.endswith("_note"):
                    continue
                lines.append(f"- **Publisher flag:** {key} = {value}")
        lines.append(f"- **Score explanation at generation ({brief['generated']}): {notice['score']}:** {', '.join(notice['reasons'])}")
        if notice["superseded_observations"]:
            tags = ", ".join(notice.get("release_tags") or []) or "unspecified"
            lines.append(f"- **Revision note:** {notice['superseded_observations']} earlier observation(s) superseded; "
                         f"this preview uses the latest release (tag: {tags})")
        if notice.get("carried_forward"):
            fields = ", ".join(item["field"] for item in notice["carried_forward"])
            lines.append(f"- **Carried forward from an earlier release (not restated in the latest):** {fields}")
        lines.append("")
        lines.append("**Still unknown (not published in the notice - confirm before committing):**")
        for item in req["missing"]:
            lines.append(f"- {item}")
        lines.append("")
        if req["derived"]:
            lines.append("**Derived (not stated verbatim):** " + "; ".join(req["derived"]))
            lines.append("")
    if elapsed or brief.get("expired"):
        lines.append("## Expired - no longer actionable")
        for notice in elapsed:
            lines.append(f"- {notice['title']} - deadline {notice['deadline']} "
                         f"({_fmt_hours(notice['hours_remaining'])})")
        for item in brief.get("expired", []):
            lines.append(f"- {item['title']} - deadline {item['deadline']} "
                         f"({_fmt_hours(hours_until(parse_deadline(item['deadline']), now))})")
        lines.append("")
    if unknown_deadlines:
        lines += ["## Deadline unknown - requires verification", ""]
        lines.extend(f"- {notice['title']} - {notice['url']}" for notice in unknown_deadlines)
        lines.append("")
    if brief["excluded"]:
        lines.append("## Cancelled / withdrawn / non-biddable at resolution")
        for item in brief["excluded"]:
            lines.append(f"- {item['ocid']} - {item['reason']}")
        lines.append("")
    lines += [
        "---",
        "",
        "Scoring is deterministic and model-free: CPV + transport keywords + deadline proximity. "
        "Publisher SME flags are reported but do not establish eligibility. "
        "Unknowns above are genuine gaps in the published notice, not assessment failures.",
    ]
    return "\n".join(lines)
