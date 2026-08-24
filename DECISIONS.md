# Decisions

Why the triage queue is ordered the way it is, and what to do with each
category. Written from operating CTS/GTS/MTS on a physical device fleet.

Ordered by the sequence I actually work through a report — not by rule
precedence. For the cases where two categories both apply, see **Precedence**
at the bottom.

Each entry carries a **Wrong when** line. Those are the conditions under which
the rule gives the wrong answer. They are the part a passing test cannot
express, which is why they live here.

\---

## D1: MODULE\_INCOMPLETE

* **Priority:** blocker
* **Reason:** The module did not run to completion, so none of its results are reliable.
* **Action:** Re-run. Escalate only if the same module fails to complete repeatedly.
* **Wrong when:** The module was cut short *because* a test took the device down. Then it is a code problem and this label buries it. Read `<Reason>` before re-running blindly.

## D2: NEW\_FAILURE

* **Priority:** high
* **Reason:** Passed in the baseline, fails in the candidate. Could be a real regression, could be the bench.
* **Action:** Rule out the environment first, then retry before escalating:

  * Reset the phone
  * Reload the candidate files
  * Check whether a SIM is required; insert one if so
  * Check battery level — hold the retry until 20% or above
  * Check thermal — touch the phone, hold the retry until you can no longer feel the heat
* **Wrong when:** The checklist becomes a reflex and a genuine regression gets retried away. Watch the retry rate: if it climbs, the environment is not the story any more.

## D3: NO\_RUNS

* **Priority:** high
* **Reason:** An empty test module. 0 passed and 0 total is not a clean module.
* **Action:** Verify the suite is complete first, then re-download the xTS and run again. Report if it persists.
* **Wrong when:** The module legitimately has no applicable tests for this device or feature set. That is not a gap, and reporting it trains people to ignore this category.

## D4: NO\_BASELINE\_FAILURE

* **Priority:** high
* **Reason:** Fails in the candidate with no baseline result at all. Nothing in the data says how long it has been broken or how widely — and that absence is the reason to escalate.
* **Action:** Same procedure as D5, but file it above: a known failure with a ticket is a smaller unknown than a failure with no history.
* **Wrong when:** The test is new in this CTS version and covers a feature the device does not claim to support. Then the elevation is noise.

## D5: PERSISTENT\_FAILURE

* **Priority:** normal
* **Reason:** Fails in both reports. Known, not new.
* **Action:** Match against existing tickets before filing a new one.
* **Wrong when:** "Known" quietly becomes "ignored". A persistent failure that was never actually ticketed stays invisible here forever.

## D6: NEW\_TEST

* **Priority:** low
* **Reason:** Present only in the candidate, and it passed. Ordinary suite churn from a version bump.
* **Action:** None. Record it.
* **Wrong when:** A test was *renamed* rather than added. It then appears as one D8 plus one D6, and a real regression can hide in that pair.

## D7: NEW\_PASS

* **Priority:** low
* **Reason:** Previously failing, now passing. Usually means a fix landed.
* **Action:** Note the fix on the ticket if there is one.
* **Wrong when:** It passes because it was silently skipped or an assertion was weakened, not because anything was fixed.

## D8: REMOVED\_TEST

* **Priority:** low
* **Reason:** Baseline only. Usually suite churn.
* **Action:** Confirm it was not dropped by a configuration mistake. Follow D2's checklist if it looks like the bench rather than the suite.
* **Wrong when:** A whole slice of coverage disappears through a config error and each individual removal looks unremarkable. Watch the count, not the entries.

## D9: PASS

* **Priority:** none
* **Reason:** Passed in both. No surprise.
* **Action:** None.
* **Wrong when:** A test passes because it never really exercised anything. Not detectable from a result file.

## UNCLASSIFIED

* **Priority:** triage
* **Reason:** No rule matched. Currently this is where `IGNORED` and `ASSUMPTION\_FAILURE` land.
* **Action:** Triage by hand when it matters.
* **Wrong when:** It stops being read. This category is deliberately visible so that the tool never silently invents an opinion — but a bucket nobody opens is the same as no bucket.

\---

## Precedence

The order above is the order I read a report in. It is **not** the order the
rules run in. Precedence only matters where a single test satisfies two
categories at once, and there are three such cases.

**1. D1 beats everything inside that module.**
A test in an incomplete module may show `pass -> fail`, which also matches D2.
D1 wins. The module never finished, so we cannot tell which tests genuinely
failed and which simply never ran. Labelling them regressions produces a large,
alarming and misleading number.

**2. D4 beats D5.**
Both are failures needing the same procedure. D4 is filed higher because a
failure with no history is a larger unknown than a known failure that already
has a ticket.

**3. Candidate-only splits on result, not on novelty.**
A test present only in the candidate is D4 if it failed and D6 if it passed.
The distinction that matters is not whether the test is new — it is whether
anything is broken.

\---

## Out of scope

`ABI\_SPECIFIC`, `NEW\_IGNORE`, `NEW\_ASSUMPTION\_FAILURE` and `FLAKY\_SUSPECT` are
deliberately excluded.

The first three depend on firmware version and per-feature support, which
widens the input this tool would need. `FLAKY\_SUSPECT` is excluded for a harder
reason: **two reports cannot establish flakiness at all.** A flaky test and a
regression produce identical evidence — passed then, failed now. Separating
them needs the same build run more than once.

Guessing there would be worse than the current silence: a guess presented as a
classification invites people to dismiss real regressions as "probably flake".

