"""Grade search answers against eval/cases.toml.

Each answer file is JSON: {"<case number>": {"strong": [...], "partial": [...],
"other_versions": [...]}}, where case numbers are 1-based positions in cases.toml.

Usage:
    python3 eval/grade.py eval/answers/skill_*.json [--show]
"""

import argparse
import json
import tomllib
from collections import Counter
from pathlib import Path

CASES = Path(__file__).with_name("cases.toml")


def grade(case: dict, answer: dict) -> str:
    """Outcome of one answer.

    exists: found (an expected module rated strong), undersold (only partial), missed.
    other_version: pointed (no strong claim, expected module named for another version),
        said_no (no strong claim, other version not mentioned), false_match.
    absent: said_no, false_match.
    """
    strong = set(answer.get("strong", []))
    named = strong | set(answer.get("partial", [])) | set(answer.get("other_versions", []))
    expected = set(case.get("expected", []))
    kind = case["kind"]
    if kind == "exists":
        if strong & expected:
            return "found"
        return "undersold" if named & expected else "missed"
    if strong:
        return "false_match"
    if kind == "other_version":
        return "pointed" if named & expected else "said_no"
    return "said_no"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("answers", nargs="+", type=Path)
    parser.add_argument("--show", action="store_true", help="list every non-ideal outcome")
    args = parser.parse_args()
    cases = tomllib.loads(CASES.read_text())["case"]
    answers = {}
    for path in args.answers:
        answers.update(json.loads(path.read_text()))

    outcomes: dict[str, Counter] = {}
    for n, case in enumerate(cases, 1):
        answer = answers.get(str(n))
        result = grade(case, answer) if answer is not None else "no_answer"
        outcomes.setdefault(case["kind"], Counter())[result] += 1
        if args.show and result not in ("found", "pointed", "said_no"):
            print(f"{n:>2} {case['kind']:13} {result:11} {case['version']} {case['query']}")
            print(f"   expected {case.get('expected', case.get('partial'))}; got {answer}")
    print()
    for kind, counter in outcomes.items():
        total = sum(counter.values())
        print(f"{kind:13} " + ", ".join(f"{k} {v}/{total}" for k, v in counter.most_common()))


if __name__ == "__main__":
    main()
