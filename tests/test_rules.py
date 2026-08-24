import pytest

from cts_triage.align import RuleContext, RunComparison, TestPair
from cts_triage.model import ModuleResult, TestReport, TestResult
from cts_triage.rules import Classification, classify


def test_classification_enum_members():
    """Verify Classification enum members match the user's operational taxonomy."""
    expected_members = {
        "MODULE_INCOMPLETE",
        "NO_RUNS",
        "NEW_FAILURE",
        "NO_BASELINE_FAILURE",
        "PERSISTENT_FAILURE",
        "NEW_TEST",
        "NEW_PASS",
        "REMOVED_TEST",
        "PASS",
        "UNCLASSIFIED",
    }
    actual_members = {m.name for m in Classification}
    assert actual_members == expected_members, f"Enum members mismatch: {actual_members}"


def test_user_classification_rules():
    """Test classification outcomes produced by user's rules in rules.py."""
    # 1. REMOVED_TEST (baseline only)
    p_removed = TestPair(
        key=("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testRemoved"),
        baseline=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testRemoved", "pass"),
        candidate=None,
    )

    # 2. NEW_FAILURE (pass -> fail)
    p_new_fail = TestPair(
        key=("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testNewFail"),
        baseline=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testNewFail", "pass"),
        candidate=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testNewFail", "fail"),
    )

    # 3. PERSISTENT_FAILURE (fail -> fail)
    p_persistent = TestPair(
        key=("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testPersistent"),
        baseline=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testPersistent", "fail"),
        candidate=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testPersistent", "fail"),
    )

    # 4. NEW_PASS (fail -> pass)
    p_new_pass = TestPair(
        key=("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testNewPass"),
        baseline=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testNewPass", "fail"),
        candidate=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testNewPass", "pass"),
    )

    # 5. PASS (pass -> pass)
    p_pass = TestPair(
        key=("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testPass"),
        baseline=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testPass", "pass"),
        candidate=TestResult("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testPass", "pass"),
    )

    comp = RunComparison(
        baseline_report=TestReport(modules=[ModuleResult(name="CtsWidgetTestCases", abi="arm64-v8a", done=True)]),
        candidate_report=TestReport(modules=[ModuleResult(name="CtsWidgetTestCases", abi="arm64-v8a", done=True)]),
        pairs=[p_removed, p_new_fail, p_persistent, p_new_pass, p_pass],
    )
    ctx = RuleContext(comp)

    assert classify(p_removed, ctx) == Classification.REMOVED_TEST
    assert classify(p_new_fail, ctx) == Classification.NEW_FAILURE
    assert classify(p_persistent, ctx) == Classification.PERSISTENT_FAILURE
    assert classify(p_new_pass, ctx) == Classification.NEW_PASS
    assert classify(p_pass, ctx) == Classification.PASS

