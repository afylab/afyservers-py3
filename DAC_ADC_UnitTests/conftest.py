"""
Session-wide pytest hook that records each test's outcome to
`pytest_results.json` in the rootdir, so that `populate_report.py` can
fill in the Result column of test_report.tex after a run.

No extra plugin (e.g. pytest-json-report) is required -- this uses only
pytest's built-in hook API.
"""

import json
from pathlib import Path

_results = {}

# outcome priority when multiple phases (setup/call/teardown) exist for
# the same nodeid: a failure at any phase should mark the test failed.
_PRIORITY = {"failed": 3, "error": 3, "skipped": 2, "passed": 1}


def pytest_runtest_logreport(report):
    nodeid = report.nodeid
    outcome = report.outcome
    if report.when == "setup" and outcome != "passed":
        # setup error/skip -> whole test never ran
        _results[nodeid] = outcome
        return
    if report.when != "call":
        return
    prev = _results.get(nodeid)
    if prev is None or _PRIORITY.get(outcome, 0) >= _PRIORITY.get(prev, 0):
        _results[nodeid] = outcome


def pytest_sessionfinish(session, exitstatus):
    out_path = Path(str(session.config.rootdir)) / "pytest_results.json"
    with open(out_path, "w") as f:
        json.dump(_results, f, indent=2, sort_keys=True)
    print(f"\n[conftest] wrote {len(_results)} test outcomes -> {out_path}")
