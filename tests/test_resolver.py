"""Tests for :mod:`lee_llm_router.resolver` — strict, flex, and bind modes.

Every snapshot here is synthetic and every crews file is written to ``tmp_path``:
the resolver is a pure function, so the tests never read the live crews file, the
live availability snapshot, or any provider binary.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from lee_llm_router.availability import parse_availability
from lee_llm_router.crews import (
    ROLE_SCOPED_CITATION,
    Crew,
    CrewsConfig,
    Stage,
    load_crews,
)
from lee_llm_router.events import (
    EVENT_FIELDS,
    MAX_EVENT_BYTES,
    build_event,
    encode_event,
)
from lee_llm_router.resolver import (
    REMEDY_REFRESH,
    REMEDY_WAIT,
    Resolution,
    ResolutionError,
    resolve,
    route_id,
)

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

EFFORT_KEYS = {"CODEX": "REASONING_EFFORT"}
"""Stage-worker env key holding the effort, when it is not plain ``EFFORT``."""

WORKERS: dict[str, tuple[str, str, str, str | None]] = {
    "codex_sol_high": ("CODEX", "/x/bin/codex", "gpt-5.6-sol", "high"),
    "codex_luna_max": ("CODEX", "/x/bin/codex", "gpt-5.6-luna", "max"),
    "claude_opus5_high": ("CLAUDE", "/x/bin/claude", "claude-opus-5", "high"),
    "claude_sonnet5_high": ("CLAUDE", "/x/bin/claude", "claude-sonnet-5", "high"),
    "antigravity_gemini38_flash_high": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.8-flash-high",
        "high",
    ),
    "antigravity_gemini31_pro": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.1-pro",
        "high",
    ),
    "antigravity_gemini31_pro_b": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.1-pro",
        "high",
    ),
    "antigravity_gemini31_pro_c": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.1-pro",
        "high",
    ),
    "antigravity_gemini31_pro_d": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.1-pro",
        "high",
    ),
    "antigravity_bad_effort": (
        "ANTIGRAVITY",
        "/x/bin/agy",
        "gemini-3.8-flash-high",
        "xhigh",
    ),
    "omp_glm_flash": ("OMP", "/x/bin/omp", "glm-5.3-flash", None),
}
"""Synthetic workers: ``id -> (env prefix, binary, model, effort)``."""


def worker_command(prefix: str, binary: str, model: str, effort: str | None) -> str:
    """Render a crews-file command template for a synthetic worker."""
    parts = [
        "/usr/bin/env",
        f"{prefix}_STAGE_WORKER_BINARY={binary}",
        f"{prefix}_STAGE_WORKER_MODEL={model}",
    ]
    if prefix == "OMP":
        # P0-2c: the omp_cli funding channel is derived from the stage-worker
        # provider signal; these synthetic workers bill to openrouter.
        parts.append("OMP_STAGE_WORKER_PROVIDER=openrouter")
    if effort is not None:
        key = EFFORT_KEYS.get(prefix, "EFFORT")
        parts.append(f"{prefix}_STAGE_WORKER_{key}={effort}")
    parts.append("python3 /x/stage_worker.py {stage}")
    return " ".join(parts)


CREWS_BLOCK = """
crews:
  resolver-crew:
    description: Tiered flex ordering, never-automatic, and forbidden handling.
    stages:
      envision:
        - codex_sol_high
        - claude_sonnet5_high
        - antigravity_gemini38_flash_high
      ideate: [codex_luna_max, codex_sol_high]
      reconsider: [claude_opus5_high]
      score: [antigravity_gemini31_pro]
      author: [antigravity_gemini31_pro, codex_sol_high]
  resolver-forbidden:
    description: Forbidden candidates are skipped, but never skipped silently.
    stages:
      envision: [antigravity_gemini31_pro, codex_sol_high]
      ideate: [antigravity_gemini31_pro, antigravity_gemini31_pro_b]
      reconsider:
        - antigravity_gemini31_pro
        - antigravity_gemini31_pro_b
        - codex_sol_high
      score:
        - antigravity_gemini31_pro
        - antigravity_gemini31_pro_b
        - antigravity_gemini31_pro_c
        - antigravity_gemini31_pro_d
        - codex_sol_high
      author:
        - antigravity_gemini31_pro
        - antigravity_gemini31_pro_b
        - codex_sol_high
  resolver-coding-forbidden:
    description: Coding stage where all candidates are role-scoped.
    stages:
      author: [antigravity_gemini31_pro, antigravity_gemini31_pro_b]
  resolver-sole-forbidden:
    description: Coding stage with a single role-scoped candidate.
    stages:
      author: [antigravity_gemini31_pro]
  resolver-edges:
    description: Refusal remedies, prompt-delivery shapes, and provider errors.
    stages:
      envision: [codex_luna_max, claude_opus5_high]
      ideate: [codex_sol_high, claude_sonnet5_high]
      reconsider: omp_glm_flash
      score: antigravity_gemini38_flash_high
      author: antigravity_bad_effort
"""


def crews_yaml() -> str:
    """Render the whole synthetic crews file."""
    lines = ["version: 1", "", "workers:"]
    for worker_id, spec in WORKERS.items():
        lines.append(f"  {worker_id}:")
        lines.append(f'    command: "{worker_command(*spec)}"')
        lines.append("    timeout_seconds: 600")
    lines.extend(CREWS_BLOCK.splitlines())
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def crews(tmp_path_factory):
    """Load the synthetic crews file used by every test in this module."""
    path: Path = tmp_path_factory.mktemp("crews") / "crews.yaml"
    path.write_text(crews_yaml(), encoding="utf-8")
    return load_crews(path)


def _entry(
    provider: str,
    bucket: str,
    status: str,
    remaining_pct: float,
    *,
    resets_at: str | None = None,
    pace_ratio: float | None = None,
) -> dict[str, Any]:
    """Build one raw ``subscriptions`` record."""
    entry: dict[str, Any] = {
        "provider": provider,
        "bucket": bucket,
        "status": status,
        "remaining_pct": remaining_pct,
    }
    if resets_at is not None:
        entry["resets_at"] = resets_at
    if pace_ratio is not None:
        entry["pace_ratio"] = pace_ratio
    return entry


def openai(status: str, remaining_pct: float, **kwargs: Any) -> dict[str, Any]:
    """Build an ``openai-sub`` record."""
    return _entry("OpenAI/Codex", "Weekly limit", status, remaining_pct, **kwargs)


def anthropic(status: str, remaining_pct: float, **kwargs: Any) -> dict[str, Any]:
    """Build an ``anthropic-sub`` record."""
    return _entry("Anthropic/Claude", "Weekly limit", status, remaining_pct, **kwargs)


def gemini(status: str, remaining_pct: float, **kwargs: Any) -> dict[str, Any]:
    """Build a ``gemini-sub`` record."""
    return _entry("Gemini/agy", "Gemini models daily", status, remaining_pct, **kwargs)


def snap(*entries: dict[str, Any], observed_at: datetime | None = None):
    """Parse a synthetic snapshot from inline records."""
    payload = {
        "observed_at": (observed_at or NOW).isoformat(),
        "host": "testhost",
        "subscriptions": list(entries),
    }
    return parse_availability(payload, now=NOW)


HEALTHY = ("ON TRACK", 90.0)
DEGRADED_BY_STATUS = ("HOT", 48.0)
DEGRADED_BY_PCT = ("ON TRACK", 20.0)
LIKELY_EXHAUSTED = ("HOT", 5.0)
EXHAUSTED = ("TOO FAST", 0.0)


# --------------------------------------------------------------------------
# strict mode
# --------------------------------------------------------------------------


def test_strict_returns_the_crews_named_worker_on_healthy_headroom(crews):
    """Strict returns the first declared worker and reports its headroom."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY, pace_ratio=0.8)),
        crew="resolver-crew",
        role="envision",
    )
    assert isinstance(result, Resolution)
    assert result.worker_id == "codex_sol_high"
    assert result.provider == "codex_cli"
    assert result.model == "gpt-5.6-sol"
    assert result.effort == "high"
    assert result.channel == "openai-sub"
    assert result.headroom == "healthy"
    assert result.headroom_remaining_fraction == pytest.approx(0.9)
    assert result.pace_ratio == pytest.approx(0.8)
    assert result.mode == "strict"
    assert result.authorized_by is None
    assert result.snapshot_stale is False
    assert result.snapshot_observed_at == NOW.isoformat()
    assert result.worker_command.startswith("/usr/bin/env CODEX_STAGE_WORKER_BINARY")


def test_strict_does_not_veto_on_degraded_and_says_so(crews):
    """A degraded channel passes strict, and the reason names the state."""
    result = resolve(
        crews,
        snap(openai(*DEGRADED_BY_STATUS)),
        crew="resolver-crew",
        role="envision",
    )
    assert result.worker_id == "codex_sol_high"
    assert result.headroom == "degraded"
    assert "channel openai-sub degraded (HOT, 48% remaining)" in result.reason
    assert "strict mode does not veto on degraded" in result.reason


def test_strict_does_not_veto_on_unknown_and_says_so(crews):
    """An unknown channel passes strict, and the reason names the state."""
    result = resolve(crews, snap(), crew="resolver-crew", role="envision")
    assert result.worker_id == "codex_sol_high"
    assert result.headroom == "unknown"
    assert "channel openai-sub unknown" in result.reason
    assert "strict mode does not veto on unknown" in result.reason


def test_strict_vetoes_on_exhausted_with_exit_2_and_reset_remedy(crews):
    """An exhausted channel is a strict veto with a reset-time remedy."""
    resets = "2026-09-08T00:00:00+00:00"
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(openai(*EXHAUSTED, resets_at=resets)),
            crew="resolver-crew",
            role="envision",
        )
    error = excinfo.value
    assert error.exit_code == 2
    assert error.kind == "not_eligible"
    assert error.remedy == f"{REMEDY_WAIT} at {resets}"
    assert "channel openai-sub exhausted" in error.message


def test_strict_vetoes_on_likely_exhausted(crews):
    """A likely-exhausted channel is also a strict veto."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(openai(*LIKELY_EXHAUSTED)),
            crew="resolver-crew",
            role="envision",
        )
    assert excinfo.value.exit_code == 2
    assert excinfo.value.remedy == REMEDY_WAIT


def test_strict_refuses_a_role_scoped_model_in_coding_role(crews):
    """A role-scoped named worker in a coding role refuses at exit 3 citing D188."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(gemini(*HEALTHY)),
            crew="resolver-crew",
            role="author",
            mode="strict",
        )
    error = excinfo.value
    assert error.exit_code == 3
    assert error.kind == "forbidden"
    assert "antigravity_gemini31_pro" in error.message
    assert "gemini-3.1-pro" in error.message
    assert "author" in error.message
    assert "coding" in error.message
    assert ROLE_SCOPED_CITATION in error.message


def test_strict_allows_role_scoped_model_in_planning_review_role(crews):
    """A role-scoped named worker in a planning/review role resolves normally."""
    result = resolve(
        crews,
        snap(gemini(*HEALTHY)),
        crew="resolver-crew",
        role="score",
        mode="strict",
    )
    assert result.worker_id == "antigravity_gemini31_pro"
    assert result.model == "gemini-3.1-pro"


def test_strict_ignores_headroom_of_channels_it_does_not_use(crews):
    """Another channel being exhausted never affects the named worker."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY), anthropic(*EXHAUSTED)),
        crew="resolver-crew",
        role="envision",
    )
    assert result.worker_id == "codex_sol_high"
    assert result.headroom == "healthy"


# --------------------------------------------------------------------------
# flex mode
# --------------------------------------------------------------------------


def test_flex_prefers_a_healthy_candidate_that_is_not_first(crews):
    """Healthy wins over degraded and unknown regardless of list position."""
    result = resolve(
        crews,
        snap(openai(*DEGRADED_BY_PCT), gemini(*HEALTHY)),
        crew="resolver-crew",
        role="envision",
        mode="flex",
    )
    assert result.worker_id == "antigravity_gemini38_flash_high"
    assert result.headroom == "healthy"
    assert "first candidate with healthy headroom" in result.reason


def test_flex_falls_back_to_degraded_before_unknown(crews):
    """With nothing healthy, a degraded candidate beats an unknown one."""
    result = resolve(
        crews,
        snap(openai(*DEGRADED_BY_PCT), gemini(*EXHAUSTED)),
        crew="resolver-crew",
        role="envision",
        mode="flex",
    )
    assert result.worker_id == "codex_sol_high"
    assert result.headroom == "degraded"
    assert "no candidate had healthy headroom" in result.reason


def test_flex_uses_unknown_only_as_a_last_resort(crews):
    """With no known headroom anywhere, the first candidate is taken."""
    result = resolve(
        crews,
        snap(),
        crew="resolver-crew",
        role="envision",
        mode="flex",
    )
    assert result.worker_id == "codex_sol_high"
    assert result.headroom == "unknown"
    assert "last resort" in result.reason
    assert "nothing better had known headroom" in result.reason


def test_flex_never_chooses_a_spent_channel(crews):
    """Exhausted and likely-exhausted candidates are never chosen."""
    result = resolve(
        crews,
        snap(
            openai(*EXHAUSTED), anthropic(*LIKELY_EXHAUSTED), gemini(*DEGRADED_BY_PCT)
        ),
        crew="resolver-crew",
        role="envision",
        mode="flex",
    )
    assert result.worker_id == "antigravity_gemini38_flash_high"


def test_flex_skips_never_automatic_when_an_alternative_exists(crews):
    """A never-automatic first candidate is skipped when a peer is eligible."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY)),
        crew="resolver-crew",
        role="ideate",
        mode="flex",
    )
    assert result.worker_id == "codex_sol_high"
    assert "never-automatic" not in result.reason


def test_flex_uses_never_automatic_when_the_crew_left_no_alternative(crews):
    """A sole never-automatic candidate is chosen, and the reason says why."""
    result = resolve(
        crews,
        snap(anthropic(*HEALTHY)),
        crew="resolver-crew",
        role="reconsider",
        mode="flex",
    )
    assert result.worker_id == "claude_opus5_high"
    assert "left no alternative for this stage" in result.reason


def test_flex_remedy_is_refresh_when_every_candidate_is_unknown(crews):
    """Nothing eligible plus nothing known means the snapshot is the problem."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(crews, snap(), crew="resolver-edges", role="envision", mode="flex")
    error = excinfo.value
    assert error.exit_code == 2
    assert error.kind == "not_eligible"
    assert error.remedy == REMEDY_REFRESH


def test_flex_remedy_names_the_earliest_reset_when_candidates_are_spent(crews):
    """The remedy points at the first channel that will come back."""
    early = "2026-09-08T00:00:00+00:00"
    late = "2026-09-09T00:00:00+00:00"
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(
                openai(*EXHAUSTED, resets_at=late),
                anthropic(*LIKELY_EXHAUSTED, resets_at=early),
            ),
            crew="resolver-edges",
            role="ideate",
            mode="flex",
        )
    assert excinfo.value.remedy == f"{REMEDY_WAIT} at {early}"


def test_flex_remedy_falls_back_to_a_plain_wait_without_a_reset_time(crews):
    """No reported reset time still yields an actionable remedy."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(openai(*EXHAUSTED), anthropic(*EXHAUSTED)),
            crew="resolver-edges",
            role="ideate",
            mode="flex",
        )
    assert excinfo.value.remedy == REMEDY_WAIT


def test_flex_skips_a_forbidden_candidate_but_says_so(crews):
    """A role-scoped candidate is skipped in coding role, naming candidate and citing D188."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY), gemini(*HEALTHY)),
        crew="resolver-crew",
        role="author",
        mode="flex",
    )
    assert result.worker_id == "codex_sol_high"
    assert (
        "skipped antigravity_gemini31_pro (role-scoped model gemini-3.1-pro is never automatic for coding role 'author', decisions.md D188)"
        in result.reason
    )


def test_flex_names_every_skipped_forbidden_candidate(crews):
    """Two role-scoped candidates in coding role before the choice means two named skips."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY), gemini(*HEALTHY)),
        crew="resolver-forbidden",
        role="author",
        mode="flex",
    )
    assert result.worker_id == "codex_sol_high"
    assert "skipped antigravity_gemini31_pro (" in result.reason
    assert "skipped antigravity_gemini31_pro_b (" in result.reason
    assert result.reason.count(ROLE_SCOPED_CITATION) == 2


def test_flex_skip_visibility_reason_is_one_line(crews):
    """The reason stays a single line, whatever it has to report."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY), gemini(*HEALTHY)),
        crew="resolver-forbidden",
        role="author",
        mode="flex",
    )
    assert result.worker_id == "codex_sol_high"
    assert "\n" not in result.reason
    assert "\r" not in result.reason


def test_flex_skip_visibility_event_stays_within_the_line_budget(crews):
    """A realistic stage still encodes inside MAX_EVENT_BYTES."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY), gemini(*HEALTHY)),
        crew="resolver-forbidden",
        role="author",
        mode="flex",
    )
    fields = result.to_dict()
    event = build_event(
        **{name: fields[name] for name in EVENT_FIELDS if name in fields}
    )
    assert len(encode_event(event)) <= MAX_EVENT_BYTES


def test_flex_refuses_when_every_candidate_is_forbidden(crews):
    """More than one candidate in coding role, all role-scoped, is a forbidden refusal."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(gemini(*HEALTHY)),
            crew="resolver-coding-forbidden",
            role="author",
            mode="flex",
        )
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "forbidden"
    assert ROLE_SCOPED_CITATION in excinfo.value.message


def test_flex_refuses_when_the_only_candidate_is_forbidden(crews):
    """A sole role-scoped candidate in coding role is exit 3, not exit 2."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(gemini(*HEALTHY)),
            crew="resolver-sole-forbidden",
            role="author",
            mode="flex",
        )
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "forbidden"
    assert ROLE_SCOPED_CITATION in excinfo.value.message


def test_flex_allows_role_scoped_candidate_in_planning_review_role(crews):
    """In planning/review, a role-scoped candidate is eligible and not skipped."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY), gemini(*HEALTHY)),
        crew="resolver-forbidden",
        role="envision",
        mode="flex",
    )
    assert result.worker_id == "antigravity_gemini31_pro"
    assert "skipped" not in result.reason


# --------------------------------------------------------------------------
# bind mode
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs,missing",
    [
        ({"authorized_by": "lee", "reason": "why"}, "worker"),
        ({"worker": "codex_sol_high", "reason": "why"}, "authorized_by"),
        ({"worker": "codex_sol_high", "authorized_by": "lee"}, "reason"),
        (
            {"worker": "codex_sol_high", "authorized_by": "  ", "reason": "why"},
            "authorized_by",
        ),
    ],
)
def test_bind_requires_worker_authority_and_reason(crews, kwargs, missing):
    """Bind refuses unless all three fields are present and non-empty."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(openai(*HEALTHY)),
            crew="resolver-crew",
            role="envision",
            mode="bind",
            **kwargs,
        )
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "usage"
    assert missing in excinfo.value.message


def test_bind_allows_a_worker_outside_the_stage_list(crews):
    """Bind is an escalation: the worker need not be a stage candidate."""
    result = resolve(
        crews,
        snap(openai(*HEALTHY)),
        crew="resolver-crew",
        role="reconsider",
        mode="bind",
        worker="codex_sol_high",
        authorized_by="lee",
        reason="one-off deep review",
    )
    assert result.worker_id == "codex_sol_high"
    assert result.mode == "bind"
    assert result.authorized_by == "lee"
    assert result.reason == "one-off deep review"


def test_bind_reports_exhausted_headroom_without_vetoing(crews):
    """Bind reports headroom; it never refuses on it."""
    result = resolve(
        crews,
        snap(openai(*EXHAUSTED, resets_at="2026-09-08T00:00:00+00:00")),
        crew="resolver-crew",
        role="envision",
        mode="bind",
        worker="codex_sol_high",
        authorized_by="lee",
        reason="ship the release note anyway",
    )
    assert result.headroom == "exhausted"
    assert result.reason == "ship the release note anyway"


def test_bind_allows_a_never_automatic_worker(crews):
    """Never-automatic models are exactly what bind exists for."""
    result = resolve(
        crews,
        snap(anthropic(*HEALTHY)),
        crew="resolver-crew",
        role="envision",
        mode="bind",
        worker="claude_opus5_high",
        authorized_by="lee",
        reason="escalating the architecture pass",
    )
    assert result.worker_id == "claude_opus5_high"
    assert result.model == "claude-opus-5"


def test_bind_refuses_a_role_scoped_model_in_coding_role(crews):
    """No authority can bind a role-scoped model in a coding role."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(gemini(*HEALTHY)),
            crew="resolver-crew",
            role="author",
            mode="bind",
            worker="antigravity_gemini31_pro",
            authorized_by="lee",
            reason="curiosity",
        )
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "forbidden"
    assert ROLE_SCOPED_CITATION in excinfo.value.message


def test_bind_allows_role_scoped_model_in_planning_review_role(crews):
    """A role-scoped model in a planning/review role binds successfully."""
    result = resolve(
        crews,
        snap(gemini(*HEALTHY)),
        crew="resolver-crew",
        role="envision",
        mode="bind",
        worker="antigravity_gemini31_pro",
        authorized_by="lee",
        reason="curiosity",
    )
    assert result.worker_id == "antigravity_gemini31_pro"
    assert result.mode == "bind"
    assert result.authorized_by == "lee"


def test_unmapped_role_fails_closed_in_all_three_modes(crews):
    """A role outside the mapping fails closed in strict, flex, and bind modes."""
    custom_crew = Crew(
        name="unmapped-crew",
        description="Crew with unmapped role",
        stages={
            "custom_stage": Stage(name="custom_stage", workers=("codex_sol_high",))
        },
        governed={},
    )
    all_crews = dict(crews.crews)
    all_crews["unmapped-crew"] = custom_crew
    crews_with_unmapped = CrewsConfig(
        crews=all_crews, workers=crews.workers, path=crews.path
    )

    # 1. strict mode
    with pytest.raises(ResolutionError) as excinfo_strict:
        resolve(
            crews_with_unmapped,
            snap(openai(*HEALTHY)),
            crew="unmapped-crew",
            role="custom_stage",
            mode="strict",
        )
    assert excinfo_strict.value.exit_code == 3
    assert excinfo_strict.value.kind == "config"
    assert "custom_stage" in excinfo_strict.value.message
    assert "author" in excinfo_strict.value.message
    assert ROLE_SCOPED_CITATION in excinfo_strict.value.message

    # 2. flex mode
    with pytest.raises(ResolutionError) as excinfo_flex:
        resolve(
            crews_with_unmapped,
            snap(openai(*HEALTHY)),
            crew="unmapped-crew",
            role="custom_stage",
            mode="flex",
        )
    assert excinfo_flex.value.exit_code == 3
    assert excinfo_flex.value.kind == "config"
    assert "custom_stage" in excinfo_flex.value.message
    assert "author" in excinfo_flex.value.message
    assert ROLE_SCOPED_CITATION in excinfo_flex.value.message

    # 3. bind mode
    with pytest.raises(ResolutionError) as excinfo_bind:
        resolve(
            crews_with_unmapped,
            snap(openai(*HEALTHY)),
            crew="unmapped-crew",
            role="custom_stage",
            mode="bind",
            worker="codex_sol_high",
            authorized_by="lee",
            reason="test",
        )
    assert excinfo_bind.value.exit_code == 3
    assert excinfo_bind.value.kind == "config"
    assert "custom_stage" in excinfo_bind.value.message
    assert "author" in excinfo_bind.value.message
    assert ROLE_SCOPED_CITATION in excinfo_bind.value.message


def test_bind_refuses_an_unknown_worker(crews):
    """A worker that is not in the crews file is a config error."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(openai(*HEALTHY)),
            crew="resolver-crew",
            role="envision",
            mode="bind",
            worker="nope",
            authorized_by="lee",
            reason="typo",
        )
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "config"
    assert "unknown worker 'nope'" in excinfo.value.message


# --------------------------------------------------------------------------
# usage and config errors
# --------------------------------------------------------------------------


def test_unknown_crew_is_exit_3(crews):
    """An unknown crew surfaces the loader's message at exit 3."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(crews, snap(), crew="nope", role="envision")
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "config"
    assert "unknown crew 'nope'" in excinfo.value.message


def test_unknown_stage_is_exit_3(crews):
    """An unknown stage surfaces the crew's message at exit 3."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(crews, snap(), crew="resolver-crew", role="nope")
    assert excinfo.value.exit_code == 3
    assert "has no stage 'nope'" in excinfo.value.message


def test_unknown_mode_is_exit_3(crews):
    """A mode outside the three known ones is a usage error."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(crews, snap(), crew="resolver-crew", role="envision", mode="loose")
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "usage"
    assert "unknown mode 'loose'" in excinfo.value.message


@pytest.mark.parametrize("mode", ["strict", "flex"])
def test_worker_outside_bind_mode_is_exit_3(crews, mode):
    """Naming a worker without bind is refused explicitly, never ignored."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(
            crews,
            snap(openai(*HEALTHY)),
            crew="resolver-crew",
            role="envision",
            mode=mode,
            worker="codex_luna_max",
        )
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "usage"
    assert "only be named in bind mode" in excinfo.value.message


def test_provider_command_failure_is_exit_3(crews):
    """A provider that refuses to build a command is a config error."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(crews, snap(gemini(*HEALTHY)), crew="resolver-edges", role="author")
    assert excinfo.value.exit_code == 3
    assert excinfo.value.kind == "config"
    assert "antigravity_bad_effort" in excinfo.value.message
    assert "effort" in excinfo.value.message


def test_resolution_error_to_dict_is_json_serialisable(crews):
    """A refusal serialises for the CLI's ``--json`` output."""
    with pytest.raises(ResolutionError) as excinfo:
        resolve(crews, snap(openai(*EXHAUSTED)), crew="resolver-crew", role="envision")
    payload = json.loads(json.dumps(excinfo.value.to_dict()))
    assert payload["exit_code"] == 2
    assert payload["kind"] == "not_eligible"
    assert payload["remedy"] == REMEDY_WAIT


# --------------------------------------------------------------------------
# route identity, dispatch, and serialisation
# --------------------------------------------------------------------------


def test_route_id_includes_the_effort(crews):
    """A worker with an effort renders it into the route identity."""
    result = resolve(
        crews, snap(openai(*HEALTHY)), crew="resolver-crew", role="envision"
    )
    assert result.route_id == "codex_cli:gpt-5.6-sol:high"


def test_route_id_uses_default_when_the_worker_declares_no_effort(crews):
    """A missing effort renders as ``default``, never as the string None."""
    result = resolve(crews, snap(), crew="resolver-edges", role="reconsider")
    assert result.effort is None
    assert result.route_id == "omp_cli:glm-5.3-flash:default"
    assert "None" not in result.route_id


def test_route_id_helper_matches_the_documented_shape():
    """The helper is the single definition of the route-identity string."""
    assert route_id("codex_cli", "gpt-5.6-sol", "high") == "codex_cli:gpt-5.6-sol:high"
    assert route_id("omp_cli", "glm-5.3-flash", None) == "omp_cli:glm-5.3-flash:default"


def test_dispatch_command_for_a_codex_worker_uses_argv_delivery(crews):
    """Codex takes its prompt on the command line."""
    result = resolve(
        crews, snap(openai(*HEALTHY)), crew="resolver-crew", role="envision"
    )
    assert result.dispatch_command[0] == "/x/bin/codex"
    assert "{prompt}" in result.dispatch_command
    assert result.prompt_delivery == "argv"
    assert "gpt-5.6-sol" in result.dispatch_command


def test_dispatch_command_for_an_antigravity_worker_uses_argv_delivery(crews):
    """Antigravity takes its prompt on the command line."""
    result = resolve(crews, snap(gemini(*HEALTHY)), crew="resolver-edges", role="score")
    assert result.dispatch_command[0] == "/x/bin/agy"
    assert result.prompt_delivery == "argv"
    assert result.dispatch_command[-1] == "{prompt}"
    assert "--dangerously-skip-permissions" in result.dispatch_command
    assert "--model" in result.dispatch_command
    assert result.model in result.dispatch_command


def test_dispatch_command_for_an_omp_worker_uses_stdin_delivery(crews):
    """omp also takes its prompt on stdin."""
    result = resolve(crews, snap(), crew="resolver-edges", role="reconsider")
    assert result.dispatch_command == ["/x/bin/omp", "-p", "--model", "glm-5.3-flash"]
    assert result.prompt_delivery == "stdin"
    assert result.channel == "openrouter"


def test_to_dict_round_trips_through_json(crews):
    """The whole resolution serialises for the event ledger."""
    result = resolve(
        crews, snap(openai(*HEALTHY)), crew="resolver-crew", role="envision"
    )
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["worker_id"] == "codex_sol_high"
    assert payload["route_id"] == "codex_cli:gpt-5.6-sol:high"
    assert payload["dispatch_command"] == list(result.dispatch_command)
    assert payload["prompt_delivery"] == "argv"
    assert payload["snapshot_stale"] is False
    assert set(payload) == set(result.to_dict())


def test_a_stale_snapshot_is_reported_and_degrades_to_unknown(crews):
    """Staleness is a fact the resolution carries, not a silent pass."""
    old = NOW - timedelta(hours=6)
    result = resolve(
        crews,
        snap(openai(*HEALTHY), observed_at=old),
        crew="resolver-crew",
        role="envision",
    )
    assert result.snapshot_stale is True
    assert result.snapshot_observed_at == old.isoformat()
    assert result.headroom == "unknown"


# --------------------------------------------------------------------------
# purity
# --------------------------------------------------------------------------


def test_resolution_is_deterministic(crews):
    """Same inputs, same output — every time."""
    snapshot = snap(openai(*DEGRADED_BY_STATUS), gemini(*HEALTHY))
    first = resolve(crews, snapshot, crew="resolver-crew", role="envision", mode="flex")
    second = resolve(
        crews, snapshot, crew="resolver-crew", role="envision", mode="flex"
    )
    assert first == second
    assert first.to_dict() == second.to_dict()


def test_resolve_never_runs_a_subprocess(crews, monkeypatch):
    """The resolver decides from the snapshot; it never calls a harness."""

    def explode(*args: Any, **kwargs: Any):
        raise AssertionError("resolve() must not run a subprocess")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    result = resolve(
        crews, snap(openai(*HEALTHY)), crew="resolver-crew", role="envision"
    )
    assert result.worker_id == "codex_sol_high"
