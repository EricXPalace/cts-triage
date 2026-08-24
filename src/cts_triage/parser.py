import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from cts_triage.model import ModuleResult, TestReport, TestResult


def _parse_bool(val: Optional[str], default: bool = True) -> bool:
    """Parse boolean attribute string defensively."""
    if val is None:
        return default
    val_str = str(val).strip().lower()
    if val_str in ("false", "0", "no", "f"):
        return False
    if val_str in ("true", "1", "yes", "t"):
        return True
    return default


def parse_xml_file(
    filepath: Union[str, Path], max_stack_lines: int = 20
) -> TestReport:
    """Parse a CTS test_result.xml file defensively into a TestReport.

    Survives truncated or malformed XML without raising an unhandled exception traceback.
    """
    path = Path(filepath)
    if not path.is_file():
        report = TestReport(max_stack_lines=max_stack_lines)
        report.raw_metadata["error"] = f"File not found: {path}"
        return report

    try:
        content = path.read_bytes()
    except Exception as e:
        report = TestReport()
        report.raw_metadata["error"] = f"Failed to read file: {e}"
        return report

    return parse_xml(content, max_stack_lines=max_stack_lines)


def parse_xml(
    source: Union[str, bytes], max_stack_lines: int = 20
) -> TestReport:
    """Parse XML string or bytes defensively into a TestReport."""
    if isinstance(source, str):
        content_bytes = source.encode("utf-8", errors="replace")
    else:
        content_bytes = source

    report = TestReport()
    modules: List[ModuleResult] = []
    abis: Set[str] = set()

    # Try full tree parsing first; if truncated, fallback to incremental iterparse
    root: Optional[ET.Element] = None
    is_truncated = False

    try:
        root = ET.fromstring(content_bytes)
    except ET.ParseError:
        is_truncated = True
        # Try wrapping or recovering if possible, or parse line-by-line via iterparse
        try:
            # Wrap incomplete XML in root tag if missing closing tag
            wrapped = content_bytes + b"\n</Result>"
            root = ET.fromstring(wrapped)
        except ET.ParseError:
            # Fall back to defensive chunk / stream parser
            root = None

    if root is not None:
        _parse_root_element(root, report, modules, abis, max_stack_lines)
    else:
        # Emergency recovery using iterparse on byte stream
        _parse_stream_defensively(content_bytes, report, modules, abis, max_stack_lines)
        is_truncated = True

    if is_truncated:
        report.raw_metadata["truncated"] = "true"

    report.modules = modules
    report.abis = abis
    return report


def _parse_root_element(
    root: ET.Element,
    report: TestReport,
    modules: List[ModuleResult],
    abis: Set[str],
    max_stack_lines: int,
) -> None:
    """Extract metadata, modules, test cases, and tests from parsed root Element."""
    # Top-level attributes
    for key, val in root.attrib.items():
        report.attributes[key] = val

    report.suite_name = root.attrib.get("suite_name") or root.attrib.get("suite_plan")
    report.suite_version = root.attrib.get("suite_version")
    report.suite_build = root.attrib.get("suite_build")
    report.start_time = root.attrib.get("start") or root.attrib.get("start_time")
    report.end_time = root.attrib.get("end") or root.attrib.get("end_time")
    report.report_version = root.attrib.get("report_version")

    # Build fingerprint lookup from root attributes or <Build> child element
    if "build_fingerprint" in root.attrib:
        report.build_fingerprint = root.attrib["build_fingerprint"]

    build_elem = root.find("Build")
    if build_elem is not None:
        for k, v in build_elem.attrib.items():
            report.attributes[f"build_{k}"] = v
        if not report.build_fingerprint:
            report.build_fingerprint = (
                build_elem.attrib.get("build_fingerprint")
                or build_elem.attrib.get("fingerprint")
            )

    # Process modules
    for mod_elem in root.findall(".//Module"):
        mod_result = _parse_module_element(mod_elem, max_stack_lines)
        if mod_result:
            modules.append(mod_result)
            if mod_result.abi:
                abis.add(mod_result.abi)


def _parse_module_element(mod_elem: ET.Element, max_stack_lines: int) -> Optional[ModuleResult]:
    """Parse a <Module> element."""
    mod_name = mod_elem.attrib.get("name") or mod_elem.attrib.get("module_name") or "unknown_module"
    abi = mod_elem.attrib.get("abi") or "unknown_abi"
    done = _parse_bool(mod_elem.attrib.get("done"), default=True)

    # Reason element/attribute
    reason: Optional[str] = mod_elem.attrib.get("reason")
    reason_elem = mod_elem.find("Reason")
    if reason_elem is not None and reason_elem.text:
        reason = reason_elem.text.strip()

    mod_attrs = dict(mod_elem.attrib)
    tests: List[TestResult] = []

    # Parse TestCases inside Module
    for tc_elem in mod_elem.findall("TestCase"):
        class_name = tc_elem.attrib.get("name") or "unknown_class"
        for t_elem in tc_elem.findall("Test"):
            method_name = t_elem.attrib.get("name") or "unknown_method"
            result_str = (
                t_elem.attrib.get("result")
                or t_elem.attrib.get("status")
                or "unknown"
            )

            msg: Optional[str] = None
            stack_trace: Optional[str] = None

            fail_elem = t_elem.find("Failure")
            if fail_elem is not None:
                msg = fail_elem.attrib.get("message")
                st_elem = fail_elem.find("StackTrace")
                if st_elem is not None and st_elem.text:
                    stack_trace = st_elem.text.strip()
                elif fail_elem.text and fail_elem.text.strip():
                    if not stack_trace:
                        stack_trace = fail_elem.text.strip()

            test_res = TestResult(
                module_name=mod_name,
                abi=abi,
                class_name=class_name,
                method_name=method_name,
                result=result_str,
                message=msg,
                stack_trace=stack_trace,
                max_stack_lines=max_stack_lines,
            )
            tests.append(test_res)

    return ModuleResult(
        name=mod_name,
        abi=abi,
        done=done,
        reason=reason,
        tests=tests,
        attributes=mod_attrs,
    )


def _parse_stream_defensively(
    content_bytes: bytes,
    report: TestReport,
    modules: List[ModuleResult],
    abis: Set[str],
    max_stack_lines: int,
) -> None:
    """Fallback stream parser using iterparse to salvage elements up to point of truncation."""
    import io

    stream = io.BytesIO(content_bytes)
    current_module_elem: Optional[ET.Element] = None

    try:
        for event, elem in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                if elem.tag == "Result" and not report.attributes:
                    for k, v in elem.attrib.items():
                        report.attributes[k] = v
                    report.suite_name = elem.attrib.get("suite_name")
                    report.suite_version = elem.attrib.get("suite_version")
                    report.build_fingerprint = elem.attrib.get("build_fingerprint")
            elif event == "end":
                if elem.tag == "Module":
                    mod_res = _parse_module_element(elem, max_stack_lines)
                    if mod_res:
                        modules.append(mod_res)
                        if mod_res.abi:
                            abis.add(mod_res.abi)
                    elem.clear()
    except ET.ParseError:
        # Ignore ParseError at truncation point, keep whatever modules were parsed
        pass
