from pathlib import Path
import pytest

from cts_triage.parser import parse_xml, parse_xml_file
from tools.make_fixtures import create_cts_xml, write_cts_xml


def test_parse_valid_cts_xml():
    xml_str = create_cts_xml(
        suite_name="CTS",
        suite_version="14_r1",
        build_fingerprint="google/coral/coral:14/UP1A.231005.007:user/release-keys",
        modules_spec=[
            {
                "name": "CtsWidgetTestCases",
                "abi": "arm64-v8a",
                "done": True,
                "test_cases": [
                    {
                        "name": "android.widget.cts.ButtonTest",
                        "tests": [
                            {"name": "testText", "result": "pass"},
                            {
                                "name": "testClick",
                                "result": "fail",
                                "message": "AssertionError",
                                "stack_trace": "line1\nline2\nline3",
                            },
                        ],
                    }
                ],
            }
        ],
    )

    report = parse_xml(xml_str)
    assert report.suite_name == "CTS"
    assert report.suite_version == "14_r1"
    assert report.build_fingerprint == "google/coral/coral:14/UP1A.231005.007:user/release-keys"
    assert "arm64-v8a" in report.abis

    assert len(report.modules) == 1
    mod = report.modules[0]
    assert mod.name == "CtsWidgetTestCases"
    assert mod.abi == "arm64-v8a"
    assert mod.done is True

    all_tests = report.all_tests()
    assert len(all_tests) == 2

    t_fail = [t for t in all_tests if t.method_name == "testClick"][0]
    assert t_fail.result == "fail"
    assert t_fail.message == "AssertionError"
    assert "line1" in t_fail.stack_trace


def test_parse_unknown_schema_elements_and_missing_attributes():
    """Ensure parser defaults rest and never crashes on unexpected elements."""
    xml_str = """<?xml version="1.0" encoding="UTF-8"?>
    <Result unknown_top_attr="hello" report_version="99.0">
      <CustomElement foo="bar">
        <NestedData>123</NestedData>
      </CustomElement>
      <Module name="CtsUnknownModule" abi="x86">
        <TestCase name="com.example.Test">
          <Test name="testFoo" result="ASSUMPTION_FAILURE" custom_attr="baz" />
        </TestCase>
      </Module>
    </Result>
    """
    report = parse_xml(xml_str)
    assert report.report_version == "99.0"
    assert report.attributes.get("unknown_top_attr") == "hello"
    assert len(report.modules) == 1
    mod = report.modules[0]
    assert mod.name == "CtsUnknownModule"
    assert mod.abi == "x86"
    assert len(mod.tests) == 1
    assert mod.tests[0].result == "ASSUMPTION_FAILURE"


def test_parse_module_incomplete_and_reason():
    xml_str = create_cts_xml(
        modules_spec=[
            {
                "name": "CtsIncompleteModule",
                "abi": "arm64-v8a",
                "done": False,
                "reason": "Device crash during test execution",
                "test_cases": [],
            }
        ]
    )
    report = parse_xml(xml_str)
    assert len(report.modules) == 1
    mod = report.modules[0]
    assert mod.done is False
    assert mod.reason == "Device crash during test execution"


def test_stack_trace_truncation():
    long_stack = "\n".join([f"at com.example.Class.method_{i}(File.java:{i})" for i in range(50)])
    xml_str = create_cts_xml(
        modules_spec=[
            {
                "name": "CtsTest",
                "abi": "arm64-v8a",
                "test_cases": [
                    {
                        "name": "TestClass",
                        "tests": [
                            {
                                "name": "testStack",
                                "result": "fail",
                                "stack_trace": long_stack,
                            }
                        ],
                    }
                ],
            }
        ]
    )
    report = parse_xml(xml_str, max_stack_lines=10)
    test = report.all_tests()[0]
    lines = test.stack_trace.splitlines()
    # 10 lines + 1 truncation summary line
    assert len(lines) == 11
    assert "truncated" in lines[-1]


def test_truncated_xml_survives_without_traceback(tmp_path: Path):
    truncated_xml = (
        '<?xml version="1.0"?>'
        '<Result suite_name="CTS">'
        '<Module name="CtsAudioTestCases" abi="arm64-v8a" done="true">'
        '<TestCase name="AudioTest">'
        '<Test name="testAudio" result="pass">'
    )
    filepath = tmp_path / "truncated.xml"
    filepath.write_text(truncated_xml, encoding="utf-8")

    # Must survive and return a TestReport without raising an unhandled exception
    report = parse_xml_file(filepath)
    assert isinstance(report, type(parse_xml_file(filepath)))
    assert report.raw_metadata.get("truncated") == "true"
