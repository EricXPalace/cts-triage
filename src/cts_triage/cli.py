import argparse
import sys
from pathlib import Path

from cts_triage.align import align_reports
from cts_triage.parser import parse_xml_file
from cts_triage.report import (
    format_json_report,
    format_text_report,
    generate_classification_map,
)
from cts_triage.rules import Classification


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two Android CTS test_result.xml reports and classify changes."
    )
    parser.add_argument("baseline", help="Path to baseline test_result.xml")
    parser.add_argument("candidate", help="Path to candidate test_result.xml")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    candidate_path = Path(args.candidate)

    if not baseline_path.exists():
        print(f"Error: Baseline file does not exist: {baseline_path}", file=sys.stderr)
        sys.exit(2)

    if not candidate_path.exists():
        print(f"Error: Candidate file does not exist: {candidate_path}", file=sys.stderr)
        sys.exit(2)

    baseline_report = parse_xml_file(baseline_path)
    candidate_report = parse_xml_file(candidate_path)

    comparison = align_reports(baseline_report, candidate_report)
    class_map = generate_classification_map(comparison)

    if args.format == "json":
        output = format_json_report(comparison, class_map)
    else:
        output = format_text_report(comparison, class_map)

    print(output)

    # Exit non-zero when any NEW_FAILURE is present
    has_new_failure = any(
        cat == Classification.NEW_FAILURE for cat in class_map.values()
    )
    if has_new_failure:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
