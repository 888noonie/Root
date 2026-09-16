"""Trusted subprocess entry point for the curated component benchmark."""

import json
import resource
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from root_engine.retry_component import candidate_delay


def main():
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
    data = json.load(sys.stdin)
    source = data["source"]
    results = []
    for case in data["cases"]:
        value = candidate_delay(source, case["header"], case["now"])
        results.append({"id": case["id"], "actual": value, "expected": case["expected"], "pass": value == case["expected"]})
    print(json.dumps(results, allow_nan=False))


if __name__ == "__main__":
    main()
