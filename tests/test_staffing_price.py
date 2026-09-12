"""Unit tests for ``compute_price`` in ``src/lee_llm_router/staffing/price.py``.

Tests cover:
- Known active route produces a correct PriceResult with list and marginal prices.
- Unknown route id raises PriceError.
- Negative token counts raise PriceError.
- Non-integer token counts raise PriceError.
- Invalid --at date raises PriceError.
- Cached tokens when model has a cache-read rate (openrouter-snapshot source).
- Cached tokens when model has no cache-read rate -> fail closed.
"""

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from lee_llm_router.availability import (
    AvailabilitySnapshot,
    Bucket,
    ChannelHeadroom,
    Health,
)
from lee_llm_router.providers.base import FailureType
from lee_llm_router.staffing import load_staffing_catalog
from lee_llm_router.staffing.price import PriceError, PriceResult, compute_price

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG_DIR = REPO_ROOT / "config" / "staffing"
AT = date(2026, 10, 1)
ACTIVE_ROUTE = "codex-gpt-5-6-sol-low-openai-sub"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _loaded_catalog() -> Any:
    """Load the real committed staffing catalog (never modified)."""
    return load_staffing_catalog(REPO_CONFIG_DIR)


def _available_snapshot(
    channel: str = "openai-sub",
    raw_status: str = "ON TRACK",
    limiting_bucket: str = "Weekly limit",
    remaining_fraction: float = 0.8,
) -> AvailabilitySnapshot:
    """Build a minimal AvailabilitySnapshot with one channel and one bucket."""
    now = datetime.now(timezone.utc)
    bucket = Bucket(
        channel=channel,
        provider="OpenAI/Codex",
        name=limiting_bucket,
        health=Health.HEALTHY,
        remaining_fraction=remaining_fraction,
        resets_at=now,
        resets_in_hours=24.0,
        pace_ratio=1.0,
        raw_status=raw_status,
    )
    headroom = ChannelHeadroom(
        channel=channel,
        health=Health.HEALTHY,
        remaining_fraction=remaining_fraction,
        limiting_bucket=limiting_bucket,
        observed_at=now,
        stale=False,
        buckets=(bucket,),
    )
    return AvailabilitySnapshot(
        observed_at=now,
        host="test-host",
        path=None,
        stale=False,
        age_minutes=0.0,
        channels={channel: headroom},
        ignored=(),
        problem=None,
        written_at=now,
    )


def _write_openrouter_snapshot(tmp_path: Path, has_cache: bool) -> Path:
    """Write a minimal OpenRouter snapshot with gpt-5.6-sol and a sha256 sidecar.

    The model id is ``gpt-5.6-sol`` (bare, no ``openai/`` prefix) so that
    ``replacement_token_prices`` finds it as an exact match and never falls
    through to the real rate table.
    """
    pricing: dict[str, str] = {
        "prompt": "4.00",
        "completion": "20.00",
    }
    if has_cache:
        pricing["input_cache_read"] = "0.40"
    data = {
        "data": [
            {
                "id": "gpt-5.6-sol",
                "name": "GPT-5.6 Sol",
                "pricing": pricing,
            }
        ]
    }
    p = tmp_path / "openrouter_snapshot.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    # Write sha256 sidecar so _verify_sha256 passes
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    sidecar = p.with_name(p.name + ".sha256")
    sidecar.write_text(sha + "  " + p.name, encoding="utf-8")
    return p


def _openrouter_snapshot_with_cache(tmp_path: Path) -> Path:
    return _write_openrouter_snapshot(tmp_path, has_cache=True)


def _openrouter_snapshot_no_cache(tmp_path: Path) -> Path:
    return _write_openrouter_snapshot(tmp_path, has_cache=False)


# ---------------------------------------------------------------------------
# Active route -> correct list/marginal price
# ---------------------------------------------------------------------------


def test_compute_price_returns_price_result_for_active_route() -> None:
    """A known active route with sample token counts produces a PriceResult."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    result = compute_price(
        route_id=ACTIVE_ROUTE,
        input_tokens=100,
        output_tokens=50,
        cached_tokens=0,
        catalog=catalog,
        availability=availability,
        at_date=AT,
    )
    assert isinstance(result, PriceResult)
    assert result.route_id == ACTIVE_ROUTE
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cached_tokens == 0
    assert result.list_usd > 0.0
    assert result.marginal_usd > 0.0
    assert result.replacement_input_usd_per_token > 0.0
    assert result.replacement_output_usd_per_token > 0.0
    assert result.marginal_input_usd_per_token > 0.0
    assert result.marginal_output_usd_per_token > 0.0
    # With ON TRACK badge, marginal should be less than list (ON TRACK multiplier 0.25)
    assert result.marginal_usd < result.list_usd
    assert result.badge == "ON TRACK"
    assert result.multiplier == 0.25


def test_compute_price_as_dict_includes_all_fields() -> None:
    """as_dict() returns all expected fields (cache fields omitted when None)."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    result = compute_price(
        route_id=ACTIVE_ROUTE,
        input_tokens=100,
        output_tokens=50,
        catalog=catalog,
        availability=availability,
        at_date=AT,
    )
    d = result.as_dict()
    assert d["route_id"] == ACTIVE_ROUTE
    assert d["input_tokens"] == 100
    assert d["output_tokens"] == 50
    assert d["list_usd"] == result.list_usd
    assert d["marginal_usd"] == result.marginal_usd
    # Cache fields may or may not be present depending on whether the
    # default rate table resolves a cache rate for this model.


def test_compute_price_render_text_includes_key_fields() -> None:
    """render_text() output contains expected labels."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    result = compute_price(
        route_id=ACTIVE_ROUTE,
        input_tokens=100,
        output_tokens=50,
        catalog=catalog,
        availability=availability,
        at_date=AT,
    )
    text = result.render_text()
    assert ACTIVE_ROUTE in text
    assert "list_usd:" in text
    assert "marginal_usd:" in text
    assert "input_tokens:  100" in text
    assert "output_tokens: 50" in text
    assert "cached_tokens: 0" in text


# ---------------------------------------------------------------------------
# Unknown route id -> PriceError
# ---------------------------------------------------------------------------


def test_unknown_route_id_raises_price_error() -> None:
    """An unknown route id raises PriceError with the route id in the message."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    with pytest.raises(PriceError) as excinfo:
        compute_price(
            route_id="nonexistent-route-id",
            input_tokens=100,
            output_tokens=50,
            catalog=catalog,
            availability=availability,
            at_date=AT,
        )
    assert "nonexistent-route-id" in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


# ---------------------------------------------------------------------------
# Negative token counts -> PriceError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "cached_tokens"),
    [
        (-1, 50, 0),
        (100, -5, 0),
        (100, 50, -10),
    ],
)
def test_negative_tokens_raise_price_error(
    input_tokens: int, output_tokens: int, cached_tokens: int
) -> None:
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    with pytest.raises(PriceError) as excinfo:
        compute_price(
            route_id=ACTIVE_ROUTE,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            catalog=catalog,
            availability=availability,
            at_date=AT,
        )
    assert "must be a non-negative integer" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Non-integer token counts -> PriceError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "cached_tokens"),
    [
        (1.5, 50, 0),
        (100, "fifty", 0),
        (100, 50, None),
        (True, 50, 0),
    ],
)
def test_non_integer_tokens_raise_price_error(
    input_tokens: int, output_tokens: int, cached_tokens: int
) -> None:
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    with pytest.raises(PriceError) as excinfo:
        compute_price(
            route_id=ACTIVE_ROUTE,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            catalog=catalog,
            availability=availability,
            at_date=AT,
        )
    assert "must be a non-negative integer" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Invalid --at date -> PriceError
# ---------------------------------------------------------------------------


def test_invalid_at_date_string_raises_price_error() -> None:
    """A malformed ISO date string raises PriceError with the value in the message."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    with pytest.raises(PriceError) as excinfo:
        compute_price(
            route_id=ACTIVE_ROUTE,
            input_tokens=100,
            output_tokens=50,
            catalog=catalog,
            availability=availability,
            at_date="not-a-date",
        )
    assert "not-a-date" in str(excinfo.value)
    assert excinfo.value.failure_type == FailureType.CONTRACT_VIOLATION


# ---------------------------------------------------------------------------
# Cached tokens with cache-read rate (openrouter-snapshot source)
# ---------------------------------------------------------------------------


def test_cached_tokens_with_cache_rate_increases_list_and_marginal(
    tmp_path: Path,
) -> None:
    """When the resolved model has a cache-read rate, cached tokens are priced."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    or_snapshot = _openrouter_snapshot_with_cache(tmp_path)

    result_no_cache = compute_price(
        route_id=ACTIVE_ROUTE,
        input_tokens=100,
        output_tokens=50,
        cached_tokens=0,
        catalog=catalog,
        availability=availability,
        at_date=AT,
        openrouter_snapshot_path=or_snapshot,
    )
    result_with_cache = compute_price(
        route_id=ACTIVE_ROUTE,
        input_tokens=100,
        output_tokens=50,
        cached_tokens=10,
        catalog=catalog,
        availability=availability,
        at_date=AT,
        openrouter_snapshot_path=or_snapshot,
    )

    assert result_with_cache.list_usd > result_no_cache.list_usd
    assert result_with_cache.marginal_usd > result_no_cache.marginal_usd
    assert result_with_cache.cache_read_usd_per_token is not None
    assert result_with_cache.marginal_cache_read_usd_per_token is not None
    assert result_with_cache.cached_tokens == 10


def test_cached_tokens_cache_rate_stored_in_as_dict(tmp_path: Path) -> None:
    """as_dict() includes cache fields when cache_rate is resolved."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    or_snapshot = _openrouter_snapshot_with_cache(tmp_path)

    result = compute_price(
        route_id=ACTIVE_ROUTE,
        input_tokens=100,
        output_tokens=50,
        cached_tokens=10,
        catalog=catalog,
        availability=availability,
        at_date=AT,
        openrouter_snapshot_path=or_snapshot,
    )
    d = result.as_dict()
    assert d["cache_read_usd_per_token"] is not None
    assert d["marginal_cache_read_usd_per_token"] is not None


# ---------------------------------------------------------------------------
# Cached tokens without cache-read rate -> fail closed (PriceError)
# ---------------------------------------------------------------------------


def test_cached_tokens_without_cache_rate_fails_closed(tmp_path: Path) -> None:
    """When the model has no cache-read rate, cached_tokens > 0 raises PriceError."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    or_snapshot = _openrouter_snapshot_no_cache(tmp_path)

    with pytest.raises(PriceError) as excinfo:
        compute_price(
            route_id=ACTIVE_ROUTE,
            input_tokens=100,
            output_tokens=50,
            cached_tokens=5,
            catalog=catalog,
            availability=availability,
            at_date=AT,
            openrouter_snapshot_path=or_snapshot,
        )
    assert "no read-cache price" in str(excinfo.value)


def test_cached_zero_without_cache_rate_ok(tmp_path: Path) -> None:
    """cached_tokens=0 does not fail when the model lacks a cache-read rate."""
    catalog = _loaded_catalog()
    availability = _available_snapshot()
    or_snapshot = _openrouter_snapshot_no_cache(tmp_path)

    result = compute_price(
        route_id=ACTIVE_ROUTE,
        input_tokens=100,
        output_tokens=50,
        cached_tokens=0,
        catalog=catalog,
        availability=availability,
        at_date=AT,
        openrouter_snapshot_path=or_snapshot,
    )
    assert isinstance(result, PriceResult)
    assert result.cache_read_usd_per_token is None
