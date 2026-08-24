from cts_triage.align import align_reports
from cts_triage.parser import parse_xml
from tools.make_fixtures import create_cts_xml


def test_alignment_pairs_and_abi_isolation():
    """Verify test pairs match across baseline/candidate and ABIs remain distinct."""
    baseline_xml = create_cts_xml(
        build_fingerprint="build_v1",
        abis=["arm64-v8a", "armeabi-v7a"],
        modules_spec=[
            {
                "name": "CtsWidgetTestCases",
                "abi": "arm64-v8a",
                "test_cases": [
                    {
                        "name": "ButtonTest",
                        "tests": [
                            {"name": "testCommon", "result": "pass"},
                            {"name": "testBaselineOnly", "result": "pass"},
                        ],
                    }
                ],
            },
            {
                "name": "CtsWidgetTestCases",
                "abi": "armeabi-v7a",
                "test_cases": [
                    {
                        "name": "ButtonTest",
                        "tests": [
                            {"name": "testCommon", "result": "pass"},
                        ],
                    }
                ],
            },
        ],
    )

    candidate_xml = create_cts_xml(
        build_fingerprint="build_v2",
        abis=["arm64-v8a", "x86_64"],
        modules_spec=[
            {
                "name": "CtsWidgetTestCases",
                "abi": "arm64-v8a",
                "test_cases": [
                    {
                        "name": "ButtonTest",
                        "tests": [
                            {"name": "testCommon", "result": "pass"},
                            {"name": "testCandidateOnly", "result": "pass"},
                        ],
                    }
                ],
            },
            {
                "name": "CtsWidgetTestCases",
                "abi": "x86_64",
                "test_cases": [
                    {
                        "name": "ButtonTest",
                        "tests": [
                            {"name": "testCommon", "result": "pass"},
                        ],
                    }
                ],
            },
        ],
    )

    b_report = parse_xml(baseline_xml)
    c_report = parse_xml(candidate_xml)

    comparison = align_reports(b_report, c_report)

    # Check metadata diff
    assert comparison.metadata_diff is not None
    assert comparison.metadata_diff.is_same_build is False
    assert comparison.metadata_diff.added_abis == {"x86_64"}
    assert comparison.metadata_diff.removed_abis == {"armeabi-v7a"}

    # Test identity is (module, abi, class, method)
    # 1. arm64-v8a testCommon: present in both
    p_common_arm64 = comparison.get_pair(
        "CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testCommon"
    )
    assert p_common_arm64 is not None
    assert p_common_arm64.is_present_in_both is True

    # 2. arm64-v8a testBaselineOnly: baseline only
    p_base_only = comparison.get_pair(
        "CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testBaselineOnly"
    )
    assert p_base_only is not None
    assert p_base_only.is_baseline_only is True

    # 3. arm64-v8a testCandidateOnly: candidate only
    p_cand_only = comparison.get_pair(
        "CtsWidgetTestCases", "arm64-v8a", "ButtonTest", "testCandidateOnly"
    )
    assert p_cand_only is not None
    assert p_cand_only.is_candidate_only is True

    # 4. armeabi-v7a testCommon vs x86_64 testCommon: isolated by ABI!
    p_v7a = comparison.get_pair(
        "CtsWidgetTestCases", "armeabi-v7a", "ButtonTest", "testCommon"
    )
    assert p_v7a is not None
    assert p_v7a.is_baseline_only is True

    p_x86 = comparison.get_pair(
        "CtsWidgetTestCases", "x86_64", "ButtonTest", "testCommon"
    )
    assert p_x86 is not None
    assert p_x86.is_candidate_only is True
