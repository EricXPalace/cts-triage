"""
Classification rules — the taxonomy is operational, not academic.

These categories come from how a CTS run is actually triaged on a device fleet:
each one is defined by what you do about it, not merely by what the data says.
That mapping lives in ACTIONS at the bottom of this file, and it is the part of
this tool that could not have been derived from the report format alone.

TWO ORDERINGS, DELIBERATELY SEPARATE
------------------------------------
`priority`     decides which label wins when one test satisfies two rules.
`REPORT_ORDER` decides what a human reads first.

These are different questions, and conflating them is a bug. NO_RUNS and
NEW_FAILURE can never both apply to the same test, so their relative priority
is meaningless — but their relative position in the report matters a lot.

Only two genuine precedence conflicts exist in this taxonomy. Both are
documented in DECISIONS.md.

WHAT TWO REPORTS CANNOT TELL YOU
--------------------------------
  NO_RUNS             "module produced nothing" is visible. "was on the test
                      plan and never ran at all" needs the plan as a third
                      input, which this tool does not yet take.
  PERSISTENT_FAILURE  operationally means "still failing after three retries
                      and an environment reset". The reports carry no retry
                      count, so what is computed here is the weaker claim
                      "failing in both".

Both gaps are labelled rather than papered over.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable


class Classification(Enum):
    MODULE_INCOMPLETE = auto()
    NO_RUNS = auto()
    NEW_FAILURE = auto()
    NO_BASELINE_FAILURE = auto()
    PERSISTENT_FAILURE = auto()
    NEW_TEST = auto()
    NEW_PASS = auto()
    REMOVED_TEST = auto()
    PASS = auto()
    UNCLASSIFIED = auto()


# The order a human works through the report. Not rule priority.
REPORT_ORDER = [
    Classification.MODULE_INCOMPLETE,
    Classification.NEW_FAILURE,
    Classification.NO_RUNS,
    Classification.NO_BASELINE_FAILURE,
    Classification.PERSISTENT_FAILURE,
    Classification.NEW_TEST,
    Classification.NEW_PASS,
    Classification.REMOVED_TEST,
    Classification.PASS,
    Classification.UNCLASSIFIED,
]


# --- registry ---------------------------------------------------------------

_RULES: list[tuple[int, str, Callable]] = []


def rule(priority: int, decision: str):
    """Register a rule. `decision` names the DECISIONS.md entries behind it
    (comma-separated when one rule can emit more than one classification)."""
    def wrap(fn):
        _RULES.append((priority, decision, fn))
        _RULES.sort(key=lambda r: -r[0])
        return fn
    return wrap


def classify(pair, ctx) -> Classification:
    """Classify one test. Runs rules highest priority first; first match wins."""
    for _p, _d, fn in _RULES:
        result = fn(pair, ctx)
        if result is not None:
            return result
    return Classification.UNCLASSIFIED


def classify_modules(ctx) -> dict[str, Classification]:
    """Module-level findings — a separate pass, on purpose.

    NO_RUNS cannot be expressed as a per-test rule. A module that produced no
    results has no tests to attach the label to, so a rule of the form
    `classify(pair, ctx)` can never fire for it: if a pair exists the module is
    not empty, and if no pair exists nothing calls the rule. The two findings
    below are properties of the module, not of any test inside it.

    MODULE_INCOMPLETE appears here *and* as a test-level rule. That is
    deliberate: the module needs re-running (this function), and its individual
    results need suppressing (the rule). Same finding, two consumers.

    See DECISIONS.md D1 and D3.
    """
    out: dict[str, Classification] = {}
    for module in ctx.all_modules():
        if ctx.module_is_empty(module):
            out[module] = Classification.NO_RUNS
        elif not ctx.module_completed(module):
            out[module] = Classification.MODULE_INCOMPLETE
    return out


# ===========================================================================
# RULES
#
# One rule per classification, one classification per DECISIONS.md entry.
# `decision=` is not used at runtime; tools/check_decisions.py uses it to
# verify that no rule exists without a documented reason and vice versa.
# ===========================================================================

@rule(priority=100, decision="D1")
def module_incomplete(pair, ctx):
    """Beats everything inside that module. See DECISIONS.md Precedence 1."""
    if not ctx.module_completed(pair.ref.module):
        return Classification.MODULE_INCOMPLETE
    return None


@rule(priority=80, decision="D4")
def no_baseline_failure(pair, ctx):
    """Candidate-only and failing: a failure with no history.

    Above D5 on purpose. See DECISIONS.md Precedence 2 and 3.
    """
    if pair.baseline is None and pair.candidate == "fail":
        return Classification.NO_BASELINE_FAILURE
    return None


@rule(priority=80, decision="D6")
def new_test(pair, ctx):
    """Candidate-only and passing: ordinary suite churn."""
    if pair.baseline is None and pair.candidate == "pass":
        return Classification.NEW_TEST
    return None


@rule(priority=80, decision="D8")
def removed_test(pair, ctx):
    if pair.candidate is None and pair.baseline is not None:
        return Classification.REMOVED_TEST
    return None


@rule(priority=60, decision="D2")
def new_failure(pair, ctx):
    if pair.baseline == "pass" and pair.candidate == "fail":
        return Classification.NEW_FAILURE
    return None


@rule(priority=60, decision="D5")
def persistent_failure(pair, ctx):
    """Failing in both.

    Operationally this means 'still failing after three retries and an
    environment reset'. The reports carry no retry count, so what is computed
    here is the weaker claim.
    """
    if pair.baseline == "fail" and pair.candidate == "fail":
        return Classification.PERSISTENT_FAILURE
    return None


@rule(priority=60, decision="D7")
def new_pass(pair, ctx):
    if pair.baseline == "fail" and pair.candidate == "pass":
        return Classification.NEW_PASS
    return None


@rule(priority=50, decision="D9")
def passed(pair, ctx):
    if pair.baseline == "pass" and pair.candidate == "pass":
        return Classification.PASS
    return None


# ===========================================================================
# OUT OF SCOPE FOR v1 — recorded so the omission stays visible
# ===========================================================================
#
#   ABI_SPECIFIC            fails on one ABI, passes on another
#   NEW_IGNORE              pass -> IGNORED
#   NEW_ASSUMPTION_FAILURE  pass -> ASSUMPTION_FAILURE
#   FLAKY_SUSPECT           not determinable from two reports at all
#
# The first three depend on firmware version and per-feature support, which
# widens the input this tool would need. The fourth needs repeated runs of the
# same build. Excluded on purpose; see the 'Out of scope for v1' section of DECISIONS.md.
#
# Until then, IGNORED and ASSUMPTION_FAILURE results fall through to
# UNCLASSIFIED. That is the honest outcome: the tool has no opinion, and says so
# rather than guessing.


# ===========================================================================
# ACTIONS — what each classification means you should do next
# ===========================================================================

ACTIONS = {
    Classification.MODULE_INCOMPLETE:
        "Re-run the module. Do not investigate individual results until it completes.",
    Classification.NEW_FAILURE:
        "Check for a known environment or device condition first (SIM seated, "
        "RF fixture aligned, storage, thermal). Reset, match the expected "
        "condition, then retry before escalating.",
    Classification.NO_RUNS:
        "Report the gap. A module that produced nothing is not a passing module.",
    Classification.NO_BASELINE_FAILURE:
        "Same procedure as PERSISTENT_FAILURE — environment reset, retry, then "
        "match against existing tickets. File it higher: there is no baseline, "
        "so neither the age nor the breadth of this failure is known.",
    Classification.PERSISTENT_FAILURE:
        "Still failing after retries. Match against existing tickets before "
        "filing a new one.",
    Classification.NEW_TEST:
        "New test item. Record the result; it is not a regression.",
    Classification.NEW_PASS:
        "Previously failing, now passing. Confirm nothing was silently skipped.",
    Classification.REMOVED_TEST:
        "Baseline only. Usually suite churn; confirm it was not dropped by a "
        "configuration mistake.",
    Classification.PASS:
        "No action.",
    Classification.UNCLASSIFIED:
        "No rule matched. Visible on purpose rather than silently bucketed.",
}


# ===========================================================================
# TICKET FIELDS
# ===========================================================================
#
# ISTQB draws a line worth keeping here: severity is the degree of technical
# impact, priority is how urgently it should be fixed. They come apart — a
# misspelt logo is low severity and high priority.
#
# NO_BASELINE_FAILURE is filed above PERSISTENT_FAILURE because we do not know
# how old or how wide the failure is. Strictly, that is an argument about
# PRIORITY: absence of history makes it urgent to look at, but says nothing
# about impact, which has not been measured yet. Asserting high severity would
# be claiming an impact nobody has established.
#
# TODO(human): decide whether the elevation belongs in severity, priority, or
# both, and record it in DECISIONS.md. What goes in the ticket depends on
# the answer.

PRIORITY_HINT = {
    Classification.MODULE_INCOMPLETE:   "blocker",   # nothing downstream is trustworthy
    Classification.NO_RUNS:             "high",
    Classification.NEW_FAILURE:         "high",
    Classification.NO_BASELINE_FAILURE: "high",      # unknown age, unknown breadth
    Classification.PERSISTENT_FAILURE:  "normal",    # known, usually already ticketed
    Classification.NEW_TEST:            "low",
    Classification.NEW_PASS:            "low",
    Classification.REMOVED_TEST:        "low",
    Classification.PASS:                "none",
    Classification.UNCLASSIFIED:        "triage",
}
