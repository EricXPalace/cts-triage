#!/usr/bin/env python3
"""
Generate CTS-shaped test_result.xml fixtures.

Why this is scenario-driven rather than random: you cannot develop a
classification taxonomy against data that only exercises one branch of it.
Every rule needs a case that triggers it, and — more importantly — the rules
need cases where two of them both apply, so that precedence can be tested
rather than assumed.

Usage:
    python tools/make_fixtures.py                     # baseline + candidate
    python tools/make_fixtures.py --runs 3            # + a repeat of candidate
    python tools/make_fixtures.py --outdir tests/fixtures

NOTE ON REALISM: this emits the report shape documented in AOSP, but real CTS
output varies by report_version and by suite. Treat these fixtures as a way to
develop the rules, then validate the parser against a genuine run before
trusting it. The parser is written to tolerate unexpected elements precisely
because this generator is not authoritative.
"""

import argparse
import os
import random
from xml.sax.saxutils import escape

ABIS = ["arm64-v8a", "armeabi-v7a"]

# (module, abi, class, method, baseline, candidate) — results: pass | fail |
# IGNORED | ASSUMPTION_FAILURE | None (absent from that report)
#
# The trailing comment on each row names the classification it is meant to
# provoke. Rows marked CONFLICT deliberately satisfy two rules at once.
SCENARIOS = [
    # --- the boring majority: unchanged passes -------------------------------
    ("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testSetText",        "pass", "pass"),
    ("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testOnClick",        "pass", "pass"),
    ("CtsWidgetTestCases", "arm64-v8a", "TextViewTest", "testGravity",      "pass", "pass"),
    ("CtsWidgetTestCases", "armeabi-v7a", "ButtonTest", "testSetText",      "pass", "pass"),

    # --- NEW_FAILURE: passed, now fails --------------------------------------
    ("CtsWidgetTestCases", "arm64-v8a", "TextViewTest", "testSetTypeface",  "pass", "fail"),
    ("CtsMediaTestCases",  "arm64-v8a", "DecoderTest", "testHevcDecode",    "pass", "fail"),

    # --- NEW_PASS: was failing, now passes -----------------------------------
    ("CtsMediaTestCases",  "arm64-v8a", "DecoderTest", "testVp9Decode",     "fail", "pass"),

    # --- PERSISTENT_FAILURE: failing in both ---------------------------------
    ("CtsMediaTestCases",  "arm64-v8a", "EncoderTest", "testAacEncode",     "fail", "fail"),

    # --- NEW_TEST: candidate only (NOT a regression, even though it fails) ----
    ("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testAccessibility",   None,  "fail"),
    ("CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testTooltip",         None,  "pass"),

    # --- REMOVED_TEST: baseline only -----------------------------------------
    ("CtsWidgetTestCases", "arm64-v8a", "TextViewTest", "testDeprecatedApi", "pass", None),

    # --- ABI_SPECIFIC: fails on one ABI, passes on the other -----------------
    ("CtsNativeTestCases", "arm64-v8a",  "JniTest", "testPointerWidth",     "pass", "pass"),
    ("CtsNativeTestCases", "armeabi-v7a", "JniTest", "testPointerWidth",    "pass", "fail"),

    # --- non-pass results that are not failures ------------------------------
    ("CtsMediaTestCases",  "arm64-v8a", "DecoderTest", "testAv1Decode",     "IGNORED", "IGNORED"),
    ("CtsMediaTestCases",  "arm64-v8a", "EncoderTest", "testHwOnly", "ASSUMPTION_FAILURE", "ASSUMPTION_FAILURE"),

    # --- CONFLICT 1: inside a module that did not complete in the candidate.
    #     MODULE_INCOMPLETE vs NEW_FAILURE — which wins?
    ("CtsSecurityTestCases", "arm64-v8a", "SELinuxTest", "testPolicyLoaded", "pass", "fail"),
    ("CtsSecurityTestCases", "arm64-v8a", "SELinuxTest", "testDomainLabels", "pass", "fail"),

    # --- CONFLICT 2: candidate-only AND inside the incomplete module.
    #     NEW_TEST vs MODULE_INCOMPLETE — which wins?
    ("CtsSecurityTestCases", "arm64-v8a", "SELinuxTest", "testNewPolicyRule", None, "fail"),

    # --- FLAKY_SUSPECT: only detectable with a third report (see --runs).
    #     In a two-report comparison this is indistinguishable from a real
    #     regression, which is itself a finding worth writing down.
    ("CtsWidgetTestCases", "arm64-v8a", "ScrollViewTest", "testFling",      "pass", "fail"),
]

# module -> (done_in_baseline, done_in_candidate, reason_if_not_done)
MODULE_STATE = {
    "CtsSecurityTestCases": (True, False, "Device did not respond after 3 attempts"),
}

# tests whose result is re-rolled on each extra run, to create genuine
# inconsistency across repeats of the same build
UNSTABLE = {("CtsWidgetTestCases", "arm64-v8a", "ScrollViewTest", "testFling")}


def result_for(row, which, run_index, rng):
    """which: 0 = baseline, 1 = candidate. run_index > 1 = repeat of candidate."""
    _, _, _, _, base, cand = row
    r = base if which == 0 else cand
    if which == 1 and run_index > 1 and row[:4] in UNSTABLE:
        # Alternate deterministically rather than at random. A fixture whose
        # content depends on the seed is a fixture you cannot write an
        # assertion against — the same reason a flaky test is useless.
        r = "pass" if run_index % 2 == 0 else "fail"
    return r


def build_tree(which, run_index, rng):
    """-> {(module, abi): {class: [(method, result)]}}"""
    tree = {}
    for row in SCENARIOS:
        module, abi, klass, method = row[0], row[1], row[2], row[3]
        r = result_for(row, which, run_index, rng)
        if r is None:
            continue
        tree.setdefault((module, abi), {}).setdefault(klass, []).append((method, r))
    return tree


def render(tree, which, build_id, run_index):
    done_idx = 0 if which == 0 else 1
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>']
    out.append(
        '<Result start="1756000000000" end="1756003600000" '
        'suite_name="CTS" suite_version="15_r1" suite_plan="cts" '
        f'suite_build_number="{build_id}" report_version="5.0" '
        'command_line_args="run cts" devices="SYNTH0001" host_name="fixture">'
    )
    out.append(
        f'  <Build build_fingerprint="google/synth/synth:15/{build_id}/user-keys" '
        'build_device="synth" build_id="' + build_id + '" '
        'build_abis="arm64-v8a,armeabi-v7a" />'
    )

    total_pass = sum(
        1 for cls in tree.values() for lst in cls.values() for _, r in lst if r == "pass"
    )
    total_fail = sum(
        1 for cls in tree.values() for lst in cls.values() for _, r in lst if r == "fail"
    )
    modules_total = len(tree)
    modules_done = sum(
        1 for (m, _a) in tree if MODULE_STATE.get(m, (True, True, ""))[done_idx]
    )
    out.append(
        f'  <Summary pass="{total_pass}" failed="{total_fail}" '
        f'modules_done="{modules_done}" modules_total="{modules_total}" />'
    )

    for (module, abi), classes in sorted(tree.items()):
        st = MODULE_STATE.get(module, (True, True, ""))
        done = st[done_idx]
        n_pass = sum(1 for lst in classes.values() for _, r in lst if r == "pass")
        runtime = 30000 + 1000 * len(classes)
        out.append(
            f'  <Module name="{module}" abi="{abi}" device="SYNTH0001" '
            f'runtime="{runtime}" done="{str(done).lower()}" pass="{n_pass}">'
        )
        if not done and st[2]:
            out.append(f'    <Reason message="{escape(st[2])}" />')
        for klass, tests in sorted(classes.items()):
            out.append(f'    <TestCase name="android.cts.{klass}">')
            for method, r in sorted(tests):
                if r == "fail":
                    out.append(f'      <Test result="fail" name="{method}">')
                    out.append(
                        '        <Failure message="'
                        + escape(f"expected:&lt;true&gt; but was:&lt;false&gt; ({method})")
                        + '">'
                    )
                    out.append(
                        "          <StackTrace>junit.framework.AssertionFailedError\n"
                        f"\tat android.cts.{klass}.{method}(SourceFile:1)\n"
                        "\tat java.lang.reflect.Method.invoke(Native Method)</StackTrace>"
                    )
                    out.append("        </Failure>")
                    out.append("      </Test>")
                else:
                    out.append(f'      <Test result="{r}" name="{method}" />')
            out.append("    </TestCase>")
        out.append("  </Module>")
    out.append("</Result>")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="tests/fixtures")
    ap.add_argument("--runs", type=int, default=2,
                    help="2 = baseline + candidate. 3+ adds repeats of the "
                         "candidate build, which is the only way flakiness "
                         "becomes distinguishable from regression.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--truncated", action="store_true",
                    help="also emit truncated.xml, a half-written report, for "
                         "testing that the parser fails cleanly")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    os.makedirs(args.outdir, exist_ok=True)

    files = []
    base = render(build_tree(0, 1, rng), 0, "BP1A.240101.001", 1)
    files.append(("baseline.xml", base))
    for i in range(1, args.runs):
        tree = build_tree(1, i, rng)
        name = "candidate.xml" if i == 1 else f"candidate_run{i}.xml"
        files.append((name, render(tree, 1, "BP1A.240201.002", i)))

    for name, text in files:
        path = os.path.join(args.outdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {path}  ({len(text.splitlines())} lines)")

    if args.truncated:
        path = os.path.join(args.outdir, "truncated.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(base[: len(base) // 2])
        print(f"wrote {path}  (deliberately malformed)")

    print("\nscenarios by intended classification:")
    print("  NEW_FAILURE ........ 2   (+2 more inside the incomplete module)")
    print("  NEW_PASS ........... 1")
    print("  PERSISTENT_FAILURE . 1")
    print("  NEW_TEST ........... 2   (one of them inside the incomplete module)")
    print("  REMOVED_TEST ....... 1")
    print("  MODULE_INCOMPLETE .. 1 module, 3 tests")
    print("  ABI_SPECIFIC ....... 1 pair")
    print("  FLAKY_SUSPECT ...... 1   (needs --runs 3 to be separable)")
    print("  non-pass, non-fail .. IGNORED and ASSUMPTION_FAILURE")
    print("\ntwo of these deliberately satisfy two rules at once. That is the")
    print("point: precedence is a decision, not an accident.")


def create_cts_xml(
    suite_name: str = "CTS",
    suite_version: str = "15_r1",
    build_fingerprint: str = "google/synth/synth:15/BP1A.240101.001/user-keys",
    abis: list[str] | None = None,
    modules_spec: list[dict] | None = None,
    report_version: str = "5.0",
) -> str:
    """Helper function to synthesize XML for test cases."""
    if abis is None:
        abis = ["arm64-v8a", "armeabi-v7a"]

    if modules_spec is None:
        modules_spec = []
        for abi in abis:
            modules_spec.append(
                {
                    "name": "CtsWidgetTestCases",
                    "abi": abi,
                    "done": True,
                    "test_cases": [
                        {
                            "name": "android.widget.cts.ButtonTest",
                            "tests": [
                                {"name": "testButtonText", "result": "pass"},
                                {"name": "testButtonClick", "result": "pass"},
                            ],
                        }
                    ],
                }
            )

    import xml.etree.ElementTree as ET
    root = ET.Element(
        "Result",
        attrib={
            "suite_name": suite_name,
            "suite_version": suite_version,
            "suite_plan": "cts",
            "report_version": report_version,
            "start": "1756000000000",
            "end": "1756003600000",
        },
    )

    ET.SubElement(
        root,
        "Build",
        attrib={
            "build_fingerprint": build_fingerprint,
            "build_id": "BP1A.240101.001",
            "build_device": "synth",
        },
    )

    for mod_info in modules_spec:
        mod_elem = ET.SubElement(
            root,
            "Module",
            attrib={
                "name": mod_info.get("name", "unknown_module"),
                "abi": mod_info.get("abi", "arm64-v8a"),
                "done": "true" if mod_info.get("done", True) else "false",
            },
        )

        reason = mod_info.get("reason")
        if reason:
            reason_elem = ET.SubElement(mod_elem, "Reason")
            reason_elem.text = reason

        for tc_info in mod_info.get("test_cases", []):
            tc_elem = ET.SubElement(
                mod_elem,
                "TestCase",
                attrib={"name": tc_info.get("name", "unknown_class")},
            )
            for t_info in tc_info.get("tests", []):
                t_elem = ET.SubElement(
                    tc_elem,
                    "Test",
                    attrib={
                        "name": t_info.get("name", "unknown_method"),
                        "result": t_info.get("result", "pass"),
                    },
                )
                if t_info.get("result") in ("fail", "FAIL") or t_info.get("message") or t_info.get("stack_trace"):
                    fail_attribs = {}
                    if t_info.get("message"):
                        fail_attribs["message"] = t_info["message"]
                    fail_elem = ET.SubElement(t_elem, "Failure", attrib=fail_attribs)
                    if t_info.get("stack_trace"):
                        st_elem = ET.SubElement(fail_elem, "StackTrace")
                        st_elem.text = t_info["stack_trace"]

    xml_bytes = ET.tostring(root, encoding="utf-8")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes.decode("utf-8")


def write_cts_xml(filepath, **kwargs):
    from pathlib import Path
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    xml_str = create_cts_xml(**kwargs)
    path.write_text(xml_str, encoding="utf-8")
    return path


if __name__ == "__main__":
    main()

