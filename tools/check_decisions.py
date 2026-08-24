#!/usr/bin/env python3
"""
Check that rules, scenarios and decision records have not drifted apart.

This is the honest version of "make the program read DECISIONS.md". It does not
generate code from prose — it verifies that every rule has a documented reason,
that every documented decision is actually implemented, and that every
classification the code can emit is specified somewhere a human agreed to.

Run it in CI. Documentation that is not checked stops being true.

    python tools/check_decisions.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "src" / "cts_triage" / "rules.py"
DECISIONS = ROOT / "DECISIONS.md"
FEATURE = ROOT / "tests" / "features" / "classification.feature"


def read(p: Path) -> str:
    if not p.exists():
        sys.exit(f"missing file: {p.relative_to(ROOT)}")
    return p.read_text(encoding="utf-8")


def main() -> int:
    rules_src = read(RULES)
    decisions_src = read(DECISIONS)
    feature_src = read(FEATURE)

    problems: list[str] = []

    # --- what the code declares ------------------------------------------
    enum_members = set(re.findall(r"^\s{4}([A-Z][A-Z_]+) = auto\(\)", rules_src, re.M))
    active_decisions = set(re.findall(r'^@rule\(priority=\d+, decision="(D\d+)"\)',
                                      rules_src, re.M))
    # decisions referenced only in commented-out decorators
    pending_decisions = set(re.findall(r'^# @rule\(priority=[^,]+, decision="(D\d+)"\)',
                                       rules_src, re.M))
    # decisions implemented by classify_modules() rather than by a @rule
    module_level = set(re.findall(r"See DECISIONS\.md (D\d+) and (D\d+)\.", rules_src))
    module_level = {d for pair in module_level for d in pair}

    # --- what the documents declare --------------------------------------
    documented = set(re.findall(r"^## (D\d+)[:\s\u2014]", decisions_src, re.M))
    specified = set(re.findall(r"classified as ([A-Z][A-Z_]+)", feature_src))
    specified |= set(re.findall(r"\|\s*([A-Z][A-Z_]+)\s*\|", feature_src))

    # --- 1. every active rule cites a decision that exists ----------------
    for d in sorted(active_decisions - documented):
        problems.append(f"rules.py implements {d}, but DECISIONS.md has no '## {d} —' entry")

    # --- 2. every documented decision is implemented or explicitly pending -
    for d in sorted(documented - active_decisions - pending_decisions - module_level):
        problems.append(f"DECISIONS.md documents {d}, but no rule cites it")

    # --- 3. every classification the code can emit is specified -----------
    # NO_RUNS and MODULE_INCOMPLETE are produced by classify_modules(), not by
    # a per-test rule, so they have no test-level scenario. UNCLASSIFIED is the
    # fallthrough and PASS is specified but trivially.
    exempt = {"UNCLASSIFIED", "UNCHANGED", "NO_RUNS"}
    for c in sorted(enum_members - specified - exempt):
        problems.append(
            f"Classification.{c} exists but no scenario in classification.feature "
            f"specifies when it is produced"
        )

    # --- 4. every 'when this is wrong' section is filled in ---------------
    for block in re.split(r"\n## ", decisions_src)[1:]:
        did = block.split(" ")[0]
        if did == "Template" or not did.startswith("D"):
            continue
        m = re.search(r"\*\*Wrong when:\*\*(.*?)(?=\n\* |\n## |\Z)", block, re.S)
        if not m:
            problems.append(f"{did} has no 'When this is wrong' section")
        elif len(m.group(1).strip()) < 40:
            problems.append(f"{did}: 'When this is wrong' is empty or too short to be real")

    # --- report -----------------------------------------------------------
    print(f"enum members ........ {len(enum_members)}")
    print(f"active rules ........ {len(active_decisions)}  {sorted(active_decisions)}")
    print(f"pending rules ....... {len(pending_decisions)}  {sorted(pending_decisions)}")
    print(f"module-level ........ {len(module_level)}  {sorted(module_level)}")
    print(f"decision records .... {len(documented)}  {sorted(documented)}")
    print()

    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("rules, scenarios and decision records are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
