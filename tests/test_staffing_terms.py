"""Tests for the P0-4b dated-terms and marginal-price API (staffing.terms).

Reads the committed catalog (config/staffing) and the pinned pricing
sources; tamper/missing tests operate on scratch copies under tmp_path
only — no committed file is ever modified and no provider call is made.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from lee_llm_router.providers.base import FailureType
from lee_llm_router.staffing import (
    ReplacementPrice,
    StaffingTermsError,
    badge_multiplier,
    load_openrouter_snapshot,
    load_rate_table,
    replacement_token_prices,
    route_price,
    terms_at,
)
from lee_llm_router.staffing.catalog import load_staffing_catalog

REPO_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "staffing"
SNAPSHOT_NAME = "openrouter-20260911.json"


@pytest.fixture(scope="module")
def catalog():
    return load_staffing_catalog(REPO_CONFIG_DIR)


@pytest.fixture
def scratch_pricing(tmp_path: Path) -> Path:
    """Scratch copy of the pinned pricing directory (never the original)."""
    dest = tmp_path / "pricing"
    dest.mkdir()
    for item in (REPO_CONFIG_DIR / "pricing").iterdir():
        shutil.copy2(item, dest / item.name)
    return dest


# ---------------------------------------------------------------------------
# terms_at — dated lookup
# ---------------------------------------------------------------------------


def test_terms_at_anthropic_100_on_2026_09_15_and_20_on_2026_10_01(catalog) -> None:
    at_sept = terms_at("2026-09-15", catalog)
    assert at_sept["anthropic-sub"].fee_usd_month == 100
    at_oct = terms_at("2026-10-01", catalog)
    assert at_oct["anthropic-sub"].fee_usd_month == 20


def test_terms_at_openai_200_then_unchanged(catalog) -> None:
    at_sept = terms_at("2026-09-15", catalog)
    assert at_sept["openai-sub"].fee_usd_month == 200
    at_oct = terms_at("2026-10-01", catalog)
    assert at_oct["openai-sub"].fee_usd_month == 200


def test_terms_at_every_channel_resolved_deterministically(catalog) -> None:
    selected = terms_at("2026-09-15", catalog)
    channel_order = [c.channel_id for c in catalog.channels.channels]
    assert list(selected.keys()) == channel_order


def test_terms_at_before_any_entry_errors_clearly(catalog) -> None:
    with pytest.raises(StaffingTermsError) as excinfo:
        terms_at("2026-08-31", catalog)
    assert "no TermsEntry for channel" in str(excinfo.value)


def test_terms_at_rejects_non_iso_date(catalog) -> None:
    with pytest.raises(StaffingTermsError):
        terms_at("not-a-date", catalog)


# ---------------------------------------------------------------------------
# badge multipliers
# ---------------------------------------------------------------------------


def test_badge_multiplier_configured_values(catalog) -> None:
    terms = catalog.terms
    assert badge_multiplier("COLD", terms) == 0.0
    assert badge_multiplier("USE IT", terms) == 0.0
    assert badge_multiplier("ON TRACK", terms) == 0.25
    assert badge_multiplier("HOT", terms) == 0.75
    assert badge_multiplier("TOO FAST", terms) == 1.0
    assert badge_multiplier("NO DATA", terms) == 1.0


def test_unknown_badge_multiplier_is_one(catalog) -> None:
    assert badge_multiplier("WHENEVER", catalog.terms) == 1.0
    assert badge_multiplier("cold", catalog.terms) == 1.0  # casing is exact-match


# ---------------------------------------------------------------------------
# marginal price for the acceptance route gpt-5.6-sol|codex|low|openai-sub
# ---------------------------------------------------------------------------


def test_sol_low_replacement_comes_from_rate_table(catalog) -> None:
    price = route_price("codex-gpt-5-6-sol-low-openai-sub", "COLD", catalog)
    # gpt-5.6-sol is not an OpenRouter-listed exact id (snapshot key is
    # openai/gpt-5.6-sol), so the agent-orch rate-table row applies:
    # $4.00/$20.00 per 1M tokens verbatim -> per token.
    assert price.replacement.source == "rate-table:gpt-5.6-sol"
    assert price.replacement.input_usd_per_token == pytest.approx(4.00 / 1e6)
    assert price.replacement.output_usd_per_token == pytest.approx(20.00 / 1e6)


def test_sol_low_cold_marginal_is_zero(catalog) -> None:
    price = route_price("codex-gpt-5-6-sol-low-openai-sub", "COLD", catalog)
    assert price.multiplier == 0.0
    assert price.marginal_input_usd_per_token == 0.0
    assert price.marginal_output_usd_per_token == 0.0
    # Reporting/list price remains the replacement price, not the marginal.
    assert price.replacement.input_usd_per_token == pytest.approx(4.00 / 1e6)


def test_sol_low_too_fast_marginal_equals_replacement(catalog) -> None:
    price = route_price("codex-gpt-5-6-sol-low-openai-sub", "TOO FAST", catalog)
    assert price.multiplier == 1.0
    assert price.marginal_input_usd_per_token == pytest.approx(
        price.replacement.input_usd_per_token
    )
    assert price.marginal_output_usd_per_token == pytest.approx(
        price.replacement.output_usd_per_token
    )


def test_unknown_badge_marginal_equals_replacement(catalog) -> None:
    price = route_price("codex-gpt-5-6-sol-low-openai-sub", "WHENEVER", catalog)
    assert price.multiplier == 1.0
    assert price.marginal_input_usd_per_token == pytest.approx(
        price.replacement.input_usd_per_token
    )
    assert price.marginal_output_usd_per_token == pytest.approx(
        price.replacement.output_usd_per_token
    )


def test_route_price_unknown_route_errors(catalog) -> None:
    with pytest.raises(StaffingTermsError) as excinfo:
        route_price("no-such-route", "COLD", catalog)
    assert "not found" in str(excinfo.value)


# ---------------------------------------------------------------------------
# pinned snapshot + sha256 verification
# ---------------------------------------------------------------------------


def test_pinned_snapshot_sha256_matches_and_prices_resolve() -> None:
    priced, listed = load_openrouter_snapshot()  # committed file + sidecar
    assert "z-ai/glm-5.3-flash" in listed
    # Verbatim from the pinned 2026-09-11 snapshot, per token: prompt
    # 0.00000015, completion 0.0000005 (D218: doubled since 2026-09-09).
    assert priced["z-ai/glm-5.3-flash"] == pytest.approx((1.5e-07, 5.0e-07))


def test_openrouter_exact_id_resolves_from_snapshot() -> None:
    price = replacement_token_prices("z-ai/glm-5.3-flash", "openrouter")
    assert isinstance(price, ReplacementPrice)
    assert price.source == "openrouter-snapshot:z-ai/glm-5.3-flash"
    assert price.input_usd_per_token == pytest.approx(1.5e-07)
    assert price.output_usd_per_token == pytest.approx(5.0e-07)


def test_d207_go_proxy_row_resolves_from_rate_table() -> None:
    price = replacement_token_prices("opencode-go/qwen3.7-plus", "opencode-go")
    assert price.source == "rate-table:opencode-go/qwen3.7-plus"
    # Zen proxy list price verbatim: $0.40/$1.60 per 1M tokens.
    assert price.input_usd_per_token == pytest.approx(0.40 / 1e6)
    assert price.output_usd_per_token == pytest.approx(1.60 / 1e6)


def test_rate_table_loads_without_verification_marker() -> None:
    rates = load_rate_table()
    assert "gpt-5.6-sol" in rates
    assert rates["gpt-5.6-sol"] == pytest.approx((4.00 / 1e6, 20.00 / 1e6))


def test_tampered_snapshot_fails_closed(scratch_pricing: Path) -> None:
    snapshot = scratch_pricing / SNAPSHOT_NAME
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    data["data"][0]["pricing"]["prompt"] = "0.00000099"
    snapshot.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(StaffingTermsError) as excinfo:
        replacement_token_prices(
            "z-ai/glm-5.3-flash", "openrouter", openrouter_snapshot_path=snapshot
        )
    assert "sha256" in str(excinfo.value)


def test_missing_sha_sidecar_fails_closed(tmp_path: Path) -> None:
    scratch = tmp_path / "pricing"
    scratch.mkdir()
    shutil.copy2(REPO_CONFIG_DIR / "pricing" / SNAPSHOT_NAME, scratch / SNAPSHOT_NAME)
    with pytest.raises(StaffingTermsError) as excinfo:
        replacement_token_prices(
            "z-ai/glm-5.3-flash",
            "openrouter",
            openrouter_snapshot_path=scratch / SNAPSHOT_NAME,
        )
    assert "sidecar not found" in str(excinfo.value)


def test_missing_price_fails_closed(catalog) -> None:
    # The committed unpriced id: opencode-go/mimo-v2.5 has no OpenRouter row
    # and no rate-table row (D207 forbids equating it with mimo-v2.5-free).
    with pytest.raises(StaffingTermsError) as excinfo:
        replacement_token_prices("opencode-go/mimo-v2.5", "opencode-go")
    assert "no replacement price" in str(excinfo.value)
    with pytest.raises(StaffingTermsError):
        route_price("opencode-opencode-go-mimo-v2-5-opencode-go", "HOT", catalog)


def test_listed_but_unpriced_snapshot_row_fails_closed(tmp_path: Path) -> None:
    scratch = tmp_path / SNAPSHOT_NAME
    scratch.write_text(
        json.dumps({"data": [{"id": "openai/gpt-5.6-sol", "pricing": None}]}),
        encoding="utf-8",
    )
    (tmp_path / (SNAPSHOT_NAME + ".sha256")).write_text(
        hashlib.sha256(scratch.read_bytes()).hexdigest() + "  " + SNAPSHOT_NAME,
        encoding="utf-8",
    )
    with pytest.raises(StaffingTermsError) as excinfo:
        replacement_token_prices(
            "openai/gpt-5.6-sol", "openai-sub", openrouter_snapshot_path=scratch
        )
    assert "unpriced" in str(excinfo.value)


def test_errors_chain_into_llm_router_contract_violation(catalog) -> None:
    with pytest.raises(StaffingTermsError) as excinfo:
        terms_at("2026-08-31", catalog)
    assert excinfo.value.failure_type is FailureType.CONTRACT_VIOLATION
