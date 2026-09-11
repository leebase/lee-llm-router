"""Tests for deterministic failure classification (P3-1, D213 ruling 3).

Every deterministic class gets an exact evidence fixture under
``tests/fixtures/staffing/failure-classify/<class>.json``; the
platform-environment pattern families are checked verbatim against the
cited Agent-Orch source (pattern strings copied with citation, never
imported). ``spec_rejected``/``capability_rejected`` must only ever be
returned through an explicit judgment naming a review verdict — never
inferred from prose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lee_llm_router.staffing.failure import (
    ALL_FAILURE_CLASSES,
    AUTH_PATTERNS,
    CAPABILITY_REJECTED,
    DETERMINISTIC_FAILURE_CLASSES,
    JUDGMENT_FAILURE_CLASSES,
    LOGGED_OUT_PATTERNS,
    MISSING_BINARY_PATTERNS,
    ORACLE_FAILED,
    PERMISSION_PATTERNS,
    PLATFORM_ENV,
    PLATFORM_ENV_EXIT_CODES,
    PLATFORM_ENV_PATTERNS,
    PLATFORM_TIMEOUT,
    QUOTA_PATTERNS,
    SERVICE_PATTERNS,
    SPEC_REJECTED,
    UNACCOUNTED_SPEND,
    UNKNOWN,
    FailureClassificationError,
    classify_failure,
    is_deterministic_failure_class,
    is_judgment_failure_class,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "staffing" / "failure-classify"


def _fixture(class_name: str) -> dict:
    """Load one exact evidence fixture by failure class name."""
    return json.loads((FIXTURES_DIR / f"{class_name}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Exact pattern families, copied with citation
# ---------------------------------------------------------------------------

# Source citation:
# /home/lee/projects/agent-orch/src/agent_orch/failure_classification.py
EXPECTED_PATTERN_SOURCES = {
    "AUTH_PATTERNS": [
        r"auth(entication)?\s+(failed|expired|invalid)",
        r"token\s+(expired|invalid|revoked)",
        r"401\s+unauthorized",
        r"invalid_api_key",
        r"incorrect\s+api\s+key",
        r"oauth\s+(error|expired|token)",
    ],
    "LOGGED_OUT_PATTERNS": [
        r"not\s+logged\s+in",
        r"login\s+required",
        r"run\s+.*login",
        r"session\s+expired",
        r"you('ve|\s+have)\s+hit\s+your\s+session\s+limit",
    ],
    "MISSING_BINARY_PATTERNS": [
        r"command\s+not\s+found",
        r"no\s+such\s+file\s+or\s+directory:\s*['\"].*['\"]",
        r"executable\s+file\s+not\s+found",
        r"binary\s+not\s+found",
        r"FileNotFoundError:\s*\[Errno\s+2\]",
    ],
    "QUOTA_PATTERNS": [
        r"quota\s+(exceeded|exhausted|limit)",
        r"rate\s+limit\s+exceeded",
        r"429\s+too\s+many\s+requests",
        r"insufficient_quota",
        r"resource\s+exhausted",
        r"billing\s+(limit|disabled)",
    ],
    "PERMISSION_PATTERNS": [
        r"permission\s+denied",
        r"permissionerror:\s*\[Errno\s+13\]",
        r"operation\s+not\s+permitted",
        r"eacces",
    ],
    "SERVICE_PATTERNS": [
        r"503\s+service\s+unavailable",
        r"502\s+bad\s+gateway",
        r"504\s+gateway\s+timeout",
        r"connection\s+refused",
        r"endpoint\s+connection\s+error",
    ],
}

_PATTERN_FAMILY_MAP = {
    "AUTH_PATTERNS": AUTH_PATTERNS,
    "LOGGED_OUT_PATTERNS": LOGGED_OUT_PATTERNS,
    "MISSING_BINARY_PATTERNS": MISSING_BINARY_PATTERNS,
    "QUOTA_PATTERNS": QUOTA_PATTERNS,
    "PERMISSION_PATTERNS": PERMISSION_PATTERNS,
    "SERVICE_PATTERNS": SERVICE_PATTERNS,
}


@pytest.mark.parametrize("family_name", sorted(EXPECTED_PATTERN_SOURCES), ids=str)
def test_platform_env_pattern_families_are_copied_exactly(family_name):
    """Each platform pattern family matches the cited Agent-Orch source."""
    expected = [p.pattern for p in _PATTERN_FAMILY_MAP[family_name]]
    assert expected == EXPECTED_PATTERN_SOURCES[family_name]


def test_platform_env_patterns_are_the_union_of_the_families():
    assert PLATFORM_ENV_PATTERNS == (
        *AUTH_PATTERNS,
        *LOGGED_OUT_PATTERNS,
        *MISSING_BINARY_PATTERNS,
        *QUOTA_PATTERNS,
        *PERMISSION_PATTERNS,
        *SERVICE_PATTERNS,
    )


def test_platform_env_exit_codes_are_copied_from_the_cited_source():
    """Exit codes 126/127 come from the cited Agent-Orch classification."""
    assert PLATFORM_ENV_EXIT_CODES == frozenset({126, 127})


def test_closed_vocabularies_match_d213_ruling_3():
    assert DETERMINISTIC_FAILURE_CLASSES == {
        PLATFORM_TIMEOUT,
        PLATFORM_ENV,
        UNACCOUNTED_SPEND,
        ORACLE_FAILED,
        UNKNOWN,
    }
    assert JUDGMENT_FAILURE_CLASSES == {SPEC_REJECTED, CAPABILITY_REJECTED}
    assert ALL_FAILURE_CLASSES == (
        DETERMINISTIC_FAILURE_CLASSES | JUDGMENT_FAILURE_CLASSES
    )
    assert is_deterministic_failure_class(PLATFORM_TIMEOUT)
    assert not is_deterministic_failure_class(SPEC_REJECTED)
    assert is_judgment_failure_class(SPEC_REJECTED)
    assert not is_judgment_failure_class(ORACLE_FAILED)


# ---------------------------------------------------------------------------
# Every deterministic class, from its exact evidence fixture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("class_name", "fixture_name"),
    [
        (PLATFORM_TIMEOUT, "platform_timeout"),
        (PLATFORM_ENV, "platform_env"),
        (UNACCOUNTED_SPEND, "unaccounted_spend"),
        (ORACLE_FAILED, "oracle_failed"),
        (UNKNOWN, "unknown"),
        (SPEC_REJECTED, "spec_rejected"),
        (CAPABILITY_REJECTED, "capability_rejected"),
    ],
)
def test_exact_evidence_fixture_classifies_to_its_class(class_name, fixture_name):
    assert classify_failure(_fixture(fixture_name)) == class_name


@pytest.mark.parametrize(
    ("class_name", "fixture_name"),
    [
        (PLATFORM_TIMEOUT, "platform_timeout"),
        (PLATFORM_ENV, "platform_env"),
        (UNACCOUNTED_SPEND, "unaccounted_spend"),
        (ORACLE_FAILED, "oracle_failed"),
        (UNKNOWN, "unknown"),
        (SPEC_REJECTED, "spec_rejected"),
        (CAPABILITY_REJECTED, "capability_rejected"),
    ],
)
def test_exact_evidence_fixture_classifies_via_cli_record(class_name, fixture_name):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "classify-failure",
                "--record",
                str(FIXTURES_DIR / f"{fixture_name}.json"),
                "--json",
            ]
        )
    assert exc.value.code == 0


def test_no_failure_classifies_to_none():
    assert classify_failure(_fixture("none")) is None


# ---------------------------------------------------------------------------
# platform_timeout: watchdog timed-out flag or exit 124, worker or oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timed_out": True},
        {"exit_code": 124},
        {"oracle_timed_out": True},
        {"oracle_exit_code": 124},
    ],
    ids=["watchdog-timed-out", "exit-124", "oracle-timed-out", "oracle-exit-124"],
)
def test_platform_timeout_detection(kwargs):
    assert classify_failure(**kwargs, verdict="fail") == PLATFORM_TIMEOUT


def test_platform_timeout_wins_over_platform_env_and_oracle_failed():
    assert (
        classify_failure(
            exit_code=124,
            stderr="command not found",
            oracle_exit_code=1,
            verdict="fail",
        )
        == PLATFORM_TIMEOUT
    )


# ---------------------------------------------------------------------------
# platform_env: exit codes 126/127, each copied pattern family, oracle errors
# ---------------------------------------------------------------------------


def test_platform_env_exit_codes_126_and_127():
    assert classify_failure(exit_code=126, verdict="fail") == PLATFORM_ENV
    assert classify_failure(exit_code=127, verdict="fail") == PLATFORM_ENV
    assert classify_failure(oracle_exit_code=127, verdict="fail") == PLATFORM_ENV


@pytest.mark.parametrize(
    ("family_name", "sample"),
    [
        ("AUTH_PATTERNS", "401 unauthorized from upstream"),
        ("LOGGED_OUT_PATTERNS", "error: login required"),
        ("MISSING_BINARY_PATTERNS", "sh: codex: command not found"),
        ("QUOTA_PATTERNS", "429 too many requests"),
        ("PERMISSION_PATTERNS", " PermissionError: [Errno 13]"),
        ("SERVICE_PATTERNS", "503 service unavailable"),
    ],
)
def test_platform_env_matches_every_copied_pattern_family(family_name, sample):
    assert classify_failure(stderr=sample, verdict="fail") == PLATFORM_ENV


def test_platform_env_oracle_error_is_platform_env():
    assert (
        classify_failure(oracle_error="launch failure: FileNotFoundError")
        == PLATFORM_ENV
    )


def test_platform_env_wins_over_unaccounted_spend_and_oracle_failed():
    assert (
        classify_failure(
            stderr="connection refused",
            accounting_status="unaccounted",
            oracle_exit_code=1,
            verdict="fail",
        )
        == PLATFORM_ENV
    )


def test_agent_orch_failure_classification_is_platform_env():
    record = {
        "verdict": "fail",
        "agent_orch_attempt": {"failure_classification": "QUOTA_EXHAUSTED"},
    }
    assert classify_failure(record) == PLATFORM_ENV


# ---------------------------------------------------------------------------
# unaccounted_spend: unavailable usage on a metered route
# ---------------------------------------------------------------------------


def test_unaccounted_spend_from_unavailable_usage_on_metered_route():
    assert (
        classify_failure(usage_basis="unavailable", metered_route=True, verdict="pass")
        == UNACCOUNTED_SPEND
    )


def test_unavailable_usage_without_metered_evidence_is_not_unaccounted_spend():
    assert classify_failure(usage_basis="unavailable", verdict="pass") is None


def test_unavailable_usage_on_subscription_record_is_not_unaccounted_spend():
    record = {
        "verdict": "pass",
        "route": {"channel": "openai-sub"},
        "usage": {"basis": "unavailable"},
    }
    assert classify_failure(record) is None


def test_unaccounted_spend_from_accounting_status():
    assert classify_failure(accounting_status="unaccounted") == UNACCOUNTED_SPEND


def test_unaccounted_spend_explicit_flag():
    assert classify_failure(unaccounted_spend=True) == UNACCOUNTED_SPEND


def test_unavailable_usage_on_non_metered_route_is_not_unaccounted_spend():
    """``not_applicable`` proves the route is non-metered: no spend to account."""
    assert (
        classify_failure(
            usage_basis="unavailable",
            accounting_status="not_applicable",
            verdict="pass",
        )
        is None
    )


def test_unaccounted_spend_wins_over_oracle_failed():
    assert (
        classify_failure(accounting_status="unaccounted", oracle_exit_code=1)
        == UNACCOUNTED_SPEND
    )


# ---------------------------------------------------------------------------
# oracle_failed: failed verdict or nonzero oracle exit, without platform evidence
# ---------------------------------------------------------------------------


def test_oracle_failed_from_nonzero_oracle_exit():
    assert classify_failure(oracle_exit_code=1, verdict="fail") == ORACLE_FAILED


def test_oracle_failed_from_failed_verdict_without_platform_evidence():
    assert classify_failure(verdict="fail") == ORACLE_FAILED


def test_oracle_failed_from_mapping_verdict():
    assert classify_failure(verdict={"verdict": "fail"}) == ORACLE_FAILED


def test_unknown_when_failure_evidence_carries_no_verdict():
    assert classify_failure(exit_code=1, stderr="worker exited nonzero") == UNKNOWN


# ---------------------------------------------------------------------------
# Judgment classes: explicit --judgment after a review verdict, never inferred
# ---------------------------------------------------------------------------


def test_judgment_requires_review_verdict():
    with pytest.raises(FailureClassificationError, match="review verdict"):
        classify_failure(judgment=SPEC_REJECTED)


def test_judgment_rejects_passing_review_verdict():
    with pytest.raises(FailureClassificationError, match="pass"):
        classify_failure(judgment=CAPABILITY_REJECTED, review_verdict="pass")


def test_judgment_rejects_unknown_values():
    with pytest.raises(FailureClassificationError, match="explicit judgment"):
        classify_failure(judgment="oracle_failed", review_verdict="fail")


def test_judgment_rejects_surrounding_whitespace():
    with pytest.raises(FailureClassificationError, match="whitespace"):
        classify_failure(judgment=" spec_rejected", review_verdict="fail")


def test_judgment_rejects_non_string():
    with pytest.raises(FailureClassificationError, match="must be a string"):
        classify_failure(judgment=42, review_verdict="fail")


def test_judgment_accepts_review_verdict_from_record_mapping():
    record = {
        "verdict": "fail",
        "judgment": SPEC_REJECTED,
        "review": {"final_verdict": "fail"},
    }
    assert classify_failure(record) == SPEC_REJECTED


@pytest.mark.parametrize("prose", ["spec rejected", "capability rejected"])
def test_judgment_classes_are_never_inferred_from_text(prose):
    """Prose naming a judgment class classifies as unknown, never as judgment."""
    assert classify_failure(stderr=prose, verdict="fail") == ORACLE_FAILED
    assert classify_failure(stderr=prose) == UNKNOWN


def test_judgment_overrides_record_agent_orch_classification():
    """An explicit judgment with a review verdict is never shadowed by a record."""
    record = {
        "verdict": "fail",
        "judgment": CAPABILITY_REJECTED,
        "review_verdict": "fail",
        "agent_orch_attempt": {"failure_classification": "AUTH_EXPIRED"},
    }
    assert classify_failure(record) == CAPABILITY_REJECTED


def test_judgment_without_verdict_in_record_still_requires_review():
    record = {"verdict": "fail", "judgment": SPEC_REJECTED}
    with pytest.raises(FailureClassificationError, match="review verdict"):
        classify_failure(record)
