"""Tests for the Auto-Orch crews loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from lee_llm_router.crews import (
    CREWS_FILE_ENV_VAR,
    FORBIDDEN_MODELS,
    NEVER_AUTOMATIC_MODELS,
    STAGE_NAMES,
    WORKER_PROVIDER_OVERRIDES,
    CrewsConfigError,
    Worker,
    is_forbidden,
    is_never_automatic,
    load_crews,
    resolve_crews_path,
    resolve_worker,
)

FIXTURE = Path(__file__).parent / "fixtures" / "crews.yaml"
LIVE_CREWS_FILE = Path("/home/lee/projects/auto-orch/config/crews.yaml")


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "crews.yaml"
    path.write_text(body, encoding="utf-8")
    return path


MINIMAL_WORKERS = """
workers:
  worker_a:
    command: "a {stage}"
    preflight_command: "a --preflight"
    timeout_seconds: 600
  worker_b:
    command: "b {stage}"
"""


def test_loads_fixture_workers_and_crews() -> None:
    config = load_crews(FIXTURE)

    assert config.path == FIXTURE
    assert list(config.crews) == ["test-flagship", "test-flex"]
    assert config.workers["codex_sol_high"].timeout_seconds == 900
    preflight = config.workers["codex_sol_high"].preflight_command
    assert preflight is not None
    assert preflight.endswith("codex_stage_worker.py --preflight")


def test_single_string_stage_normalizes_to_one_tuple() -> None:
    crew = load_crews(FIXTURE).crew("test-flagship")

    assert crew.eligible("ideate") == ("claude_opus5_high",)
    assert crew.primary("ideate") == "claude_opus5_high"
    assert crew.stages["ideate"].primary == "claude_opus5_high"


def test_list_stage_preserves_declared_order() -> None:
    crew = load_crews(FIXTURE).crew("test-flex")

    assert crew.eligible("envision") == (
        "codex_luna_max",
        "antigravity_gemini38_flash_high",
        "codex_sol_high",
    )
    assert crew.primary("envision") == "codex_luna_max"


def test_stage_order_is_preserved_from_file() -> None:
    crew = load_crews(FIXTURE).crew("test-flagship")

    assert list(crew.stages) == list(STAGE_NAMES)


def test_governed_routes_and_judge_model() -> None:
    crew = load_crews(FIXTURE).crew("test-flex")

    assert crew.governed["primary"].harness == "antigravity_cli"
    assert crew.governed["primary"].model == "gemini-3.8-flash-high"
    assert crew.governed["reviewer"].effort == "low"
    assert crew.governed["judge"].effort is None
    assert crew.judge_model == "claude-sonnet-5"


def test_env_var_resolves_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CREWS_FILE_ENV_VAR, str(FIXTURE))

    assert resolve_crews_path() == FIXTURE
    assert load_crews().path == FIXTURE


def test_explicit_path_beats_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CREWS_FILE_ENV_VAR, str(tmp_path / "ignored.yaml"))

    assert resolve_crews_path(FIXTURE) == FIXTURE


def test_default_path_used_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CREWS_FILE_ENV_VAR, raising=False)

    resolved = resolve_crews_path()

    assert resolved.is_absolute()
    assert resolved.name == "crews.yaml"


def test_unknown_worker_is_an_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        MINIMAL_WORKERS + """
crews:
  broken:
    stages:
      envision: worker_a
      ideate: nope_not_a_worker
""",
    )

    with pytest.raises(CrewsConfigError, match="unknown worker"):
        load_crews(path)


def test_bad_stage_type_is_an_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        MINIMAL_WORKERS + """
crews:
  broken:
    stages:
      envision: {harness: codex_cli}
""",
    )

    with pytest.raises(CrewsConfigError, match="must be a worker id string"):
        load_crews(path)


def test_empty_stage_list_is_an_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        MINIMAL_WORKERS + """
crews:
  broken:
    stages:
      envision: []
""",
    )

    with pytest.raises(CrewsConfigError, match="empty worker list"):
        load_crews(path)


def test_non_string_stage_list_entry_is_an_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        MINIMAL_WORKERS + """
crews:
  broken:
    stages:
      envision: [worker_a, 7]
""",
    )

    with pytest.raises(CrewsConfigError, match="is not a string"):
        load_crews(path)


def test_unknown_stage_name_is_an_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        MINIMAL_WORKERS + """
crews:
  broken:
    stages:
      envision: worker_a
      hallucinate: worker_b
""",
    )

    with pytest.raises(CrewsConfigError, match="unknown stage 'hallucinate'"):
        load_crews(path)


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(CrewsConfigError, match="crews file not found"):
        load_crews(tmp_path / "absent.yaml")


def test_missing_workers_section_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "crews:\n  x:\n    stages:\n      envision: a\n")

    with pytest.raises(CrewsConfigError, match="missing top-level 'workers'"):
        load_crews(path)


def test_missing_crews_section_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, MINIMAL_WORKERS)

    with pytest.raises(CrewsConfigError, match="missing top-level 'crews'"):
        load_crews(path)


def test_unknown_crew_lookup_is_an_error() -> None:
    config = load_crews(FIXTURE)

    with pytest.raises(CrewsConfigError, match="unknown crew"):
        config.crew("no-such-crew")


def test_missing_stage_lookup_is_an_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        MINIMAL_WORKERS + """
crews:
  partial:
    stages:
      envision: worker_a
""",
    )
    crew = load_crews(path).crew("partial")

    with pytest.raises(CrewsConfigError, match="has no stage 'author'"):
        crew.eligible("author")


@pytest.mark.skipif(
    not LIVE_CREWS_FILE.is_file(), reason="live Auto-Orch crews file not present"
)
def test_live_crews_file_has_fourteen_complete_crews() -> None:
    config = load_crews(LIVE_CREWS_FILE)

    assert len(config.crews) == 14
    for name, crew in config.crews.items():
        assert set(crew.stages) == set(STAGE_NAMES), name
        for stage in STAGE_NAMES:
            assert crew.primary(stage) in config.workers, (name, stage)


def _worker(worker_id: str, command: str) -> Worker:
    return Worker(id=worker_id, command=command)


CODEX_COMMAND = (
    "/usr/bin/env CODEX_STAGE_WORKER_BINARY=/x/bin/codex "
    "CODEX_STAGE_WORKER_MODEL=gpt-5.6-sol "
    "CODEX_STAGE_WORKER_REASONING_EFFORT=high "
    "python3 /x/codex_stage_worker.py {stage} {prompt_path} {response_path}"
)
CLAUDE_COMMAND = (
    "/usr/bin/env CLAUDE_STAGE_WORKER_BINARY=/x/bin/claude "
    "CLAUDE_STAGE_WORKER_MODEL=claude-opus-5 "
    "CLAUDE_STAGE_WORKER_EFFORT=high "
    "python3 /x/claude_stage_worker.py {stage} {prompt_path} {response_path}"
)
OPENCODE_COMMAND = (
    "/usr/bin/env OPENCODE_STAGE_WORKER_BINARY=/x/bin/opencode "
    "OPENCODE_STAGE_WORKER_MODEL=opencode-go/deepseek-v4-flash "
    "OPENCODE_STAGE_WORKER_AGENT=build OPENCODE_STAGE_WORKER_DIR=/tmp "
    "python3 /x/opencode_stage_worker.py {stage} {prompt_path} {response_path}"
)
ANTIGRAVITY_COMMAND = (
    "/usr/bin/env ANTIGRAVITY_STAGE_WORKER_BINARY=/x/bin/agy "
    "ANTIGRAVITY_STAGE_WORKER_MODEL=gemini-3.8-flash-high "
    "ANTIGRAVITY_STAGE_WORKER_EFFORT=high "
    "python3 /x/antigravity_stage_worker.py {stage} {prompt_path} {response_path}"
)


def test_resolve_worker_codex_prefix() -> None:
    resolved = resolve_worker(_worker("codex_sol_high", CODEX_COMMAND))

    assert resolved.provider == "codex_cli"
    assert resolved.model == "gpt-5.6-sol"
    assert resolved.effort == "high"
    assert resolved.harness_binary == "/x/bin/codex"
    assert resolved.dispatch_command == CODEX_COMMAND


def test_resolve_worker_claude_prefix() -> None:
    resolved = resolve_worker(_worker("claude_opus5_high", CLAUDE_COMMAND))

    assert resolved.provider == "claude_code_cli"
    assert resolved.model == "claude-opus-5"
    assert resolved.effort == "high"


def test_resolve_worker_opencode_prefix_without_effort() -> None:
    resolved = resolve_worker(_worker("opencode_deepseek", OPENCODE_COMMAND))

    assert resolved.provider == "opencode_cli"
    assert resolved.model == "opencode-go/deepseek-v4-flash"
    assert resolved.effort is None


def test_resolve_worker_antigravity_prefix() -> None:
    resolved = resolve_worker(_worker("agy_flash_high", ANTIGRAVITY_COMMAND))

    assert resolved.provider == "antigravity_cli"
    assert resolved.model == "gemini-3.8-flash-high"
    assert resolved.effort == "high"


def test_worker_provider_override_wins_over_parsing(monkeypatch) -> None:
    monkeypatch.setitem(
        WORKER_PROVIDER_OVERRIDES,
        "codex_sol_high",
        ("omp_cli", "pinned-model", "low"),
    )

    resolved = resolve_worker(_worker("codex_sol_high", CODEX_COMMAND))

    assert resolved.provider == "omp_cli"
    assert resolved.model == "pinned-model"
    assert resolved.effort == "low"
    assert resolved.harness_binary is None


def test_resolve_worker_unknown_prefix_raises() -> None:
    command = "/usr/bin/env WEIRD_STAGE_WORKER_MODEL=x python3 /x/weird_stage_worker.py"

    with pytest.raises(CrewsConfigError, match="unknown stage-worker prefix"):
        resolve_worker(_worker("weird", command))


def test_resolve_worker_missing_model_raises() -> None:
    command = (
        "/usr/bin/env CODEX_STAGE_WORKER_BINARY=/x/bin/codex "
        "python3 /x/codex_stage_worker.py"
    )

    with pytest.raises(CrewsConfigError, match="CODEX_STAGE_WORKER_MODEL"):
        resolve_worker(_worker("codex_no_model", command))


def test_resolve_worker_no_env_vars_raises() -> None:
    with pytest.raises(CrewsConfigError, match="declares no"):
        resolve_worker(_worker("legacy", "run-sol {stage}"))


def test_never_automatic_and_forbidden_helpers() -> None:
    assert "claude-fable-5-1" in NEVER_AUTOMATIC_MODELS
    assert "gemini-3.1-pro" in FORBIDDEN_MODELS
    assert is_never_automatic("claude-opus-5") is True
    assert is_never_automatic("gpt-5.6-sol") is False
    assert is_never_automatic(None) is False
    assert is_forbidden("gemini-3.1-pro") is True
    assert is_forbidden("gemini-3.8-flash-high") is False
    assert is_forbidden(None) is False


def test_every_fixture_worker_resolves() -> None:
    config = load_crews(FIXTURE)

    for worker in config.workers.values():
        assert resolve_worker(worker).model


@pytest.mark.skipif(
    not LIVE_CREWS_FILE.is_file(), reason="live Auto-Orch crews file not present"
)
def test_live_crews_file_workers_all_resolve() -> None:
    config = load_crews(LIVE_CREWS_FILE)

    for crew in config.crews.values():
        for stage in crew.stages.values():
            for worker_id in stage.workers:
                resolved = resolve_worker(config.workers[worker_id])
                assert resolved.provider
                assert resolved.model


OMP_COMMAND = (
    "/usr/bin/env OMP_STAGE_WORKER_BINARY=/x/bin/omp "
    "OMP_STAGE_WORKER_MODEL=gemini-3.8-flash-high "
    "python3 /x/omp_stage_worker.py {stage} {prompt_path} {response_path}"
)


def test_resolve_worker_omp_prefix() -> None:
    resolved = resolve_worker(_worker("omp_flash_high", OMP_COMMAND))

    assert resolved.provider == "omp_cli"
    assert resolved.model == "gemini-3.8-flash-high"
    assert resolved.effort is None
    assert resolved.harness_binary == "/x/bin/omp"


def test_omp_prefix_is_registered() -> None:
    from lee_llm_router.crews import WORKER_ENV_PREFIX_PROVIDERS

    assert WORKER_ENV_PREFIX_PROVIDERS["OMP"] == "omp_cli"
