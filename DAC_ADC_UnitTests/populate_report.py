#!/usr/bin/env python3
r"""
Populate the Result column of test_report.tex from a pytest run.

Usage
-----
    # 1. Run the hardware suite (writes pytest_results.json via conftest.py)
    pytest test_dac_adc_giga.py -v --tb=short

    # 2. Fill in the report template
    python populate_report.py --results pytest_results.json \
                               --template test_report.tex \
                               --out test_report_filled.tex

    # 3. Compile (requires a LaTeX distribution on the machine you run this on)
    pdflatex test_report_filled.tex
    pdflatex test_report_filled.tex   # twice, to resolve the ToC

Notes
-----
- The template (test_report.tex) is never modified in place; output goes
  to a separate file so the template can be reused across runs.
- Parametrized tests (e.g. test_set_voltage_valid[9.9-7]) are collapsed
  onto their base test name (test_set_voltage_valid); the row is marked
  FAIL if *any* parametrization failed/errored, SKIP if none failed but
  at least one was skipped, and PASS only if every parametrization passed.
- Matching is done against `\seqsplit{escaped_test_name}` tokens in the
  .tex, which is how every row in this report identifies its test. Any
  test in the .tex with no corresponding entry in pytest_results.json
  (e.g. it was removed from the driver, or the run used
  `-m "not calibration"`) is left blank, exactly as in the template.
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

_PRIORITY = {"failed": 3, "error": 3, "skipped": 2, "passed": 1}

_STATUS_TEX = {
    "passed": r"\textcolor{passgreen}{\textbf{PASS}}",
    "failed": r"\textcolor{red}{\textbf{FAIL}}",
    "error": r"\textcolor{red}{\textbf{FAIL}}",
    "skipped": r"\textcolor{warnorange}{SKIP}",
}


def load_aggregated_results(results_path: Path) -> dict:
    """nodeid -> outcome  =>  base_test_name -> aggregated outcome."""
    raw = json.loads(results_path.read_text())
    by_base = defaultdict(list)
    for nodeid, outcome in raw.items():
        func = nodeid.split("::")[-1]
        base = func.split("[", 1)[0]
        by_base[base].append(outcome)

    aggregated = {}
    for base, outcomes in by_base.items():
        best = max(outcomes, key=lambda o: _PRIORITY.get(o, 0))
        aggregated[base] = best
    return aggregated


def fill_template(template_text: str, aggregated: dict) -> tuple[str, list, list]:
    filled_tests = []
    missing_tests = []

    text = template_text
    for base_name, outcome in aggregated.items():
        tex_name = base_name.replace("_", r"\_")
        pattern = re.compile(
            r"(\\seqsplit\{" + re.escape(tex_name) + r"\}.*?)&\s*\\\\",
            re.DOTALL,
        )
        status_tex = _STATUS_TEX.get(outcome, outcome)
        new_text, n_subs = pattern.subn(
            lambda m: m.group(1) + "& " + status_tex + r" \\", text, count=1
        )
        if n_subs == 0:
            missing_tests.append(base_name)
        else:
            text = new_text
            filled_tests.append(base_name)

    # anything left in the template with a still-blank Result cell was
    # never run in this session (e.g. calibration tests excluded via
    # -m "not calibration", or a row whose test no longer exists)
    still_blank = re.findall(r"\\seqsplit\{([^}]*)\}(?:(?!\\seqsplit).)*?&\s*\\\\", text, re.DOTALL)

    return text, filled_tests, still_blank


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default="pytest_results.json", type=Path)
    ap.add_argument("--template", default="test_report.tex", type=Path)
    ap.add_argument("--out", default="test_report_filled.tex", type=Path)
    args = ap.parse_args()

    aggregated = load_aggregated_results(args.results)
    template_text = args.template.read_text()
    filled_text, filled_tests, still_blank = fill_template(template_text, aggregated)

    args.out.write_text(filled_text)

    print(f"Filled {len(filled_tests)} test rows in {args.out}")
    not_found_in_template = set(aggregated) - set(filled_tests)
    if not_found_in_template:
        print("Results present but no matching row found in template "
              "(test renamed/removed from report?):")
        for name in sorted(not_found_in_template):
            print(f"  - {name}: {aggregated[name]}")
    if still_blank:
        print("Rows left blank (no result for this test in "
              "pytest_results.json -- not run, e.g. -m \"not calibration\"):")
        for name in sorted(set(still_blank)):
            print(f"  - {name}")


if __name__ == "__main__":
    main()
