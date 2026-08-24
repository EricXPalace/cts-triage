from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


def truncate_stack_trace(stack_trace: Optional[str], max_lines: int = 20) -> Optional[str]:
    """Truncate stack trace string to at most max_lines."""
    if not stack_trace:
        return stack_trace
    lines = stack_trace.strip().splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines]) + f"\n... [{len(lines) - max_lines} lines truncated]"


@dataclass(frozen=True)
class TestKey:
    """Unique identity tuple of a test: (module_name, abi, class_name, method_name)."""

    __test__ = False

    module_name: str
    abi: str
    class_name: str
    method_name: str

    def to_tuple(self) -> Tuple[str, str, str, str]:
        return (self.module_name, self.abi, self.class_name, self.method_name)

    def __str__(self) -> str:
        return f"{self.abi} {self.module_name} {self.class_name}#{self.method_name}"


@dataclass(frozen=True)
class TestResult:
    """Result of a single test execution."""


    __test__ = False

    module_name: str

    abi: str
    class_name: str
    method_name: str
    result: str  # open set: pass, fail, IGNORED, ASSUMPTION_FAILURE, etc.
    message: Optional[str] = None
    stack_trace: Optional[str] = None
    max_stack_lines: int = 20

    def __post_init__(self) -> None:
        if self.stack_trace:
            object.__setattr__(
                self,
                "stack_trace",
                truncate_stack_trace(self.stack_trace, self.max_stack_lines),
            )

    @property
    def key(self) -> Tuple[str, str, str, str]:
        return (self.module_name, self.abi, self.class_name, self.method_name)

    @property
    def test_key(self) -> TestKey:
        return TestKey(self.module_name, self.abi, self.class_name, self.method_name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.result.lower() == other.lower()
        if isinstance(other, TestResult):
            return (
                self.module_name == other.module_name
                and self.abi == other.abi
                and self.class_name == other.class_name
                and self.method_name == other.method_name
                and self.result == other.result
                and self.message == other.message
                and self.stack_trace == other.stack_trace
            )
        return False

    def __hash__(self) -> int:
        return hash((
            self.module_name,
            self.abi,
            self.class_name,
            self.method_name,
            self.result,
            self.message,
            self.stack_trace,
        ))



@dataclass
class ModuleResult:
    """Result of a test module execution."""

    name: str
    abi: str
    done: bool = True
    reason: Optional[str] = None
    tests: List[TestResult] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[str, str]:
        return (self.name, self.abi)


@dataclass
class TestReport:
    """Full CTS run report."""

    __test__ = False

    build_fingerprint: Optional[str] = None

    suite_name: Optional[str] = None
    suite_version: Optional[str] = None
    suite_build: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    report_version: Optional[str] = None
    abis: Set[str] = field(default_factory=set)
    modules: List[ModuleResult] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    raw_metadata: Dict[str, str] = field(default_factory=dict)

    def all_tests(self) -> List[TestResult]:
        """Returns flat list of all test results in all modules."""
        tests = []
        for mod in self.modules:
            tests.extend(mod.tests)
        return tests

    def tests_by_key(self) -> Dict[Tuple[str, str, str, str], TestResult]:
        """Returns map of test identity tuple -> TestResult."""
        res = {}
        for test in self.all_tests():
            res[test.key] = test
        return res
