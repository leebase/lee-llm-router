"""Tests for the P0-5b ``catalog explain`` CLI (doctor.py).

The catalog under test is a scratch copy of the committed ``config/staffing``
documents (copied read-only into ``tmp_path``; schema and pinned pricing
sources are read in place, never modified), and the availability snapshot is
a scratch JSON file written by the test. No provider call, no prompt, no
probability, no ladder, no model choice — display ordering by marginal
price only, as the P0-5b packet expressly allows.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from lee_llm_router.staffing import load_staffing_catalog

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"

FABLE_ROUTE = "claude-claude-fable-5-1-high-anthropic-sub"
GLM_OPENROUTER_ROUTE = "pi-z-ai-glm-5-3-flash-openrouter"
MIMO_ROUTE = "opencode-opencode-go-mimo-v2-5-opencode-go"
SOL_LOW_ROUTE = "codex-gpt-5-6-sol-low-openai-sub"

IMPL_CLASS = "impl/deterministic/none/s/python"

#: Exact per-route JSON field set (no model/harness/provider/machinery keys).
ROUTE_JSON_KEYS = {
    "route_id",
    "eligible",
    "channel",
    "badge",
    "headroom",
    "health",
    "marginal_input_usd_per_token",
    "marginal_output_usd_per_token",
    "replacement_input_usd_per_token",
    "replacement_output_usd_per_token",
    "reasons",
}

MACHINERY_MARKERS = (
    "dispatch_template",
    "usage_capture",
    "openrouter-snapshot",
    "rate_table",
    "schema",
    "worker",
    '"model"',
    '"harness"',
    '"effort"',
    '"source"',
    '"status_reason"',
    "Traceback",
)


@pytest.fixture
def catalog_dir(tmp_path: Path) -> Path:
    """Scratch catalog: the committed six documents, nothing else."""
    dest = tmp_path / "catalog"
    shutil.copytree(
        REPO_CONFIG_DIR,
        dest,
        ignore=shutil.ignore_patterns("schema", "pricing", "__pycache__"),
    )
    return dest


def _write_snapshot(
    path: Path,
    *,
    codex: tuple[str, int] | None = ("ON TRACK", 80),
    anthropic: tuple[str, int] | None = ("COLD", 90),
    gemini: tuple[str, int] | None = ("ON TRACK", 60),
    opencode: tuple[str, int] | None = ("ON TRACK", 50),
) -> Path:
    """Write a fresh scratch availability snapshot file and return its path."""
    subscriptions = []
    for provider, bucket, value in (
        ("OpenAI/Codex", "Weekly limit", codex),
        ("Anthropic/Claude", "Current session", anthropic),
        ("Gemini/agy", "Gemini models", gemini),
        ("OpenCode/Go", "Weekly", opencode),
    ):
        if value is not None:
            subscriptions.append(
                {
                    "provider": provider,
                    "bucket": bucket,
                    "status": value[0],
                    "remaining_pct": value[1],
                }
            )
    observed_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload = {
        "host": "explain-test",
        "observed_at": observed_at.isoformat(),
        "subscriptions": subscriptions,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run_explain(capsys: pytest.CaptureFixture[str], *argv: str):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["catalog", "explain", *argv])
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    return exc_info.value.code, captured


def _explain_json_run(
    capsys: pytest.CaptureFixture[str],
    catalog_dir: Path,
    snapshot: Path,
    at: str | None = "2026-09-15",
    *extra: str,
) -> tuple[int, dict]:
    argv = ["--role", "impl", "--class", IMPL_CLASS]
    if at is not None:
        argv += ["--at", at]
    code, captured = _run_explain(
        capsys,
        *argv,
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--json",
        *extra,
    )
    return code, json.loads(captured.out)


def _by_route(payload: dict, route_id: str) -> dict:
    return next(r for r in payload["routes"] if r["route_id"] == route_id)


# ---------------------------------------------------------------------------
# P0-5 acceptance reproduced through the CLI: exhausted Anthropic channel
# ---------------------------------------------------------------------------


def test_explain_reproduces_p0_5_acceptance(tmp_path, catalog_dir, capsys):
    """Canonical impl class; Anthropic exhausted -> Fable's combined reason."""
    snapshot = _write_snapshot(tmp_path / "availability.json", anthropic=("HOT", 0))
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0
    assert payload["role"] == "impl"
    assert payload["class_key"] == IMPL_CLASS
    assert payload["at"] == "2026-09-15"

    routes = payload["routes"]
    assert len(routes) == len(load_staffing_catalog(catalog_dir).routes.routes)
    for route in routes:
        assert set(route) == ROUTE_JSON_KEYS

    fable = _by_route(payload, FABLE_ROUTE)
    assert fable["eligible"] is False
    assert fable["reasons"] == ["never_automatic", "channel exhausted"]
    assert "; ".join(fable["reasons"]) == "never_automatic; channel exhausted"
    assert fable["channel"] == "anthropic-sub"
    assert fable["badge"] == "HOT"
    assert fable["health"] == "exhausted"
    assert fable["headroom"] == 0.0
    assert fable["marginal_input_usd_per_token"] is not None


def test_explain_display_sorted_by_marginal_price(tmp_path, catalog_dir, capsys):
    """Priced rows ascend by marginal price; unpriced rows trail, id-broken."""
    snapshot = _write_snapshot(tmp_path / "availability.json", anthropic=("HOT", 0))
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0

    routes = payload["routes"]
    priced = [r for r in routes if r["marginal_input_usd_per_token"] is not None]
    unpriced = [r for r in routes if r["marginal_input_usd_per_token"] is None]
    assert unpriced == routes[len(priced) :]  # unpriced strictly last
    keys = [
        (
            r["marginal_input_usd_per_token"],
            r["marginal_output_usd_per_token"],
            r["route_id"],
        )
        for r in priced
    ]
    assert keys == sorted(keys)


def test_explain_excluded_and_unpriced_routes_stay_visible(
    tmp_path, catalog_dir, capsys
):
    """Every catalog route appears, including the unpriced exact id."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0

    routes = payload["routes"]
    mimo = _by_route(payload, MIMO_ROUTE)
    assert mimo["eligible"] is False
    assert "route status unpriced" in mimo["reasons"]
    assert "pricing unavailable" in mimo["reasons"]
    assert mimo["marginal_input_usd_per_token"] is None
    assert mimo["replacement_output_usd_per_token"] is None
    assert routes[-1]["route_id"] == MIMO_ROUTE


def test_explain_table_lists_required_columns_and_fable_reason(
    tmp_path, catalog_dir, capsys
):
    """Human table carries every committed field; no machinery labels."""
    snapshot = _write_snapshot(tmp_path / "availability.json", anthropic=("HOT", 0))
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 0

    out = captured.out
    for header in (
        "ROUTE ID",
        "STATUS",
        "CHANNEL",
        "BADGE",
        "HEADROOM",
        "HEALTH",
        "MARG IN $/TOK",
        "MARG OUT $/TOK",
        "REPL IN $/TOK",
        "REPL OUT $/TOK",
        "REASONS",
    ):
        assert header in out

    fable_line = next(line for line in out.splitlines() if FABLE_ROUTE in line)
    assert "excluded" in fable_line
    assert "anthropic-sub" in fable_line
    assert "HOT" in fable_line
    assert "0%" in fable_line
    assert "exhausted" in fable_line
    assert "never_automatic; channel exhausted" in fable_line

    for marker in MACHINERY_MARKERS:
        assert marker not in out


def test_explain_json_has_no_machinery_leakage(tmp_path, catalog_dir, capsys):
    """JSON exposes no model/harness/provider/machinery labels."""
    snapshot = _write_snapshot(tmp_path / "availability.json", anthropic=("HOT", 0))
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0
    text = json.dumps(payload)
    for marker in MACHINERY_MARKERS:
        assert marker not in text


# ---------------------------------------------------------------------------
# Per-channel marginal pricing: each row's marginal price uses the badge
# derived for its own channel from the snapshot (no report-wide badge).
# ---------------------------------------------------------------------------


def test_explain_marginal_price_uses_per_channel_badge(tmp_path, catalog_dir, capsys):
    """HOT rows price at 0.75x, ON TRACK at 0.25x, no-badge rows at 1.0x."""
    snapshot = _write_snapshot(
        tmp_path / "availability.json",
        codex=("ON TRACK", 80),
        anthropic=("HOT", 80),
        gemini=None,
        opencode=None,
    )
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0

    sol = _by_route(payload, SOL_LOW_ROUTE)
    assert sol["badge"] == "ON TRACK"
    assert sol["marginal_input_usd_per_token"] == pytest.approx(
        0.25 * sol["replacement_input_usd_per_token"]
    )

    fable = _by_route(payload, FABLE_ROUTE)
    assert fable["badge"] == "HOT"
    assert fable["marginal_input_usd_per_token"] == pytest.approx(
        0.75 * fable["replacement_input_usd_per_token"]
    )
    # Exclusion reasons and the replacement price are preserved.
    assert fable["reasons"] == ["never_automatic"]
    assert fable["replacement_input_usd_per_token"] > 0.0

    # openrouter (metered, no quota record) carries no badge: fail closed
    # to the committed NO DATA multiplier (1.0) — marginal == replacement.
    glm = _by_route(payload, GLM_OPENROUTER_ROUTE)
    assert glm["badge"] is None
    assert glm["marginal_input_usd_per_token"] == pytest.approx(
        glm["replacement_input_usd_per_token"]
    )


def test_explain_table_shows_live_badges_with_matching_prices(
    tmp_path, catalog_dir, capsys
):
    """Human table: HOT and ON TRACK rows show their own channel badges."""
    snapshot = _write_snapshot(
        tmp_path / "availability.json",
        codex=("ON TRACK", 80),
        anthropic=("HOT", 80),
    )
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 0

    lines = {
        line.split()[0]: line
        for line in captured.out.splitlines()
        if line and not line.startswith("-")
    }
    sol_line = lines[SOL_LOW_ROUTE]
    assert "ON TRACK" in sol_line
    fable_line = lines[FABLE_ROUTE]
    assert "HOT" in fable_line
    # Fable is excluded but still priced at its own channel's badge.
    assert "excluded" in fable_line
    assert "never_automatic" in fable_line


# ---------------------------------------------------------------------------
# --at date transition
# ---------------------------------------------------------------------------


def test_explain_at_date_transition(tmp_path, catalog_dir, capsys):
    """Before the committed terms date nothing is eligible; after, routes are.

    The pre-first-entry run also pins the fail-closed selected-terms view
    (Medium finding): ``terms_at`` raises, the JSON ``terms`` key is null,
    and the text line reads ``selected terms: unavailable at ...`` — never
    a crash or an invented terms entry.
    """
    snapshot = _write_snapshot(tmp_path / "availability.json")

    code, before = _explain_json_run(capsys, catalog_dir, snapshot, at="2026-09-08")
    assert code == 0
    assert before["at"] == "2026-09-08"
    assert all(route["eligible"] is False for route in before["routes"])
    assert all(
        any(r.startswith("terms unavailable at 2026-09-08") for r in route["reasons"])
        for route in before["routes"]
    )
    # Fail-closed terms view: null JSON terms, route fields still preserved.
    assert before["terms"] is None
    for route in before["routes"]:
        assert set(route) == ROUTE_JSON_KEYS

    code, after = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0
    glm = _by_route(after, GLM_OPENROUTER_ROUTE)
    assert glm["eligible"] is True
    assert glm["reasons"] == []


def test_explain_text_terms_unavailable_before_first_entry(
    tmp_path, catalog_dir, capsys
):
    """Text output at the pre-first-entry date shows the unavailable line."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-08",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 0

    lines = captured.out.splitlines()
    assert "selected terms: unavailable at 2026-09-08" in lines
    assert "selected terms at 2026-09-08" not in lines
    # No per-channel terms rows are rendered when the view fails closed.
    assert not any(line.startswith("  ") and "effective_from" in line for line in lines)


def test_explain_default_at_is_today(tmp_path, catalog_dir, capsys):
    """Without --at the report is dated today."""
    from datetime import date

    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot, at=None)
    assert code == 0
    assert payload["at"] == date.today().isoformat()


# ---------------------------------------------------------------------------
# Invalid inputs: clear nonzero exit, no traceback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role, class_string",
    [
        # Not five segments.
        ("impl", "impl/deterministic/none/s"),
        # Empty segment (empty tag set must be the literal 'none').
        ("impl", "impl/deterministic//s/python"),
        # Role segment does not equal --role.
        ("plan", "impl/deterministic/none/s/python"),
        # Role outside the committed value set.
        ("lead", "lead/deterministic/none/s/python"),
        # oracle_type outside the committed value set.
        ("impl", "impl/oracle/none/s/python"),
        # size_band outside the committed value set.
        ("impl", "impl/deterministic/none/xl/python"),
        # language outside the committed value set.
        ("impl", "impl/deterministic/none/s/rust"),
        # domain tag outside the committed value set.
        ("impl", "impl/deterministic/quantum/s/python"),
        # Non-canonical tag order (must be ascending by codepoint).
        ("impl", "impl/judge/security+persistence/m/python"),
    ],
)
def test_explain_invalid_class_exits_nonzero_without_traceback(
    tmp_path, catalog_dir, capsys, role, class_string
):
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        role,
        "--class",
        class_string,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code != 0
    assert captured.err.startswith("catalog explain:")
    assert captured.out == ""


def test_explain_invalid_at_date_exits_nonzero(tmp_path, catalog_dir, capsys):
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "not-a-date",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 3
    assert "--at" in captured.err
    assert captured.out == ""


def test_explain_invalid_catalog_exits_nonzero(tmp_path, catalog_dir, capsys):
    (catalog_dir / "channels.yaml").unlink()
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 3
    assert "catalog invalid" in captured.err
    assert "channels" in captured.err
    assert captured.out == ""


def test_explain_missing_availability_file_exits_nonzero(tmp_path, catalog_dir, capsys):
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(tmp_path / "nope.json"),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 3
    assert "availability snapshot unusable" in captured.err
    assert captured.out == ""


def test_explain_malformed_availability_file_exits_nonzero(
    tmp_path, catalog_dir, capsys
):
    snapshot = tmp_path / "availability.json"
    snapshot.write_text("{not json", encoding="utf-8")
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 3
    assert "availability snapshot unusable" in captured.err
    assert captured.out == ""


# ---------------------------------------------------------------------------
# Defaults: repo config/staffing catalog dir and load_availability behavior
# ---------------------------------------------------------------------------


def test_explain_defaults_to_repo_catalog_and_load_availability(capsys):
    """No --catalog-dir and no --availability-file: committed defaults apply."""
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--json",
    )
    assert code == 0
    payload = json.loads(captured.out)
    assert len(payload["routes"]) == len(
        load_staffing_catalog(REPO_CONFIG_DIR).routes.routes
    )
    # Default availability resolves through load_availability; whatever it
    # reports, every route still gets a row with the committed field set.
    for route in payload["routes"]:
        assert set(route) == ROUTE_JSON_KEYS


def test_explain_catalog_subcommand_required(capsys):
    from lee_llm_router.doctor import main

    with pytest.raises(SystemExit) as exc_info:
        main(["catalog"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 3
    assert "catalog: subcommand required" in captured.err


# ---------------------------------------------------------------------------
# P0-5d: selected-terms projection in text and JSON output
# ---------------------------------------------------------------------------


def test_explain_text_terms_before_retier_date(tmp_path, catalog_dir, capsys):
    """Text output before the re-tier shows Anthropic/Gemini at 100 (2026-09-09)."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 0

    lines = captured.out.splitlines()
    assert "selected terms at 2026-09-15" in lines
    assert "  anthropic-sub: effective_from 2026-09-09, fee_usd_month 100" in lines
    assert "  gemini-sub: effective_from 2026-09-09, fee_usd_month 100" in lines


def test_explain_text_terms_after_retier_date(tmp_path, catalog_dir, capsys):
    """Text output at the re-tier date shows both channels dropped to 20."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-10-01",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 0

    lines = captured.out.splitlines()
    assert "selected terms at 2026-10-01" in lines
    assert "  anthropic-sub: effective_from 2026-09-30, fee_usd_month 20" in lines
    assert "  gemini-sub: effective_from 2026-09-30, fee_usd_month 20" in lines


def test_explain_json_terms_deterministic_numerics_and_routes_fields(
    tmp_path, catalog_dir, capsys
):
    """JSON ``terms`` is deterministic, numeric post-re-tier, routes intact."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, after = _explain_json_run(capsys, catalog_dir, snapshot, at="2026-10-01")
    assert code == 0

    terms = after["terms"]
    assert isinstance(terms, dict)
    for channel in ("anthropic-sub", "gemini-sub"):
        entry = terms[channel]
        assert entry["effective_from"] == "2026-09-30"
        assert isinstance(entry["fee_usd_month"], (int, float))
        assert entry["fee_usd_month"] == 20
        assert set(entry) == {"effective_from", "fee_usd_month", "kind"}

    # Deterministic: same inputs produce byte-identical selected terms.
    code, again = _explain_json_run(capsys, catalog_dir, snapshot, at="2026-10-01")
    assert code == 0
    assert again["terms"] == terms

    # Existing routes fields are preserved alongside the new terms object.
    assert after["role"] == "impl"
    assert after["class_key"] == IMPL_CLASS
    assert after["at"] == "2026-10-01"
    for route in after["routes"]:
        assert set(route) == ROUTE_JSON_KEYS


def test_explain_json_terms_preserve_unknown_literal(tmp_path, catalog_dir, capsys):
    """The committed 'unknown' fee literal passes through without coercion."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0

    terms = payload["terms"]
    assert terms["opencode-go"]["fee_usd_month"] == "unknown"
    assert terms["local"]["fee_usd_month"] == "unknown"
    assert isinstance(terms["opencode-go"]["effective_from"], str)
    # No choice/probability/ladder keys leak into the terms view.
    for entry in terms.values():
        assert set(entry) == {"effective_from", "fee_usd_month", "kind"}


# ---------------------------------------------------------------------------
# P1-1: effective tier (term-kind label) in the JSON terms view
# ---------------------------------------------------------------------------


def test_explain_json_tier_label_reproduces_both_gate_dates(
    tmp_path, catalog_dir, capsys
):
    """Gate item 1: Anthropic and Gemini differ between the two dates.

    At ``--at 2026-09-15`` both subscription channels carry the 2026-09-09
    $100/mo terms; at ``--at 2026-10-01`` both carry the 2026-09-30
    $20/mo re-tier — selected by the committed ``terms_at`` lookup, never
    recomputed here, and carrying the ``subscription`` tier label at both
    dates. Eligibility, ordering, and reasons are untouched.
    """
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, before = _explain_json_run(capsys, catalog_dir, snapshot, at="2026-09-15")
    assert code == 0
    code, after = _explain_json_run(capsys, catalog_dir, snapshot, at="2026-10-01")
    assert code == 0

    for channel in ("anthropic-sub", "gemini-sub"):
        pre = before["terms"][channel]
        post = after["terms"][channel]
        assert pre == {
            "effective_from": "2026-09-09",
            "fee_usd_month": 100,
            "kind": "subscription",
        }
        assert post == {
            "effective_from": "2026-09-30",
            "fee_usd_month": 20,
            "kind": "subscription",
        }
        # The dated terms genuinely differ between the two gate dates.
        assert pre != post


def test_explain_json_tier_label_present_for_every_channel(
    tmp_path, catalog_dir, capsys
):
    """All seven committed channels carry the exact selected tier label."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot, at="2026-09-15")
    assert code == 0

    terms = payload["terms"]
    assert set(terms) == {
        "openai-sub",
        "anthropic-sub",
        "gemini-sub",
        "opencode-go",
        "openrouter",
        "opencode-zen",
        "local",
    }
    expected_kind = {
        "openai-sub": "subscription",
        "anthropic-sub": "subscription",
        "gemini-sub": "subscription",
        "opencode-go": "subscription",
        "openrouter": "metered",
        "opencode-zen": "metered",
        "local": "local",
    }
    for channel, tier in expected_kind.items():
        entry = terms[channel]
        assert entry["kind"] == tier
        assert set(entry) == {"effective_from", "fee_usd_month", "kind"}
    # Truthful unknowns: the unknown fee literal survives alongside the label.
    assert terms["opencode-go"]["fee_usd_month"] == "unknown"
    assert terms["local"]["fee_usd_month"] == "unknown"


def test_explain_text_output_unchanged_by_tier_label(tmp_path, catalog_dir, capsys):
    """Text output compatibility: the tier label is JSON-only disclosure."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 0

    lines = captured.out.splitlines()
    assert "selected terms at 2026-09-15" in lines
    assert "  anthropic-sub: effective_from 2026-09-09, fee_usd_month 100" in lines
    assert "  gemini-sub: effective_from 2026-09-09, fee_usd_month 100" in lines
    # No kind/tier text leaked into the per-channel lines or elsewhere.
    assert not any("kind" in line or "tier" in line.lower() for line in lines)


# ---------------------------------------------------------------------------
# Chief round 15 (D86/D87): floors recorded, not enforced — disclosure only
# ---------------------------------------------------------------------------


def _strip_role_floors(catalog_dir: Path) -> Path:
    """Rewrite the scratch catalog's policy.yaml with ``role_floors: []``.

    The committed policy records Chief round 15 floors; the schema requires
    the ``role_floors`` key but allows an empty array, so blanking it yields
    a valid catalog that differs from the committed one only in that data.
    Operates on the scratch copy in ``tmp_path``, never the repo config.
    """
    policy_path = catalog_dir / "policy.yaml"
    lines = policy_path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith("role_floors:"))
    end = next(
        i
        for i in range(start + 1, len(lines))
        if lines[i].strip() and not lines[i].startswith((" ", "#"))
    )
    lines[start:end] = ["role_floors: []\n"]
    policy_path.write_text("".join(lines), encoding="utf-8")
    return catalog_dir


def test_explain_text_discloses_floors_exactly_once(tmp_path, catalog_dir, capsys):
    """Text output carries the exact disclosure line exactly once."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 0
    assert captured.out.splitlines().count("floors recorded, not enforced") == 1


def test_explain_json_discloses_floors_as_additive_field_once(
    tmp_path, catalog_dir, capsys
):
    """JSON adds exactly one top-level ``floors_disclosure`` field; rows intact."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, payload = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0

    # Exactly the prior top-level fields plus the two additive disclosures.
    assert set(payload) == {
        "role",
        "class_key",
        "at",
        "terms",
        "floors_disclosure",
        "independence",
        "routes",
    }
    assert payload["floors_disclosure"] == "floors recorded, not enforced"

    # The key occurs exactly once in the serialized JSON (one top-level field).
    raw = json.dumps(payload, indent=2)
    assert raw.count('"floors_disclosure"') == 1
    assert raw.count('"independence"') == 1

    # Route row keys remain unchanged (no per-row floor field added).
    for route in payload["routes"]:
        assert set(route) == ROUTE_JSON_KEYS


def test_explain_recorded_floors_change_no_eligibility(tmp_path, catalog_dir, capsys):
    """Routes are identical with and without the committed ``role_floors`` data.

    The recorded floors add no floor exclusion reason and change no route's
    ``eligible``/``reasons`` — disclosure only, no enforcement.
    """
    snapshot = _write_snapshot(tmp_path / "availability.json")

    code, with_floors = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0

    floors_dir = _strip_role_floors(catalog_dir)
    assert floors_dir != REPO_CONFIG_DIR  # repo config untouched
    code, without_floors = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0

    def floor_view(payload: dict) -> list[tuple]:
        return [
            (r["route_id"], r["eligible"], tuple(r["reasons"]))
            for r in payload["routes"]
        ]

    assert floor_view(with_floors) == floor_view(without_floors)

    # No reason string anywhere mentions a floor.
    for payload in (with_floors, without_floors):
        for route in payload["routes"]:
            assert not any("floor" in reason.lower() for reason in route["reasons"])

    # A route eligible under the committed floors stays eligible, empty reasons.
    glm = _by_route(with_floors, GLM_OPENROUTER_ROUTE)
    assert glm["eligible"] is True
    assert glm["reasons"] == []


# ---------------------------------------------------------------------------
# Chief round 15 packet D: --author-route independence disclosure
# ---------------------------------------------------------------------------

REVIEW_CLASS = "review/deterministic/none/s/python"
SONNET_HIGH_ROUTE = "claude-claude-sonnet-5-high-anthropic-sub"
DEEPSEEK_FLASH_ROUTE = "pi-deepseek-deepseek-v4-flash-openrouter"


def test_explain_absent_author_route_discloses_exactly_once(
    tmp_path, catalog_dir, capsys
):
    """No --author-route: the exact disclosure line appears exactly once in
    text, and JSON records evaluated=false (review/judge still applicable)."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "review",
        "--class",
        REVIEW_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
    )
    assert code == 0
    assert (
        captured.out.splitlines().count(
            "independence not evaluated (no --author-route)"
        )
        == 1
    )

    code, captured = _run_explain(
        capsys,
        "--role",
        "review",
        "--class",
        REVIEW_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--json",
    )
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["independence"] == {
        "evaluated": False,
        "applicable": True,
        "disclosure": "independence not evaluated (no --author-route)",
    }
    # No route is excluded by independence without the input.
    for route in payload["routes"]:
        assert "independence" not in route["reasons"]


def test_explain_author_route_review_excludes_same_route_and_family(
    tmp_path, catalog_dir, capsys
):
    """--author-route FABLE for review: the author route and every same-family
    (claude) candidate carry exactly the 'independence' reason; different-family
    routes are untouched. The author route, derived family, and family source
    are recorded once in text and JSON."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "review",
        "--class",
        REVIEW_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--author-route",
        FABLE_ROUTE,
        "--json",
    )
    assert code == 0
    payload = json.loads(captured.out)

    assert payload["independence"] == {
        "evaluated": True,
        "applicable": True,
        "author_route": FABLE_ROUTE,
        "author_family": "claude",
        "family_source": "model_vendor_prefix",
    }
    raw = json.dumps(payload, indent=2)
    assert raw.count('"author_route"') == 1
    assert raw.count('"author_family"') == 1
    assert raw.count('"family_source"') == 1

    fable = _by_route(payload, FABLE_ROUTE)
    assert fable["eligible"] is False
    assert "independence" in fable["reasons"]
    assert fable["reasons"] == ["never_automatic", "independence"]

    # Eligible same-family candidate: excluded by independence alone.
    sonnet = _by_route(payload, SONNET_HIGH_ROUTE)
    assert sonnet["eligible"] is False
    assert sonnet["reasons"] == ["independence"]

    # Different family (z-ai namespace): untouched and eligible.
    glm = _by_route(payload, GLM_OPENROUTER_ROUTE)
    assert glm["eligible"] is True
    assert glm["reasons"] == []

    # Same-family deepseek-v4-pro (leading-token deepseek) is a different
    # family from z-ai; it must be untouched by a z-ai author route.
    deepseek = _by_route(payload, DEEPSEEK_FLASH_ROUTE)
    assert "independence" not in deepseek["reasons"]

    # Existing route row fields are preserved.
    for route in payload["routes"]:
        assert set(route) == ROUTE_JSON_KEYS


def test_explain_author_route_text_records_author_family_source_once(
    tmp_path, catalog_dir, capsys
):
    """Text output records the author route, derived family, and source once."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "review",
        "--class",
        REVIEW_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--author-route",
        FABLE_ROUTE,
    )
    assert code == 0
    line = (
        f"independence: author route {FABLE_ROUTE}, family claude "
        "(from model_vendor_prefix)"
    )
    assert captured.out.splitlines().count(line) == 1
    assert "independence not evaluated (no --author-route)" not in captured.out


def test_explain_author_route_judge_same_route(tmp_path, catalog_dir, capsys):
    """--author-route SOL for judge: the author route itself is excluded with
    the 'independence' reason alongside its existing reasons."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "judge",
        "--class",
        "judge/deterministic/none/s/python",
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--author-route",
        SOL_LOW_ROUTE,
        "--json",
    )
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["independence"]["evaluated"] is True
    assert payload["independence"]["author_family"] == "gpt"
    sol = _by_route(payload, SOL_LOW_ROUTE)
    assert sol["eligible"] is False
    assert "independence" in sol["reasons"]


def test_explain_author_route_invalid_exits_3(tmp_path, catalog_dir, capsys):
    """An unknown --author-route fails closed with a named error and exit 3."""
    snapshot = _write_snapshot(tmp_path / "availability.json")
    code, captured = _run_explain(
        capsys,
        "--role",
        "review",
        "--class",
        REVIEW_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--author-route",
        "no-such-route",
    )
    assert code == 3
    assert captured.err.startswith("catalog explain:")
    assert "no-such-route" in captured.err
    assert captured.out == ""


def test_explain_author_route_impl_not_applicable(tmp_path, catalog_dir, capsys):
    """For impl the check is not applicable: no exclusion, evaluated false,
    and the record says so rather than pretending it ran."""
    snapshot = _write_snapshot(tmp_path / "availability.json")

    # Baseline without --author-route for comparison.
    code, baseline = _explain_json_run(capsys, catalog_dir, snapshot)
    assert code == 0

    code, payload = _explain_json_run(
        capsys,
        catalog_dir,
        snapshot,
        "2026-09-15",
        "--author-route",
        SOL_LOW_ROUTE,
    )
    assert code == 0
    assert payload["independence"] == {
        "evaluated": False,
        "applicable": False,
        "author_route": SOL_LOW_ROUTE,
        "author_family": "gpt",
        "family_source": "model_vendor_prefix",
        "disclosure": "independence not applicable for role 'impl'",
    }
    # Eligibility is unchanged: no route gains the independence reason.
    for baseline_route, route in zip(baseline["routes"], payload["routes"]):
        assert route["reasons"] == baseline_route["reasons"]
        assert route["eligible"] == baseline_route["eligible"]
        assert "independence" not in route["reasons"]

    code, captured = _run_explain(
        capsys,
        "--role",
        "impl",
        "--class",
        IMPL_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--author-route",
        SOL_LOW_ROUTE,
    )
    assert code == 0
    assert (
        "independence not applicable for role 'impl' (author route "
        f"{SOL_LOW_ROUTE}, family gpt (from model_vendor_prefix))"
    ) in captured.out


# ---------------------------------------------------------------------------
# Chief round 15 route.family override: the explicit family reaches explain
# (Astra Medium) — schema + typed Route now carry optional ``family``; these
# tests exercise the precedence through the scratch catalog and the CLI.
# ---------------------------------------------------------------------------


def _set_route_family(catalog_dir: Path, route_id: str, family: str) -> Path:
    """Rewrite the scratch catalog's routes.yaml, giving one route a family.

    Operates only on the scratch copy in ``tmp_path``; the committed
    routes.yaml is never modified (schema + loader now accept the field).
    """
    routes_path = catalog_dir / "routes.yaml"
    doc = yaml.safe_load(routes_path.read_text(encoding="utf-8"))
    route = next(r for r in doc["routes"] if r["route_id"] == route_id)
    route["family"] = family
    routes_path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return catalog_dir


def _review_author_json(
    capsys: pytest.CaptureFixture[str],
    catalog_dir: Path,
    snapshot: Path,
    author_route: str,
):
    """Run review-class explain with an author route and return the JSON."""
    code, captured = _run_explain(
        capsys,
        "--role",
        "review",
        "--class",
        REVIEW_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--author-route",
        author_route,
        "--json",
    )
    assert code == 0
    return json.loads(captured.out)


def test_explain_author_route_family_override_reaches_explain(
    tmp_path, catalog_dir, capsys
):
    """A schema-valid route.family on the author route overrides the prefix.

    The override replaces the model-vendor-prefix fallback in both the
    recorded family/source and the exclusion: same-prefix routes without
    the override escape the independence exclusion, and only the route
    carrying the explicit family is excluded by it.
    """
    snapshot = _write_snapshot(tmp_path / "availability.json")

    # Baseline (no override): prefix fallback excludes every claude-* model.
    baseline = _review_author_json(capsys, catalog_dir, snapshot, SONNET_HIGH_ROUTE)
    assert baseline["independence"]["family_source"] == "model_vendor_prefix"
    assert baseline["independence"]["author_family"] == "claude"
    assert "independence" in _by_route(baseline, FABLE_ROUTE)["reasons"]

    # Override: the explicit family reaches the CLI output and the exclusion.
    _set_route_family(catalog_dir, SONNET_HIGH_ROUTE, "scribble")
    payload = _review_author_json(capsys, catalog_dir, snapshot, SONNET_HIGH_ROUTE)
    assert payload["independence"]["author_route"] == SONNET_HIGH_ROUTE
    assert payload["independence"]["author_family"] == "scribble"
    assert payload["independence"]["family_source"] == "route.family"
    raw = json.dumps(payload, indent=2)
    assert raw.count('"family_source"') == 1
    assert '"route.family"' in raw

    # The author route itself is excluded by independence alone.
    sonnet = _by_route(payload, SONNET_HIGH_ROUTE)
    assert sonnet["eligible"] is False
    assert sonnet["reasons"] == ["independence"]

    # Exclusion precedence: same-prefix routes WITHOUT the override are no
    # longer excluded by independence (their prefix family no longer
    # matches the override family); their reasons are unchanged otherwise.
    fable = _by_route(payload, FABLE_ROUTE)
    assert "independence" not in fable["reasons"]
    sonnet_medium = _by_route(payload, "claude-claude-sonnet-5-medium-anthropic-sub")
    assert "independence" not in sonnet_medium["reasons"]

    # Text output records the override family and its source exactly once.
    code, captured = _run_explain(
        capsys,
        "--role",
        "review",
        "--class",
        REVIEW_CLASS,
        "--at",
        "2026-09-15",
        "--availability-file",
        str(snapshot),
        "--catalog-dir",
        str(catalog_dir),
        "--author-route",
        SONNET_HIGH_ROUTE,
    )
    assert code == 0
    line = (
        f"independence: author route {SONNET_HIGH_ROUTE}, family scribble "
        "(from route.family)"
    )
    assert captured.out.splitlines().count(line) == 1


def test_explain_candidate_family_override_changes_exclusion(
    tmp_path, catalog_dir, capsys
):
    """A candidate's explicit family takes precedence over its model prefix.

    Giving the z-ai-namespaced GLM route family 'claude' pulls it into the
    claude author's exclusion set; routes without the override keep the
    model-vendor-prefix fallback. Comparison keys only (D206) — no route
    choice, ranking, or probability changes.
    """
    snapshot = _write_snapshot(tmp_path / "availability.json")

    # Baseline: GLM is eligible for review with empty reasons.
    baseline = _review_author_json(capsys, catalog_dir, snapshot, FABLE_ROUTE)
    assert baseline["independence"]["family_source"] == "model_vendor_prefix"
    glm_baseline = _by_route(baseline, GLM_OPENROUTER_ROUTE)
    assert glm_baseline["eligible"] is True
    assert glm_baseline["reasons"] == []

    # Override the candidate family; exclusion follows the explicit value.
    _set_route_family(catalog_dir, GLM_OPENROUTER_ROUTE, "claude")
    payload = _review_author_json(capsys, catalog_dir, snapshot, FABLE_ROUTE)
    assert payload["independence"]["author_family"] == "claude"
    assert payload["independence"]["family_source"] == "model_vendor_prefix"

    # Candidate-side precedence: GLM is now excluded by independence alone
    # despite its z-ai model namespace.
    glm = _by_route(payload, GLM_OPENROUTER_ROUTE)
    assert glm["eligible"] is False
    assert glm["reasons"] == ["independence"]

    # Routes without the override keep the prefix fallback: sonnet is
    # excluded as same-prefix, deepseek (different prefix) is untouched.
    sonnet = _by_route(payload, SONNET_HIGH_ROUTE)
    assert sonnet["reasons"] == ["independence"]
    deepseek = _by_route(payload, DEEPSEEK_FLASH_ROUTE)
    assert "independence" not in deepseek["reasons"]
