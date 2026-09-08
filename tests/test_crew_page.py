"""Focused tests for Crew Resolver Sprint 5's pure evidence core."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import pytest

from lee_llm_router.availability import AvailabilitySnapshot, parse_availability
from lee_llm_router.crew_page import (
    BENCHMARK_ROLES_BY_RESOLVER_ROLE,
    BENCHMARK_SCHEMA,
    BenchmarkEvidenceError,
    WorkerIdentity,
    aggregate_worker_metrics,
    load_benchmark_evidence,
    match_worker_evidence,
    render_crew_page,
    select_proposals,
    worker_key_for,
    worker_key_for_identity,
    worker_key_for_worker,
    write_crew_page,
)
from lee_llm_router.crews import Crew, CrewsConfig, Stage, Worker, load_crews

FIXTURE_CREWS = Path(__file__).parent / "fixtures" / "crews.yaml"


def _raw_row(
    model: str,
    harness: str,
    role: str = "coder",
    task_key: str = "task-a@v1",
    run_id: str = "run-1",
    *,
    effort: str | None = "high",
    accepted: bool = False,
    score: int | None = 80,
    cost: str | None = "0.50",
    model_family: str = "Display name that is not an identity key",
) -> dict[str, object]:
    provider = {
        "codex": "codex",
        "pi": "codex",
        "claude": "claude",
        "agy": "agy",
        "opencode": "openrouter",
        "omp": "openrouter",
    }[harness]
    key = f"{model}|{harness}|{effort or ''}"
    return {
        "acceptance": "accepted" if accepted else "not_accepted",
        "accepted_count": 1 if accepted else 0,
        "cost_low_usd": cost,
        "cost_high_usd": cost,
        "role": role,
        "run_count": 1,
        "run_ids": [run_id],
        "score_100": score,
        "task_key": task_key,
        "worker_key": key,
        "worker": {
            "effort": effort,
            "harness": harness,
            "model": model,
            "model_family": model_family,
            "provider": provider,
            "vendor": "synthetic",
        },
    }


def _write_evidence(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "staffing-evidence.json"
    path.write_text(
        json.dumps({"schema_version": BENCHMARK_SCHEMA, "rows": rows}),
        encoding="utf-8",
    )
    return path


def _codex_worker(worker_id: str, model: str, effort: str) -> Worker:
    command = (
        "/usr/bin/env CODEX_STAGE_WORKER_BINARY=/x/bin/codex "
        f"CODEX_STAGE_WORKER_MODEL={model} "
        f"CODEX_STAGE_WORKER_REASONING_EFFORT={effort} "
        "python3 worker.py {stage} {prompt_path} {response_path}"
    )
    return Worker(id=worker_id, command=command)


def _omp_worker(worker_id: str, model: str) -> Worker:
    command = (
        "/usr/bin/env OMP_STAGE_WORKER_BINARY=/x/bin/omp "
        f"OMP_STAGE_WORKER_MODEL={model} "
        "python3 worker.py {stage} {prompt_path} {response_path}"
    )
    return Worker(id=worker_id, command=command)


def _claude_worker(worker_id: str, model: str, effort: str) -> Worker:
    command = (
        "/usr/bin/env CLAUDE_STAGE_WORKER_BINARY=/x/bin/claude "
        f"CLAUDE_STAGE_WORKER_MODEL={model} "
        f"CLAUDE_STAGE_WORKER_EFFORT={effort} "
        "python3 worker.py {stage} {prompt_path} {response_path}"
    )
    return Worker(id=worker_id, command=command)


def _config(workers: dict[str, Worker], role: str = "author") -> CrewsConfig:
    current = next(iter(workers))
    return CrewsConfig(
        workers=workers,
        crews={
            "crew-a": Crew(
                name="crew-a",
                description="synthetic",
                stages={role: Stage(role, (current,))},
                governed={},
            )
        },
        path=Path("synthetic-crews.yaml"),
    )


def test_missing_benchmark_is_an_explicit_absence(tmp_path: Path) -> None:
    evidence = load_benchmark_evidence(tmp_path / "missing.json")

    assert evidence.present is False
    assert evidence.available is False
    assert evidence.absent is True
    assert evidence.rows == ()
    assert (
        select_proposals(
            _config({"current": _codex_worker("current", "gpt-5.6-sol", "high")}),
            evidence,
        )
        == ()
    )


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("{not json", "malformed JSON"),
        (json.dumps({"schema_version": "wrong", "rows": []}), "schema_version"),
        (json.dumps({"schema_version": BENCHMARK_SCHEMA, "rows": [{}]}), "worker_key"),
    ],
)
def test_present_bad_evidence_fails_closed(
    tmp_path: Path, content: str, match: str
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(BenchmarkEvidenceError, match=match):
        load_benchmark_evidence(path)


def test_present_non_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkEvidenceError, match="not a file"):
        load_benchmark_evidence(tmp_path)


def test_worker_key_mapping_is_explicit_and_ignores_display_names() -> None:
    cases = [
        ("codex_cli", "gpt-5.6-sol", "high", None, "gpt-5.6-sol|codex|high"),
        ("openai", "gpt-5.6-luna", "xhigh", "pi", "gpt-5.6-luna|pi|xhigh"),
        (
            "claude_code_cli",
            "claude-fable-5-1",
            "low",
            None,
            "claude-fable-5-1|claude|low",
        ),
        (
            "antigravity_cli",
            "gemini-3.8-flash-high",
            "high",
            None,
            "gemini-3.8-flash-high|agy|high",
        ),
        (
            "opencode_cli",
            "z-ai/glm-5.3-flash",
            "max",
            None,
            "z-ai/glm-5.3-flash|opencode|max",
        ),
        (
            "omp_cli",
            "qwen/qwen3.8-27b",
            "xhigh",
            None,
            "qwen/qwen3.8-27b|omp|xhigh",
        ),
    ]
    for provider, model, effort, harness, expected in cases:
        assert worker_key_for_identity(provider, model, effort, harness) == expected

    assert (
        worker_key_for(WorkerIdentity("openai", "gpt-5.6-luna", "xhigh", "pi"))
        == "gpt-5.6-luna|pi|xhigh"
    )
    assert worker_key_for_identity("unknown-display-name", "gpt-5.6-sol") is None


def test_benchmark_roles_only_map_declared_stages() -> None:
    assert set(BENCHMARK_ROLES_BY_RESOLVER_ROLE) == {
        "author",
        "envision",
        "ideate",
        "reconsider",
        "score",
    }


def test_evidence_matching_does_not_use_model_family_display_name(
    tmp_path: Path,
) -> None:
    row = _raw_row("gpt-5.6-sol", "codex", model_family="Preferred Sol display")
    evidence = load_benchmark_evidence(_write_evidence(tmp_path, [row]))

    assert len(match_worker_evidence(evidence, "Preferred Sol display")) == 0
    identity = WorkerIdentity("codex", "gpt-5.6-sol", "high", "codex")
    assert len(match_worker_evidence(evidence, identity)) == 1


def test_metrics_keep_unknowns_and_use_accepted_cost_only(tmp_path: Path) -> None:
    rows = [
        _raw_row(
            "gpt-5.6-sol",
            "codex",
            task_key="task-a@v1",
            run_id="run-z",
            score=82,
            cost="0.01",
        ),
        _raw_row(
            "gpt-5.6-sol",
            "codex",
            task_key="task-b@v1",
            run_id="run-a",
            accepted=True,
            score=None,
            cost="0.50",
        ),
        _raw_row(
            "gpt-5.6-sol",
            "codex",
            task_key="task-c@v1",
            run_id="run-m",
            accepted=True,
            score=91,
            cost=None,
        ),
    ]
    evidence = load_benchmark_evidence(_write_evidence(tmp_path, rows))
    metrics = aggregate_worker_metrics(evidence, "gpt-5.6-sol|codex|high")

    assert metrics.best_score == 91
    assert metrics.cost_to_accept == 0.50
    assert metrics.cost_to_accept_low_usd == 0.50
    assert metrics.total_run_count == 3
    assert metrics.task_count == 3
    assert metrics.one_task is False
    assert metrics.run_ids == ("run-a", "run-m", "run-z")
    unknown = aggregate_worker_metrics(evidence, "no-such|codex|")
    assert unknown.best_score is None
    assert unknown.cost_to_accept is None
    assert unknown.total_run_count is None
    assert unknown.one_task is None


def test_grouped_retry_evidence_tracks_acceptance_without_reusing_rejected_cost(
    tmp_path: Path,
) -> None:
    row = _raw_row(
        "gpt-5.6-sol",
        "codex",
        run_id="first-attempt",
        cost="0.13",
    )
    row.update(
        {
            "acceptance": "not_accepted",
            "accepted_count": 1,
            "run_count": 2,
            "run_ids": ["first-attempt", "retry"],
        }
    )
    evidence_path = _write_evidence(tmp_path, [row])
    evidence = load_benchmark_evidence(evidence_path)

    assert evidence.rows[0].accepted is True
    metrics = aggregate_worker_metrics(evidence, "gpt-5.6-sol|codex|high")
    assert metrics.accepted is True
    assert metrics.accepted_run_count == 1
    assert metrics.total_run_count == 2
    assert metrics.cost_to_accept is None
    assert metrics.cost_to_accept_low_usd is None
    assert metrics.cost_to_accept_high_usd is None

    availability_path = tmp_path / "availability.json"
    availability_path.write_text(
        json.dumps(
            {
                "observed_at": "2025-01-01T00:00:00+00:00",
                "subscriptions": [],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "crews.html"
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "crews",
                "page",
                "--out",
                str(output),
                "--crews-file",
                str(FIXTURE_CREWS),
                "--availability-file",
                str(availability_path),
                "--benchmark-file",
                str(evidence_path),
            ]
        )

    assert exc_info.value.code == 0
    assert "Cost-to-accept</dt><dd>unknown" in output.read_text(encoding="utf-8")


def test_proposals_fail_closed_without_authoritative_boundaries(
    tmp_path: Path,
) -> None:
    workers = {
        "current": _codex_worker("current", "gpt-5.6-sol", "high"),
        "candidate": _codex_worker("candidate", "gpt-5.6-sol", "medium"),
    }
    config = _config(workers)
    rows = [
        _raw_row("gpt-5.6-sol", "codex", run_id="current", score=70),
        _raw_row(
            "gpt-5.6-sol",
            "codex",
            effort="medium",
            run_id="candidate",
            accepted=True,
            score=95,
        ),
    ]
    evidence = load_benchmark_evidence(_write_evidence(tmp_path, rows))
    proposals = select_proposals(config, evidence)

    # The evidence proves identity, role, task, and acceptance, but neither
    # model tier nor vendor-independence boundary.  No proposal is permitted.
    assert proposals == ()

    rejected = rows[1].copy()
    rejected["acceptance"] = "not_accepted"
    rejected["accepted_count"] = 0
    no_acceptance = load_benchmark_evidence(
        _write_evidence(tmp_path, [rows[0], rejected])
    )
    assert select_proposals(config, no_acceptance) == ()


def test_proposal_requires_same_role_and_task(tmp_path: Path) -> None:
    workers = {
        "current": _codex_worker("current", "gpt-5.6-sol", "high"),
        "candidate": _codex_worker("candidate", "gpt-5.6-sol", "medium"),
    }
    config = _config(workers)
    evidence = load_benchmark_evidence(
        _write_evidence(
            tmp_path,
            [
                _raw_row("gpt-5.6-sol", "codex", run_id="current"),
                _raw_row(
                    "gpt-5.6-sol",
                    "codex",
                    effort="medium",
                    role="planner",
                    run_id="wrong-role",
                    accepted=True,
                ),
                _raw_row(
                    "gpt-5.6-sol",
                    "codex",
                    effort="medium",
                    task_key="different-task@v1",
                    run_id="wrong-task",
                    accepted=True,
                ),
            ],
        )
    )

    assert select_proposals(config, evidence) == ()


def test_cross_vendor_candidate_is_not_proposed_without_boundary_proof(
    tmp_path: Path,
) -> None:
    workers = {
        "current": _codex_worker("current", "gpt-5.6-sol", "high"),
        "candidate": _claude_worker("candidate", "claude-sonnet-5", "high"),
    }
    config = _config(workers)
    evidence = load_benchmark_evidence(
        _write_evidence(
            tmp_path,
            [
                _raw_row("gpt-5.6-sol", "codex", run_id="current"),
                _raw_row(
                    "claude-sonnet-5",
                    "claude",
                    run_id="candidate",
                    accepted=True,
                ),
            ],
        )
    )

    # A channel/provider distinction is not authoritative proof of vendor
    # independence, so the candidate is fail-closed.
    assert select_proposals(config, evidence) == ()


def test_never_automatic_candidate_is_never_proposed(tmp_path: Path) -> None:
    workers = {
        "current": _claude_worker("current", "claude-opus-5", "high"),
        "candidate": _claude_worker("candidate", "claude-fable-5-1", "high"),
    }
    config = _config(workers)
    evidence = load_benchmark_evidence(
        _write_evidence(
            tmp_path,
            [
                _raw_row("claude-opus-5", "codex", run_id="current"),
                _raw_row(
                    "claude-fable-5-1",
                    "claude",
                    effort="high",
                    run_id="candidate",
                    accepted=True,
                ),
            ],
        )
    )
    assert select_proposals(config, evidence) == ()


def test_role_scoped_candidate_is_excluded_on_coding_stage(
    tmp_path: Path,
) -> None:
    workers = {
        "current": _codex_worker("current", "gpt-5.6-luna", "max"),
        "candidate": _omp_worker("candidate", "gemini-3.1-pro"),
    }
    config = _config(workers)
    evidence = load_benchmark_evidence(
        _write_evidence(
            tmp_path,
            [
                _raw_row("gpt-5.6-luna", "codex", effort="max", run_id="current"),
                _raw_row(
                    "gemini-3.1-pro",
                    "omp",
                    effort=None,
                    run_id="candidate",
                    accepted=True,
                ),
            ],
        )
    )
    assert select_proposals(config, evidence) == ()


def test_multiple_crews_have_no_proposals_without_boundary_proof(
    tmp_path: Path,
) -> None:
    first = _codex_worker("first", "gpt-5.6-sol", "high")
    second = _codex_worker("second", "gpt-5.6-sol", "medium")
    config = CrewsConfig(
        workers={"first": first, "second": second},
        crews={
            "z-crew": Crew(
                name="z-crew",
                description="synthetic",
                stages={"author": Stage("author", ("first",))},
                governed={},
            ),
            "a-crew": Crew(
                name="a-crew",
                description="synthetic",
                stages={"author": Stage("author", ("first",))},
                governed={},
            ),
        },
        path=Path("synthetic-crews.yaml"),
    )
    evidence = load_benchmark_evidence(
        _write_evidence(
            tmp_path,
            [
                _raw_row("gpt-5.6-sol", "codex", run_id="current"),
                _raw_row(
                    "gpt-5.6-sol",
                    "codex",
                    effort="medium",
                    run_id="candidate",
                    accepted=True,
                ),
            ],
        )
    )

    assert select_proposals(config, evidence) == ()


def test_repository_fixture_workers_cover_named_mapping_families() -> None:
    config = load_crews(FIXTURE_CREWS)

    assert worker_key_for_worker(config.workers["codex_sol_high"]) == (
        "gpt-5.6-sol|codex|high"
    )
    assert worker_key_for_worker(config.workers["claude_opus5_high"]) == (
        "claude-opus-5|claude|high"
    )
    assert (
        worker_key_for_worker(config.workers["antigravity_gemini38_flash_high"])
        == "gemini-3.8-flash-high|agy|high"
    )


class _PageParser(HTMLParser):
    """Minimal parser used to ensure the projection is structurally readable."""

    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)


def _page_availability() -> AvailabilitySnapshot:
    return parse_availability(
        {
            "observed_at": "2025-01-01T00:00:00+00:00",
            "subscriptions": [
                {
                    "provider": "OpenAI/Codex",
                    "bucket": "Weekly limit",
                    "status": "COLD",
                    "remaining_pct": 80,
                }
            ],
        },
        now=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
    )


def test_render_page_projects_order_metrics_escaping_and_appendix(
    tmp_path: Path,
) -> None:
    worker = _codex_worker("worker<&", "gpt-5.6-sol", "high")
    config = CrewsConfig(
        workers={"worker<&": worker},
        crews={
            "crew<&": Crew(
                name="crew<&",
                description="Purpose <unsafe>",
                stages={"author": Stage("author", ("worker<&",))},
                governed={},
            )
        },
        path=tmp_path / "not-rendered.yaml",
    )
    evidence = load_benchmark_evidence(
        _write_evidence(
            tmp_path,
            [
                _raw_row(
                    "gpt-5.6-sol",
                    "codex",
                    run_id="run<&",
                    task_key="task<&",
                    accepted=True,
                )
            ],
        )
    )

    page = render_crew_page(config, _page_availability(), evidence)
    parser = _PageParser()
    parser.feed(page)
    parser.close()

    assert parser.errors == []
    assert "crew&lt;&amp;" in page
    assert "Purpose &lt;unsafe&gt;" in page
    assert "healthy" in page
    assert "2025-01-01T00:00:00+00:00" in page
    assert "Stale: no" in page
    assert "Best score" in page
    assert "80" in page
    assert "0.50" in page
    assert "1" in page
    assert "one task" in page
    main_prose = page.split('<section class="evidence-appendix"', 1)[0]
    assert "Provider: <code>OpenAI</code>" in main_prose
    assert "_cli" not in main_prose
    assert "run&lt;&amp;" not in main_prose
    assert "run&lt;&amp;" in page.split('<section class="evidence-appendix"', 1)[1]
    assert "No proposals qualify." in page
    assert "<script" not in page.lower()
    assert "href=" not in page.lower()
    assert "src=" not in page.lower()
    assert "@media (prefers-color-scheme: dark)" in page
    assert "@media (max-width: 390px)" in page


def test_render_page_sanitizes_provider_tokens_in_every_crew_purpose() -> None:
    config = CrewsConfig(
        workers={"current": _codex_worker("current", "gpt-5.6-sol", "high")},
        crews={
            "mixed": Crew(
                name="mixed",
                description=(
                    "codex_cli has no read-only judge adapter; "
                    "claude_code_cli handles review."
                ),
                stages={"author": Stage("author", ("current",))},
                governed={},
            )
        },
        path=Path("synthetic-crews.yaml"),
    )

    page = render_crew_page(
        config,
        _page_availability(),
        load_benchmark_evidence(None),
    )
    main_prose = page.split('<section class="evidence-appendix"', 1)[0]

    assert "OpenAI has no read-only judge adapter" in main_prose
    assert "Anthropic handles review." in main_prose
    for raw_provider in (
        "codex_cli",
        "claude_code_cli",
        "antigravity_cli",
        "opencode_cli",
        "omp_cli",
    ):
        assert raw_provider not in main_prose


def test_render_page_without_benchmark_has_unknown_metrics() -> None:
    config = _config({"current": _codex_worker("current", "gpt-5.6-sol", "high")})
    page = render_crew_page(
        config,
        _page_availability(),
        load_benchmark_evidence(None),
    )

    assert "No benchmark evidence yet." in page
    assert page.count("unknown") >= 4
    assert "one task" not in page


def test_render_page_marks_role_scoped_worker_on_coding_stage() -> None:
    config = _config({"role-scoped": _omp_worker("role-scoped", "gemini-3.1-pro")})

    page = render_crew_page(
        config,
        _page_availability(),
        load_benchmark_evidence(None),
    )

    assert "planning/review only" in page


def test_write_page_uses_only_the_caller_selected_output_path(tmp_path: Path) -> None:
    config = _config({"current": _codex_worker("current", "gpt-5.6-sol", "high")})
    output = tmp_path / "page.html"

    written = write_crew_page(
        output,
        config,
        _page_availability(),
        load_benchmark_evidence(None),
    )

    assert written == output
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert list(tmp_path.glob(".page.html.*.tmp")) == []
