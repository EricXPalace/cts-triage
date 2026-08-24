from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from cts_triage.model import ModuleResult, TestReport, TestResult


@dataclass(frozen=True)
class TestRef:
    module: str


@dataclass(frozen=True)
class TestPair:
    """A pair of baseline and candidate test results for a single test identity."""

    __test__ = False

    key: Tuple[str, str, str, str]  # (module_name, abi, class_name, method_name)

    baseline: Optional[TestResult] = None
    candidate: Optional[TestResult] = None

    @property
    def ref(self) -> TestRef:
        return TestRef(module=self.module_name)

    @property
    def module_name(self) -> str:
        return self.key[0]

    @property
    def abi(self) -> str:
        return self.key[1]

    @property
    def class_name(self) -> str:
        return self.key[2]

    @property
    def method_name(self) -> str:
        return self.key[3]

    @property
    def is_baseline_only(self) -> bool:
        return self.baseline is not None and self.candidate is None

    @property
    def is_candidate_only(self) -> bool:
        return self.baseline is None and self.candidate is not None

    @property
    def is_present_in_both(self) -> bool:
        return self.baseline is not None and self.candidate is not None



@dataclass
class MetadataDiff:
    """Run-level metadata comparison between baseline and candidate reports."""

    baseline_fingerprint: Optional[str]
    candidate_fingerprint: Optional[str]
    baseline_suite_version: Optional[str]
    candidate_suite_version: Optional[str]
    baseline_abis: Set[str]
    candidate_abis: Set[str]

    @property
    def is_same_build(self) -> bool:
        if not self.baseline_fingerprint or not self.candidate_fingerprint:
            return False
        return self.baseline_fingerprint == self.candidate_fingerprint

    @property
    def is_same_suite_version(self) -> bool:
        if not self.baseline_suite_version or not self.candidate_suite_version:
            return False
        return self.baseline_suite_version == self.candidate_suite_version

    @property
    def added_abis(self) -> Set[str]:
        return self.candidate_abis - self.baseline_abis

    @property
    def removed_abis(self) -> Set[str]:
        return self.baseline_abis - self.candidate_abis


@dataclass
class RunComparison:
    """Complete alignment of two CTS test runs."""

    baseline_report: TestReport
    candidate_report: TestReport
    pairs: List[TestPair] = field(default_factory=list)
    pairs_by_key: Dict[Tuple[str, str, str, str], TestPair] = field(default_factory=dict)
    metadata_diff: Optional[MetadataDiff] = None

    def get_pair(
        self, module_name: str, abi: str, class_name: str, method_name: str
    ) -> Optional[TestPair]:
        key = (module_name, abi, class_name, method_name)
        return self.pairs_by_key.get(key)

    def get_module(self, report_type: str, module_name: str, abi: str) -> Optional[ModuleResult]:
        report = self.baseline_report if report_type == "baseline" else self.candidate_report
        for mod in report.modules:
            if mod.name == module_name and mod.abi == abi:
                return mod
        return None

    def find_cross_abi_pairs(self, module_name: str, class_name: str, method_name: str) -> List[TestPair]:
        """Find test pairs matching (module, class, method) across all ABIs."""
        results = []
        for pair in self.pairs:
            if (
                pair.module_name == module_name
                and pair.class_name == class_name
                and pair.method_name == method_name
            ):
                results.append(pair)
        return results


def align_reports(baseline: TestReport, candidate: TestReport) -> RunComparison:
    """Align baseline and candidate TestReport instances into a RunComparison."""
    baseline_map = baseline.tests_by_key()
    candidate_map = candidate.tests_by_key()

    all_keys = set(baseline_map.keys()) | set(candidate_map.keys())

    pairs: List[TestPair] = []
    pairs_by_key: Dict[Tuple[str, str, str, str], TestPair] = {}

    # Sort keys for deterministic output ordering
    for key in sorted(all_keys):
        b_test = baseline_map.get(key)
        c_test = candidate_map.get(key)
        pair = TestPair(key=key, baseline=b_test, candidate=c_test)
        pairs.append(pair)
        pairs_by_key[key] = pair

    meta_diff = MetadataDiff(
        baseline_fingerprint=baseline.build_fingerprint,
        candidate_fingerprint=candidate.build_fingerprint,
        baseline_suite_version=baseline.suite_version,
        candidate_suite_version=candidate.suite_version,
        baseline_abis=baseline.abis,
        candidate_abis=candidate.abis,
    )

    return RunComparison(
        baseline_report=baseline,
        candidate_report=candidate,
        pairs=pairs,
        pairs_by_key=pairs_by_key,
        metadata_diff=meta_diff,
    )


class RuleContext:
    """Context provided to classification rules during comparison evaluation."""

    def __init__(self, comparison: RunComparison):
        self.comparison = comparison

    @property
    def baseline_report(self) -> TestReport:
        return self.comparison.baseline_report

    @property
    def candidate_report(self) -> TestReport:
        return self.comparison.candidate_report

    @property
    def metadata_diff(self) -> Optional[MetadataDiff]:
        return self.comparison.metadata_diff

    def module_completed(self, module_name: str) -> bool:
        """Returns True if module completed (done=True) in candidate and baseline reports."""
        cand_mods = [m for m in self.candidate_report.modules if m.name == module_name]
        if cand_mods:
            for m in cand_mods:
                if not m.done:
                    return False
        base_mods = [m for m in self.baseline_report.modules if m.name == module_name]
        if base_mods:
            for m in base_mods:
                if not m.done:
                    return False
        return True

    def module_is_empty(self, module_name: str) -> bool:
        """Returns True if module produced no test results at all in candidate report."""
        cand_pairs = [p for p in self.comparison.pairs if p.module_name == module_name and p.candidate is not None]
        if cand_pairs:
            return False
        cand_mods = [m for m in self.candidate_report.modules if m.name == module_name]
        if not cand_mods:
            return True
        total_tests = sum(len(m.tests) for m in cand_mods)
        return total_tests == 0


