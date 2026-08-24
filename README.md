# cts-triage

Compares two Android CTS `test_result.xml` reports and classifies what actually
changed.


**Status:** early. The plumbing works; the classification rules are being
written one at a time, each with its reasoning recorded in
[`DECISIONS.md`](DECISIONS.md).

---

## The problem

A raw pass/fail diff between two CTS runs is easy to produce and almost useless.
A full-ABI run generates thousands of deltas, and the overwhelming majority are
not regressions. Handing that list to an engineer means they spend their morning
doing what the tool should have done.

The useful question is not *what changed* but *what changed that a human needs
to look at*. Those are very different lists.

## Classification

| Category | Meaning |
|---|---|
| `NEW_FAILURE` | Passed in baseline, failed in candidate. **The list that matters.** |
| `NEW_PASS` | Failed in baseline, passed in candidate |
| `PERSISTENT_FAILURE` | Failed in both — known, not new |
| `NEW_TEST` | Only in candidate. **Not a regression.** |
| `REMOVED_TEST` | Only in baseline |
| `MODULE_INCOMPLETE` | Module did not finish — environment or configuration, not code |
| `FLAKY_SUSPECT` | Inconsistent within or across runs |
| `ABI_SPECIFIC` | Fails on one ABI, passes on another |
| `UNCLASSIFIED` | No rule matched. Deliberately visible rather than silently bucketed. |

### Three of these are the whole point

**`NEW_TEST` is not a regression.** Every CTS version bump adds test cases, and
a naive diff reports all of them as new failures. The first time this happens
people investigate; the second time they stop trusting the report. Separating
new tests from regressions is the difference between a tool that gets used and
one that gets ignored.

**`MODULE_INCOMPLETE` is not a test failure.** A module that never finished
tells you something about the device, the harness, or the environment. Counting
its tests as failures produces a large, alarming, and entirely misleading
number.

**`ABI_SPECIFIC` is a lead, not a category.** A test that fails on one ABI and
passes on another is pointing at something specific, usually in a native layer.
Surfacing it separately turns a needle-in-haystack into a starting point.

## Usage

```bash
python -m cts_triage baseline.xml candidate.xml
python -m cts_triage baseline.xml candidate.xml --format json
```

Exits non-zero when any `NEW_FAILURE` is present, so it can gate a pipeline
stage.

## Scope

CTS only. GTS and MTS are proprietary and deliberately out of scope; nothing in
this repository is derived from them.

Test fixtures are synthesized by `tools/make_fixtures.py`. No real CTS
artifacts, device data, or employer material is included. The report format is
public and documented in AOSP.

## On how this was built

The parsing, alignment, reporting and test scaffolding were built with heavy
LLM assistance. That layer is mechanical and there is no reason to write it by
hand.

**The classification taxonomy and the rules are mine**, and the reasoning behind
each one is in [`DECISIONS.md`](DECISIONS.md) — including, for each rule, the
conditions under which it gives the wrong answer.

That split is deliberate and it is the honest description of how the work was
done. The rules come from operating CTS, GTS and MTS through Tradefed and
Android Test Station across a device fleet; a language model has read a great
deal of code but has not spent five years deciding whether a given failure
should block a release.

## License

Apache-2.0.

