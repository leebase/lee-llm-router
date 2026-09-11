"""Tests for the pure next-action mapping (D211 ruling 6, P2-6).

``staffing.next_action.next_action`` is a pure decision function: no
dispatch, no state, no I/O, no provider call. Every input — including
null, unknown classes, and invalid capability counts — yields exactly
one of the six action strings. These tests pin the exact outputs, the
platform-prefix boundary, the first/subsequent capability boundary, and
the fail-closed boundaries, using only in-process string inputs.
"""

from __future__ import annotations

from lee_llm_router.staffing import next_action as next_action_module
from lee_llm_router.staffing.next_action import (
    ESCALATE,
    FIRST_CAPABILITY_ATTEMPT,
    PLATFORM_FAILURE_PREFIX,
    RECONCILE_THEN_RETRY,
    REPAIR_SAME_ROUTE,
    RETRY_SAME_ROUTE_AFTER_PLATFORM_REPAIR,
    RETURN_TO_PLANNER,
    SECOND_CAPABILITY_ATTEMPT,
    SUPERVISOR_JUDGMENT,
    next_action,
)

# ---------------------------------------------------------------------------
# Exact mapping for the closed five-value failure_class vocabulary
# ---------------------------------------------------------------------------


def test_platform_timeout_maps_to_retry_after_platform_repair() -> None:
    assert next_action("platform_timeout") == RETRY_SAME_ROUTE_AFTER_PLATFORM_REPAIR


def test_platform_env_maps_to_retry_after_platform_repair() -> None:
    assert next_action("platform_env") == RETRY_SAME_ROUTE_AFTER_PLATFORM_REPAIR


def test_spec_rejected_maps_to_return_to_planner() -> None:
    assert next_action("spec_rejected") == RETURN_TO_PLANNER


def test_first_capability_rejected_maps_to_repair_same_route() -> None:
    assert next_action("capability_rejected", 1) == REPAIR_SAME_ROUTE


def test_second_capability_rejected_maps_to_escalate() -> None:
    assert next_action("capability_rejected", 2) == ESCALATE


def test_unaccounted_spend_maps_to_reconcile_then_retry() -> None:
    assert next_action("unaccounted_spend") == RECONCILE_THEN_RETRY


def test_null_failure_class_maps_to_supervisor_judgment() -> None:
    # attempt-record v2: failure_class null means "no failure recorded";
    # there is no failure to map, so the supervisor decides.
    assert next_action(None) == SUPERVISOR_JUDGMENT


def test_oracle_failed_maps_to_supervisor_judgment() -> None:
    # P3-2 definition (D213 ruling 3 + the accepted D211 ruling 6 mapping):
    # oracle_failed is a deterministic *classification* class in the Phase 3
    # vocabulary, but the class→action decision stays owned by this pure
    # Phase 2 mapping, and oracle_failed is none of platform_*,
    # spec_rejected, capability_rejected, or unaccounted_spend. The
    # already-authorized handling is therefore the pure mapping's own
    # fail-closed outcome: supervisor_judgment. The P3-2 CLI preserves this
    # verbatim and invents no dispatch or policy for it.
    assert next_action("oracle_failed") == SUPERVISOR_JUDGMENT
    # The capability context is consulted only for capability_rejected, so
    # a repair count never turns oracle_failed into a repair or escalation.
    assert next_action("oracle_failed", 1) == SUPERVISOR_JUDGMENT
    assert next_action("oracle_failed", "second") == SUPERVISOR_JUDGMENT


def test_unknown_class_maps_to_supervisor_judgment() -> None:
    # D213 ruling 3's deterministic "unknown" class fails closed exactly
    # like any other unnamed string: the supervisor decides.
    assert next_action("unknown") == SUPERVISOR_JUDGMENT


# ---------------------------------------------------------------------------
# Platform-prefix boundary
# ---------------------------------------------------------------------------


def test_any_platform_underscored_prefix_retries_same_route() -> None:
    for failure_class in (
        "platform_x",
        "platform_auth",
        "platform_quotas",
        "platform_something_unheard_of",
    ):
        assert next_action(failure_class) == RETRY_SAME_ROUTE_AFTER_PLATFORM_REPAIR


def test_bare_platform_without_underscore_is_unknown() -> None:
    # The contract prefix is the literal "platform_"; "platform" alone is
    # not a named class and must not inherit the platform action.
    assert next_action("platform") == SUPERVISOR_JUDGMENT


def test_hyphenated_platform_lookalike_is_unknown() -> None:
    assert next_action("platform-foo") == SUPERVISOR_JUDGMENT


def test_platform_substring_not_at_start_is_unknown() -> None:
    assert next_action("network_platform_env") == SUPERVISOR_JUDGMENT


def test_platform_prefix_is_case_sensitive() -> None:
    assert next_action("PLATFORM_TIMEOUT") == SUPERVISOR_JUDGMENT
    assert next_action("Platform_env") == SUPERVISOR_JUDGMENT


def test_whitespace_surrounding_a_known_class_is_unknown() -> None:
    # Matching is exact: no trimming, no normalization.
    assert next_action(" platform_timeout") == SUPERVISOR_JUDGMENT
    assert next_action("platform_timeout ") == SUPERVISOR_JUDGMENT
    assert next_action(" spec_rejected") == SUPERVISOR_JUDGMENT


def test_whitespace_only_prefix_match_with_trailing_space_fails_closed() -> None:
    # P2-6 regression: "platform_timeout " starts with the literal prefix
    # "platform_" and previously inherited the platform retry action even
    # though its surrounding whitespace makes it an unknown class.
    assert next_action("platform_timeout ") == SUPERVISOR_JUDGMENT


# ---------------------------------------------------------------------------
# Unknown / ill-typed failure classes fail closed
# ---------------------------------------------------------------------------


def test_unnamed_class_fails_closed_to_supervisor_judgment() -> None:
    for failure_class in (
        "network_error",
        "timeout",
        "spec_reject",
        "capability_rejected_timeout",
        "UNACCOUNTED_SPEND",
        "unaccounted_spends",
    ):
        assert next_action(failure_class) == SUPERVISOR_JUDGMENT


def test_empty_string_failure_class_fails_closed() -> None:
    assert next_action("") == SUPERVISOR_JUDGMENT


def test_non_string_failure_class_fails_closed() -> None:
    for failure_class in (42, 3.14, True, False, ["platform_env"], {"class": "x"}):
        assert next_action(failure_class) == SUPERVISOR_JUDGMENT  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Capability first / second / subsequent boundary
# ---------------------------------------------------------------------------


def test_first_capability_word_context_maps_to_repair_same_route() -> None:
    assert next_action("capability_rejected", FIRST_CAPABILITY_ATTEMPT) == (
        REPAIR_SAME_ROUTE
    )


def test_second_capability_word_context_maps_to_escalate() -> None:
    assert next_action("capability_rejected", SECOND_CAPABILITY_ATTEMPT) == ESCALATE


def test_subsequent_capability_attempts_escalate() -> None:
    for attempt in (2, 3, 4, 10, 10**6):
        assert next_action("capability_rejected", attempt) == ESCALATE


def test_capability_word_context_is_case_sensitive() -> None:
    assert next_action("capability_rejected", "First") == SUPERVISOR_JUDGMENT
    assert next_action("capability_rejected", "SECOND") == SUPERVISOR_JUDGMENT


# ---------------------------------------------------------------------------
# Invalid / missing capability counts fail closed
# ---------------------------------------------------------------------------


def test_capability_rejected_without_context_fails_closed() -> None:
    # The count is caller-supplied evidence; without it the function must
    # not guess first vs second.
    assert next_action("capability_rejected") == SUPERVISOR_JUDGMENT
    assert next_action("capability_rejected", None) == SUPERVISOR_JUDGMENT


def test_invalid_capability_counts_fail_closed() -> None:
    for attempt in (0, -1, -100, 1.0, 2.5, True, False, "1", "2", "third", "zero"):
        assert next_action("capability_rejected", attempt) == SUPERVISOR_JUDGMENT  # type: ignore[arg-type]


def test_no_third_word_context_exists() -> None:
    # Word context names exactly the first and second attempts; later
    # attempts are expressed as integers, and "third" is not a valid word.
    assert next_action("capability_rejected", "third") == SUPERVISOR_JUDGMENT


def test_capability_context_ignored_for_other_classes() -> None:
    assert next_action("platform_timeout", 2) == RETRY_SAME_ROUTE_AFTER_PLATFORM_REPAIR
    assert (
        next_action("platform_env", "first") == RETRY_SAME_ROUTE_AFTER_PLATFORM_REPAIR
    )
    assert next_action("spec_rejected", 99) == RETURN_TO_PLANNER
    assert next_action("spec_rejected", None) == RETURN_TO_PLANNER
    assert next_action("unaccounted_spend", 3) == RECONCILE_THEN_RETRY
    assert next_action(None, 2) == SUPERVISOR_JUDGMENT


# ---------------------------------------------------------------------------
# The five replay facts (fixed trace-derived inputs, exact expected_action)
# ---------------------------------------------------------------------------


def test_five_replay_facts_map_failure_class_to_expected_action_exactly() -> None:
    # docs/staffing/phase2-contracts.md §Five replay facts. The class key
    # and oracle are fixed inputs of each case; next_action consumes only
    # the failure class.
    replay = [
        ("platform_timeout", "retry_same_route_after_platform_repair"),
        ("spec_rejected", "return_to_planner"),
        ("platform_env", "retry_same_route_after_platform_repair"),
        ("unaccounted_spend", "reconcile_then_retry"),
        ("platform_env", "retry_same_route_after_platform_repair"),
    ]
    for failure_class, expected_action in replay:
        assert next_action(failure_class) == expected_action


# ---------------------------------------------------------------------------
# Purity and exact string outputs
# ---------------------------------------------------------------------------


def test_every_return_value_is_exactly_one_of_six_action_strings() -> None:
    actions = {
        RETRY_SAME_ROUTE_AFTER_PLATFORM_REPAIR,
        RETURN_TO_PLANNER,
        REPAIR_SAME_ROUTE,
        ESCALATE,
        RECONCILE_THEN_RETRY,
        SUPERVISOR_JUDGMENT,
    }
    sampled = [
        next_action(failure_class)
        for failure_class in (
            None,
            "",
            "platform_timeout",
            "platform_env",
            "platform_x",
            "platform",
            "spec_rejected",
            "capability_rejected",
            "unaccounted_spend",
            "mystery",
        )
    ] + [
        next_action("capability_rejected", attempt)
        for attempt in (1, 2, 3, None, 0, "first", "second", "third", True)
    ]
    assert set(sampled) <= actions


def test_repeated_calls_are_deterministic_and_inputs_unmutated() -> None:
    failure_class = "capability_rejected"
    first = next_action(failure_class, 1)
    second = next_action(failure_class, 1)
    assert first == second == REPAIR_SAME_ROUTE
    # The mapping never mutates its inputs.
    assert failure_class == "capability_rejected"
    assert FIRST_CAPABILITY_ATTEMPT == "first"
    assert SECOND_CAPABILITY_ATTEMPT == "second"


def test_prefix_constant_matches_documented_platform_prefix() -> None:
    assert PLATFORM_FAILURE_PREFIX == "platform_"


def test_module_exports_nothing_beyond_declared_api() -> None:
    # The module stays a pure decision surface: only the constants and the
    # mapping function are public.
    assert set(next_action_module.__all__) == {
        "ESCALATE",
        "FIRST_CAPABILITY_ATTEMPT",
        "PLATFORM_FAILURE_PREFIX",
        "RECONCILE_THEN_RETRY",
        "REPAIR_SAME_ROUTE",
        "RETURN_TO_PLANNER",
        "RETRY_SAME_ROUTE_AFTER_PLATFORM_REPAIR",
        "SECOND_CAPABILITY_ATTEMPT",
        "SUPERVISOR_JUDGMENT",
        "next_action",
    }
