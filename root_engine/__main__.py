import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone

from .collector import Collector, read_json, search_url
from .brief import generate_brief, render_preview
from .screen import screen
from .store import RootError, Store
from .promotion import PromotionClosed


def main(argv=None):
    parser = argparse.ArgumentParser(description="ROOT bounded advantage engine — local milestone 1–3")
    parser.add_argument("--db", default=".root/portfolio.sqlite3", help="Portfolio SQLite path")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--objective", required=True)
    init.add_argument("--policy", help="JSON policy file; omitted uses zero-cash defaults")
    add = commands.add_parser("opportunity-add")
    add.add_argument("--file", required=True)
    collect = commands.add_parser("collect")
    mode = collect.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture")
    mode.add_argument("--live", action="store_true")
    collect.add_argument("--published-from")
    collect.add_argument("--published-to")
    collect.add_argument("--limit", type=int, default=100)
    collect.add_argument("--max-pages", type=int, default=1)
    check = commands.add_parser("screen")
    check.add_argument("--opportunity")
    commands.add_parser("observations")
    commands.add_parser("status")
    commands.add_parser("models")
    brief = commands.add_parser("brief", help="Render the deterministic tender preview from stored observations")
    brief.add_argument("--fixture", help="Read observations from a fixture JSON instead of the store")
    brief.add_argument("--json", action="store_true", help="Emit the brief JSON rather than the markdown preview")
    brief.add_argument("--as-of", help="Fixture-only ISO timestamp for reproducible historical demonstrations")
    goal_add = commands.add_parser("goal-create", help="Create a bounded capability /goal")
    goal_add.add_argument("--file", required=True)
    goal_add.add_argument("--model", help="Bind an existing GGUF path and bounded inference plan to this new goal")
    goal_run = commands.add_parser("goal-run", help="Discover, evaluate and optionally adopt a curated GitHub component")
    goal_run.add_argument("--id", required=True)
    goal_mode = goal_run.add_mutually_exclusive_group(required=True)
    goal_mode.add_argument("--live", action="store_true")
    goal_mode.add_argument("--fixture")
    goal_run.add_argument("--local-review", action="store_true")
    for name in ("goal-show", "goal-rollback"):
        command = commands.add_parser(name)
        command.add_argument("--id", required=True)
    promote_show = commands.add_parser("promote-show")
    promote_show.add_argument("--id", required=True)
    promote_allow = commands.add_parser("promote-allow")
    promote_allow.add_argument("--id", required=True)
    promote_allow.add_argument("--actor", required=True)
    promote_deny = commands.add_parser("promote-deny")
    promote_deny.add_argument("--id", required=True)
    promote_deny.add_argument("--actor", required=True)
    promote_deny.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    store = None
    try:
        if args.command == "models":
            from .local_models import inventory
            print(json.dumps(inventory(), indent=2))
            return 0
        store = Store(args.db, create=args.command == "init",
                      objective=getattr(args, "objective", None),
                      policy=read_json(args.policy) if getattr(args, "policy", None) else None)
        if args.command.startswith("promote-"):
            from .promotion import PromotionClosed, allow, deny, show as promote_show_fn
            if args.command == "promote-show":
                result = promote_show_fn(store, args.id)
            elif args.command == "promote-allow":
                result = allow(store, args.id, args.actor)
            else:
                result = deny(store, args.id, args.actor, args.reason)
        elif args.command.startswith("goal-"):
            from .goals import Goals, run_goal
            goals = Goals(store)
            if args.command == "goal-create":
                spec = read_json(args.file)
                if args.model:
                    spec["model_path"] = args.model
                result = goals.create(spec)
            elif args.command == "goal-run":
                result = run_goal(goals, args.id, fixture=read_json(args.fixture) if args.fixture else None, local_review=args.local_review)
            elif args.command == "goal-show":
                result = goals.view(args.id)
            else:
                result = goals.rollback(args.id)
        elif args.command in ("init", "status"):
            result = store.status()
        elif args.command == "opportunity-add":
            result = {"opportunity_id": store.put_opportunity(read_json(args.file))}
        elif args.command == "collect":
            collector = Collector(store)
            if args.fixture:
                result = collector.fixture(args.fixture)
            else:
                if not args.published_from or not args.published_to:
                    raise RootError("Live collection requires both publication bounds")
                result = collector.live(search_url(args.published_from, args.published_to, args.limit), args.max_pages)
        elif args.command == "observations":
            result = [dict(row) for row in store.db.execute("SELECT o.id, o.ocid, o.release_id, o.source_date, p.source_url, p.mode, p.retrieved FROM observations o JOIN packages p ON p.id=o.package_id ORDER BY o.id")]
        elif args.command == "brief":
            as_of = None
            if args.as_of:
                if not args.fixture:
                    raise RootError("--as-of is permitted only with synthetic fixture input")
                as_of = datetime.fromisoformat(args.as_of)
                if as_of.tzinfo is None:
                    as_of = as_of.replace(tzinfo=timezone.utc)
            if args.fixture:
                fixture = read_json(args.fixture)
                rows = [(o["ocid"], o["source_date"], json.dumps(o["payload"])) for o in fixture["observations"]]
            else:
                rows = list(store.db.execute("SELECT ocid, source_date, payload FROM observations ORDER BY source_date"))
            brief = generate_brief(rows, now=as_of)
            if as_of:
                brief["snapshot_note"] += " Fixture simulation with an explicitly supplied historical timestamp."
            result = brief if args.json else render_preview(brief, now=as_of)
            print(result if isinstance(result, str) else json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            return 0
        else:
            candidates = store.opportunities()
            if args.opportunity:
                candidates = [c for c in candidates if c["id"] == args.opportunity]
                if not candidates:
                    raise RootError("Unknown opportunity id")
            result = [screen(store, c) for c in candidates]
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        if args.command == "goal-run" and result["state"] == "stopped":
            return 2
        if args.command == "goal-run" and (result.get("result") or {}).get("evaluation") == "fail":
            return 1
        if args.command.startswith("promote-") and result.get("state") in ("denied", "expired", "failed", "superseded") and not result.get("idempotent"):
            return 1
        return 0
    except PromotionClosed as exc:
        payload = exc.projection if exc.projection is not None else {"error": str(exc)}
        if "error" not in payload:
            payload = dict(payload, error=str(exc))
        print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
        return 1
    except (RootError, OSError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
