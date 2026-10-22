"""The verification suite: case definitions are valid and closed-form cases pass."""

import pytest

from slipsurface.lem import METHODS
from verification import run

CASES = run.load_cases()
REQUIRED = {"id", "title", "kind", "reference_type", "source", "status"}


def test_case_ids_are_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_case_definition(case):
    assert REQUIRED <= set(case), REQUIRED - set(case)
    assert case["kind"] in {"analytic", "project"}
    assert case["status"] in {"active", "planned"}
    if case["status"] != "active":
        return
    assert set(case["tolerance"]) <= {"abs", "rel"} and case["tolerance"]
    if case["kind"] == "project":
        assert (run.ROOT / case["project"]).is_file()
        assert case["reference"] and set(case["reference"]) <= set(METHODS)
    else:
        from verification.analytic import FUNCTIONS

        assert case["function"] in FUNCTIONS


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if c["status"] == "active" and c["kind"] == "analytic"],
    ids=lambda c: c["id"],
)
def test_closed_form_case(case):
    rows = run.run_case(case)
    assert rows
    bad = [(r.method, r.computed, r.reference) for r in rows if not r.ok]
    assert not bad
