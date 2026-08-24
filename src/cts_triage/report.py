import json
from typing import Dict, List, Optional

from cts_triage.align import RuleContext, RunComparison, TestPair
from cts_triage.rules import (
    ACTIONS,
    PRIORITY_HINT,
    REPORT_ORDER,
    Classification,
    classify,
)

CATEGORY_DISPLAY_ORDER: List[Classification] = REPORT_ORDER


def generate_classification_map(
    comparison: RunComparison,
) -> Dict[TestPair, Classification]:
    """Classifies all test pairs in comparison."""
    context = RuleContext(comparison)
    result = {}
    for pair in comparison.pairs:
        result[pair] = classify(pair, context)
    return result


def format_text_report(
    comparison: RunComparison,
    class_map: Dict[TestPair, Classification],
) -> str:
    """Format human-readable text report, prioritized by attention level."""
    try:
        from rich.console import Console
        from rich.table import Table
        import io

        string_io = io.StringIO()
        console = Console(file=string_io, force_terminal=False, color_system=None)

        console.print("[bold]CTS Triage Report[/bold]")
        console.print("=" * 60)

        meta = comparison.metadata_diff
        if meta:
            console.print(f"Baseline Build:  {meta.baseline_fingerprint or 'N/A'}")
            console.print(f"Candidate Build: {meta.candidate_fingerprint or 'N/A'}")
            console.print(f"Same Build:      {meta.is_same_build}")
            console.print(
                f"Baseline ABIs:   {', '.join(sorted(meta.baseline_abis)) or 'N/A'}"
            )
            console.print(
                f"Candidate ABIs:  {', '.join(sorted(meta.candidate_abis)) or 'N/A'}"
            )
        console.print("-" * 60)

        # Summary Table
        counts: Dict[Classification, int] = {cat: 0 for cat in CATEGORY_DISPLAY_ORDER}
        grouped: Dict[Classification, List[TestPair]] = {
            cat: [] for cat in CATEGORY_DISPLAY_ORDER
        }

        for pair, cat in class_map.items():
            counts[cat] = counts.get(cat, 0) + 1
            grouped.setdefault(cat, []).append(pair)

        summary_table = Table(title="Classification Summary", show_header=True)
        summary_table.add_column("Category", style="cyan")
        summary_table.add_column("Priority", style="yellow")
        summary_table.add_column("Count", justify="right", style="bold")

        for cat in CATEGORY_DISPLAY_ORDER:
            cnt = counts[cat]
            prio = PRIORITY_HINT.get(cat, "")
            summary_table.add_row(cat.name, prio, str(cnt))

        console.print(summary_table)
        console.print("-" * 60)

        # Detail sections for categories with > 0 items
        for cat in CATEGORY_DISPLAY_ORDER:
            pairs = grouped.get(cat, [])
            if not pairs:
                continue

            action_desc = ACTIONS.get(cat, "")
            action_suffix = f"\n  [italic]Action: {action_desc}[/italic]" if action_desc else ""
            console.print(
                f"\n[bold underline]{cat.name}[/bold underline] ({len(pairs)}):{action_suffix}"
            )
            for pair in pairs:
                b_res = pair.baseline.result if pair.baseline else "MISSING"
                c_res = pair.candidate.result if pair.candidate else "MISSING"
                msg_str = ""
                if pair.candidate and pair.candidate.message:
                    msg_str = f" - Reason: {pair.candidate.message}"
                elif pair.baseline and pair.baseline.message:
                    msg_str = f" - Reason: {pair.baseline.message}"

                console.print(
                    f"  [{pair.abi}] {pair.module_name} -> {pair.class_name}#{pair.method_name}"
                    f" ({b_res} -> {c_res}){msg_str}"
                )

        return string_io.getvalue()

    except ImportError:
        # Standard library fallback if rich is not available
        lines = []
        lines.append("CTS Triage Report")
        lines.append("=" * 60)

        meta = comparison.metadata_diff
        if meta:
            lines.append(f"Baseline Build:  {meta.baseline_fingerprint or 'N/A'}")
            lines.append(f"Candidate Build: {meta.candidate_fingerprint or 'N/A'}")
            lines.append(f"Same Build:      {meta.is_same_build}")
            lines.append(f"Baseline ABIs:   {', '.join(sorted(meta.baseline_abis)) or 'N/A'}")
            lines.append(f"Candidate ABIs:  {', '.join(sorted(meta.candidate_abis)) or 'N/A'}")
        lines.append("-" * 60)

        counts: Dict[Classification, int] = {cat: 0 for cat in CATEGORY_DISPLAY_ORDER}
        grouped: Dict[Classification, List[TestPair]] = {
            cat: [] for cat in CATEGORY_DISPLAY_ORDER
        }

        for pair, cat in class_map.items():
            counts[cat] = counts.get(cat, 0) + 1
            grouped.setdefault(cat, []).append(pair)

        lines.append("Classification Summary:")
        for cat in CATEGORY_DISPLAY_ORDER:
            prio = PRIORITY_HINT.get(cat, "")
            lines.append(f"  {cat.name:22s} [{prio:7s}]: {counts[cat]}")
        lines.append("-" * 60)

        for cat in CATEGORY_DISPLAY_ORDER:
            pairs = grouped.get(cat, [])
            if not pairs:
                continue
            action_desc = ACTIONS.get(cat, "")
            action_suffix = f"\n  Action: {action_desc}" if action_desc else ""
            lines.append(f"\n{cat.name} ({len(pairs)}):{action_suffix}")
            for pair in pairs:
                b_res = pair.baseline.result if pair.baseline else "MISSING"
                c_res = pair.candidate.result if pair.candidate else "MISSING"
                msg_str = ""
                if pair.candidate and pair.candidate.message:
                    msg_str = f" - Reason: {pair.candidate.message}"
                elif pair.baseline and pair.baseline.message:
                    msg_str = f" - Reason: {pair.baseline.message}"

                lines.append(
                    f"  [{pair.abi}] {pair.module_name} -> {pair.class_name}#{pair.method_name}"
                    f" ({b_res} -> {c_res}){msg_str}"
                )

        return "\n".join(lines)


def format_json_report(
    comparison: RunComparison,
    class_map: Dict[TestPair, Classification],
) -> str:
    """Format machine-readable JSON report."""
    counts = {cat.name: 0 for cat in CATEGORY_DISPLAY_ORDER}
    classifications_output: Dict[str, List[dict]] = {
        cat.name: [] for cat in CATEGORY_DISPLAY_ORDER
    }

    for pair, cat in class_map.items():
        counts[cat.name] = counts.get(cat.name, 0) + 1
        entry = {
            "module_name": pair.module_name,
            "abi": pair.abi,
            "class_name": pair.class_name,
            "method_name": pair.method_name,
            "baseline_result": pair.baseline.result if pair.baseline else None,
            "candidate_result": pair.candidate.result if pair.candidate else None,
            "message": (
                pair.candidate.message
                if pair.candidate
                else (pair.baseline.message if pair.baseline else None)
            ),
        }
        classifications_output[cat.name].append(entry)

    meta = comparison.metadata_diff
    meta_dict = {}
    if meta:
        meta_dict = {
            "baseline_fingerprint": meta.baseline_fingerprint,
            "candidate_fingerprint": meta.candidate_fingerprint,
            "baseline_suite_version": meta.baseline_suite_version,
            "candidate_suite_version": meta.candidate_suite_version,
            "baseline_abis": sorted(list(meta.baseline_abis)),
            "candidate_abis": sorted(list(meta.candidate_abis)),
            "is_same_build": meta.is_same_build,
        }

    report_data = {
        "summary": {
            "total_pairs": len(comparison.pairs),
            "counts": counts,
            "metadata_diff": meta_dict,
            "actions": {cat.name: ACTIONS.get(cat, "") for cat in CATEGORY_DISPLAY_ORDER},
            "priority_hints": {cat.name: PRIORITY_HINT.get(cat, "") for cat in CATEGORY_DISPLAY_ORDER},
        },
        "classifications": classifications_output,
    }

    return json.dumps(report_data, indent=2)

