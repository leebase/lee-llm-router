"""Import historical benchmark evidence into the staffing attempt ledger.

The Phase-1 benchmark source is the v6 staffing-evidence sidecar.  Its
``source_csv`` names and hashes the per-run CSV, while each sidecar row adds a
validated task class and a lossless ``run_usage`` entry for every CSV run.
This module verifies that join before projecting a run into the closest valid
attempt-record v2 shape.

Benchmark CSV rows do not identify a channel-qualified staffing route, an
oracle command, a supervisor route, or a cost calculated from Phase-1 terms.
Those facts are therefore never inferred.  Imported records are deliberately
not ``verified_success`` records and their canonical cost is unavailable.

No provider or subprocess boundary exists here.  Appends go through
``staffing.ledger.append_attempt``, which validates and performs the existing
single-write ``O_APPEND`` operation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from lee_llm_router.providers.base import LLMRouterError
from lee_llm_router.staffing.catalog import StaffingCatalogError, validate_class_block
from lee_llm_router.staffing.ledger import (
    AttemptLedgerError,
    append_attempt,
    read_attempts,
    resolve_attempts_path,
    validate_attempt,
)

BENCHMARK_SCHEMA_VERSION = "benchmark.staffing-evidence/2"
BENCHMARK_USAGE_SOURCE = "benchmark v6 CSV usage_*_tokens"
TOKEN_COLUMNS = (
    "usage_input_tokens",
    "usage_output_tokens",
    "usage_cached_input_tokens",
    "usage_reasoning_tokens",
    "usage_total_tokens",
)
_ATTEMPT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_CLASS_FIELDS = {
    "class_key",
    "role",
    "oracle_type",
    "domain_tags",
    "size_band",
    "language",
}
_ROLE_STAGE = {
    "impl": "author",
    "plan": "ideate",
    "review": "score",
    "judge": "score",
    "prose": "author",
}


class EvidenceImportError(LLMRouterError):
    """Raised when benchmark import inputs or the destination are invalid."""


class _RowError(ValueError):
    """One malformed or unmappable CSV row, safe to skip explicitly."""


@dataclass(frozen=True)
class ImportIssue:
    """Reason one source CSV row was skipped.

    Attributes:
        row_number: One-based physical CSV line number.
        run_id: Source run id when it was readable.
        reason: Explicit malformed/unmappable or duplicate reason.
    """

    row_number: int
    run_id: str | None
    reason: str


@dataclass(frozen=True)
class ImportSummary:
    """Counts and per-row diagnostics from one benchmark import."""

    imported: int
    skipped: int
    issues: tuple[ImportIssue, ...]
    ledger_path: Path


@dataclass(frozen=True)
class _RunMetadata:
    """Sidecar facts joined to a single source CSV run."""

    task_key: str
    class_record: Mapping[str, Any]
    worker: Mapping[str, Any]
    usage: Mapping[str, Any]


def _read_json_object(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvidenceImportError(
            f"cannot read benchmark sidecar {path}: {exc}"
        ) from exc
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceImportError(
            f"benchmark sidecar {path} is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise EvidenceImportError(f"benchmark sidecar {path} is not a JSON object")
    return value, raw


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _RowError(f"{label} is missing or empty")
    return value.strip()


def _aware_timestamp(value: Any, label: str) -> str:
    text = _required_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _RowError(f"{label} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _RowError(f"{label} is not timezone-aware")
    return text


def _optional_counter(value: Any, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise _RowError(f"{label} is not a nonnegative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise _RowError(f"{label} is not a nonnegative integer") from exc
    if str(parsed) != str(value).strip() or parsed < 0:
        raise _RowError(f"{label} is not a nonnegative integer")
    return parsed


def _optional_elapsed(value: Any) -> int | None:
    return _optional_counter(value, "elapsed_ms")


def _acceptance(row: Mapping[str, Any]) -> str:
    raw_acceptance = row.get("acceptance")
    raw_accepted = row.get("accepted")
    acceptance: str | None = None
    if isinstance(raw_acceptance, str) and raw_acceptance.strip():
        acceptance = raw_acceptance.strip().lower()
    if isinstance(raw_accepted, str) and raw_accepted.strip():
        value = raw_accepted.strip().lower()
        boolean_map = {
            "true": "accepted",
            "yes": "accepted",
            "1": "accepted",
            "false": "not_accepted",
            "no": "not_accepted",
            "0": "not_accepted",
        }
        if value not in boolean_map:
            raise _RowError("accepted is not a supported boolean")
        from_boolean = boolean_map[value]
        if acceptance is not None and acceptance != from_boolean:
            raise _RowError("acceptance and accepted disagree")
        acceptance = from_boolean
    if acceptance not in {"accepted", "not_accepted", "unverified"}:
        raise _RowError("acceptance is not accepted, not_accepted, or unverified")
    return acceptance


def _verdict(acceptance: str) -> str:
    return {
        "accepted": "pass",
        "not_accepted": "fail",
        "unverified": "unverified",
    }[acceptance]


def _attempt_id(run_id: str) -> str:
    candidate = f"benchmark:{run_id}"
    if not _ATTEMPT_ID_RE.fullmatch(candidate):
        raise _RowError("run_id cannot form a valid deterministic attempt id")
    return candidate


def _source_csv_path(
    sidecar_path: Path,
    source_ref: str,
    explicit: str | Path | None,
) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    referenced = Path(source_ref).expanduser()
    if referenced.is_absolute():
        return referenced
    for parent in (sidecar_path.parent, *sidecar_path.parents):
        candidate = parent / referenced
        if candidate.is_file():
            return candidate
    raise EvidenceImportError(
        f"cannot resolve source_csv.path {source_ref!r} from {sidecar_path}; "
        "supply --csv"
    )


def _validated_class(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != _CLASS_FIELDS:
        raise EvidenceImportError(f"{label} is not an exact Phase-1 class block")
    try:
        validate_class_block(value, document="benchmark sidecar", path=label)
    except (KeyError, TypeError, StaffingCatalogError) as exc:
        raise EvidenceImportError(f"{label} is not canonical: {exc}") from exc
    return value


def _sidecar_index(document: Mapping[str, Any]) -> dict[str, _RunMetadata]:
    if document.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise EvidenceImportError(
            "benchmark sidecar schema_version must be " f"{BENCHMARK_SCHEMA_VERSION!r}"
        )
    _aware_timestamp(document.get("generated_at"), "sidecar generated_at")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise EvidenceImportError("benchmark sidecar rows is not an array")
    index: dict[str, _RunMetadata] = {}
    for sidecar_number, item in enumerate(rows, start=1):
        label = f"sidecar rows[{sidecar_number - 1}]"
        if not isinstance(item, dict):
            raise EvidenceImportError(f"{label} is not an object")
        task_key = item.get("task_key")
        if not isinstance(task_key, str) or not task_key:
            raise EvidenceImportError(f"{label}.task_key is missing or empty")
        class_record = _validated_class(item.get("class"), f"{label}.class")
        worker = item.get("worker")
        if not isinstance(worker, dict):
            raise EvidenceImportError(f"{label}.worker is not an object")
        run_ids = item.get("run_ids")
        run_usage = item.get("run_usage")
        if not isinstance(run_ids, list) or not isinstance(run_usage, list):
            raise EvidenceImportError(f"{label} lacks run_ids or run_usage arrays")
        usage_by_id: dict[str, Mapping[str, Any]] = {}
        for usage_item in run_usage:
            if not isinstance(usage_item, dict):
                raise EvidenceImportError(f"{label}.run_usage contains a non-object")
            run_id = usage_item.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise EvidenceImportError(f"{label}.run_usage has an invalid run_id")
            if run_id in usage_by_id:
                raise EvidenceImportError(f"duplicate sidecar run_usage id {run_id!r}")
            usage_by_id[run_id] = usage_item
        for run_id in run_ids:
            if not isinstance(run_id, str) or not run_id:
                raise EvidenceImportError(f"{label}.run_ids has an invalid run id")
            if run_id in index:
                raise EvidenceImportError(f"duplicate sidecar run id {run_id!r}")
            if run_id not in usage_by_id:
                raise EvidenceImportError(f"sidecar run {run_id!r} lacks run_usage")
            index[run_id] = _RunMetadata(
                task_key=task_key,
                class_record=class_record,
                worker=worker,
                usage=usage_by_id[run_id],
            )
        extra_usage = set(usage_by_id) - set(run_ids)
        if extra_usage:
            raise EvidenceImportError(
                f"{label}.run_usage contains ids absent from run_ids: "
                f"{sorted(extra_usage)!r}"
            )
    return index


def _row_usage(row: Mapping[str, Any]) -> dict[str, Any]:
    source_status = row.get("usage_status")
    # ``partial`` means the provider receipt omitted some optional semantic
    # detail, not that its reported counters are estimates. Preserve every
    # supplied counter exactly. ``unknown`` has no authoritative counters and
    # cannot truthfully become a provider_reported attempt.
    if source_status not in (None, "", "known", "partial"):
        raise _RowError(
            f"usage_status {source_status!r} is not provider-reported usage"
        )
    parsed = {
        column: _optional_counter(row.get(column), column) for column in TOKEN_COLUMNS
    }
    if parsed["usage_input_tokens"] is None:
        raise _RowError("usage_input_tokens is unavailable")
    if parsed["usage_output_tokens"] is None:
        raise _RowError("usage_output_tokens is unavailable")
    return {
        "basis": "provider_reported",
        "source": BENCHMARK_USAGE_SOURCE,
        "input_tokens": parsed["usage_input_tokens"],
        "output_tokens": parsed["usage_output_tokens"],
        "cached_input_tokens": parsed["usage_cached_input_tokens"],
        "reasoning_tokens": parsed["usage_reasoning_tokens"],
        "total_tokens": parsed["usage_total_tokens"],
    }


def _verify_join(
    row: Mapping[str, Any], metadata: _RunMetadata, usage: Mapping[str, Any]
) -> None:
    task_key = _required_text(row.get("task_key"), "task_key")
    if task_key != metadata.task_key:
        raise _RowError("task_key disagrees with the v6 sidecar")
    for field in ("model", "harness", "effort"):
        csv_value = row.get(field)
        sidecar_value = metadata.worker.get(field)
        if (csv_value or "") != (sidecar_value or ""):
            raise _RowError(f"{field} disagrees with the v6 sidecar")
    for source_name, record_name in (
        ("usage_input_tokens", "input_tokens"),
        ("usage_output_tokens", "output_tokens"),
        ("usage_cached_input_tokens", "cached_input_tokens"),
        ("usage_reasoning_tokens", "reasoning_tokens"),
        ("usage_total_tokens", "total_tokens"),
    ):
        expected = metadata.usage.get(source_name)
        if usage[record_name] != expected:
            raise _RowError(f"{source_name} disagrees with sidecar run_usage")


def _timestamp_note(row: Mapping[str, Any]) -> str:
    timestamps = [
        f"{name}={row[name]}"
        for name in (
            "run_created_at",
            "launch_created_at",
            "started_at",
            "finished_at",
            "captured_at",
            "evaluation_created_at",
        )
        if isinstance(row.get(name), str) and row[name]
    ]
    return "Source row timestamps: " + ", ".join(timestamps)


def _build_record(
    row: Mapping[str, Any],
    metadata: _RunMetadata,
    *,
    sidecar_path: Path,
    csv_path: Path,
    sidecar_sha256: str,
    source_csv_sha256: str,
    generated_at: str,
) -> dict[str, Any]:
    run_id = _required_text(row.get("run_id"), "run_id")
    attempt_id = _attempt_id(run_id)
    usage = _row_usage(row)
    _verify_join(row, metadata, usage)
    acceptance = _acceptance(row)
    captured_at = _aware_timestamp(row.get("captured_at"), "captured_at")
    elapsed_ms = _optional_elapsed(row.get("elapsed_ms"))
    model = _required_text(row.get("model"), "model")
    harness = _required_text(row.get("harness"), "harness")
    model_family = _required_text(metadata.worker.get("model_family"), "model_family")
    effort_raw = row.get("effort")
    if not isinstance(effort_raw, str):
        raise _RowError("effort is not text")
    effort = effort_raw or None
    role = metadata.class_record["role"]
    stage = _ROLE_STAGE.get(role)
    if stage is None:
        raise _RowError(f"class role {role!r} cannot map to a benchmark stage")

    # The committed v2 schema embeds the older named-crew payload.  Per-run
    # CSV evidence predates that envelope, so this uses its least-specific
    # mixed crew and a single role-derived stage.  The notes explicitly mark
    # those fields as compatibility structure, not facts about source routing.
    benchmark_run = {
        "schema_version": "benchmark.crew-run/1",
        "crew_name": "mixed-economy",
        "crews_file_sha256": sidecar_sha256,
        "mission": {
            "task_key": metadata.task_key,
            "role_composition": [stage],
        },
        "attempt_id": attempt_id,
        "stages": [
            {
                "stage": stage,
                "worker": {
                    "model": model,
                    "harness": harness,
                    "effort": effort,
                    "model_family": model_family,
                },
                "run_id": run_id,
                "cost_low_usd": None,
                "cost_high_usd": None,
                "elapsed_ms": elapsed_ms,
                "acceptance": acceptance,
                "pricing_snapshot_ref": None,
                "pricing_snapshot_sha256": None,
                "evidence_status": "measured",
            }
        ],
        "totals": {
            "cost_low_usd": None,
            "cost_high_usd": None,
            "elapsed_ms": elapsed_ms,
            "stage_count": 1,
            "priced_stage_count": 0,
            "timed_stage_count": 1 if elapsed_ms is not None else 0,
        },
        "final_acceptance": acceptance,
        "provenance": {
            "assembled_by": "lee-llm-router evidence import",
            "assembled_at": generated_at,
            "source_csv_sha256": source_csv_sha256,
            "notes": [
                "Single-run compatibility projection from benchmark v6 CSV; "
                "mixed-economy and the role-derived stage do not assert that "
                "the historical run belonged to a named crew.",
                "crews_file_sha256 carries the verified v6 sidecar digest; the "
                "per-run CSV does not identify a crews file.",
            ],
        },
    }
    record = {
        "schema_version": 2,
        "attempt_id": attempt_id,
        "record_kind": "benchmark_run",
        "captured_at": captured_at,
        "verified_success": False,
        "class_record": dict(metadata.class_record),
        "verdict": _verdict(acceptance),
        "usage": usage,
        "cost": {"basis": ["unavailable"]},
        "wall_clock_ms": elapsed_ms,
        "benchmark_run": benchmark_run,
        "provenance": {
            "source": "benchmark",
            "recorded_by": "lee-llm-router evidence import",
            "source_refs": [str(sidecar_path), str(csv_path)],
            "notes": [
                "No route or supervisor route is asserted because the source "
                "does not identify a staffing channel.",
                "Canonical cost is unavailable: source API-equivalent figures "
                "are not Phase-1 list and marginal costs for a selected route.",
                _timestamp_note(row),
            ],
        },
    }
    validate_attempt(record)
    return record


def import_benchmark_evidence(
    sidecar: str | Path,
    *,
    csv_path: str | Path | None = None,
    ledger_path: str | Path | None = None,
) -> ImportSummary:
    """Import valid per-run rows from a benchmark v6 sidecar and source CSV.

    Malformed or unmappable CSV rows are skipped and returned as explicit
    issues.  Structural sidecar errors, a source checksum mismatch, or an
    invalid existing ledger fail the whole operation before any new append.

    Args:
        sidecar: Benchmark v6 staffing-evidence JSON sidecar.
        csv_path: Optional source CSV override.  The file still must match the
            SHA-256 pinned by ``sidecar.source_csv``.
        ledger_path: Optional explicit attempt ledger.  When absent the normal
            app-specific environment/default resolution is used.

    Returns:
        Imported/skipped counts, diagnostics, and resolved ledger path.

    Raises:
        EvidenceImportError: If source-level evidence cannot be verified.
        AttemptLedgerError: If the existing ledger or a built record is
            invalid.
        OSError: If the ledger cannot be read or appended.
    """
    sidecar_path = Path(sidecar).expanduser()
    document, sidecar_bytes = _read_json_object(sidecar_path)
    index = _sidecar_index(document)
    source_csv = document.get("source_csv")
    if not isinstance(source_csv, dict):
        raise EvidenceImportError("benchmark sidecar source_csv is not an object")
    source_ref = source_csv.get("path")
    expected_sha256 = source_csv.get("sha256")
    if not isinstance(source_ref, str) or not source_ref:
        raise EvidenceImportError("benchmark sidecar source_csv.path is missing")
    if not isinstance(expected_sha256, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", expected_sha256
    ):
        raise EvidenceImportError("benchmark sidecar source_csv.sha256 is invalid")
    resolved_csv = _source_csv_path(sidecar_path, source_ref, csv_path)
    try:
        csv_bytes = resolved_csv.read_bytes()
    except OSError as exc:
        raise EvidenceImportError(
            f"cannot read benchmark CSV {resolved_csv}: {exc}"
        ) from exc
    actual_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    if actual_sha256.lower() != expected_sha256.lower():
        raise EvidenceImportError(
            f"benchmark CSV SHA-256 mismatch for {resolved_csv}: "
            f"expected {expected_sha256.lower()}, got {actual_sha256}"
        )

    target = resolve_attempts_path(ledger_path)
    existing = read_attempts(target) if target.is_file() else []
    known_ids = {record["attempt_id"] for record in existing}
    imported = 0
    issues: list[ImportIssue] = []
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceImportError(f"benchmark CSV {resolved_csv} is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise EvidenceImportError(f"benchmark CSV {resolved_csv} has no header")
    required_headers = {
        "run_id",
        "task_key",
        "model",
        "harness",
        "effort",
        "captured_at",
        "usage_input_tokens",
        "usage_output_tokens",
        "usage_cached_input_tokens",
        "usage_reasoning_tokens",
        "usage_total_tokens",
    }
    missing_headers = sorted(required_headers - set(reader.fieldnames))
    if missing_headers:
        raise EvidenceImportError(
            f"benchmark CSV {resolved_csv} is missing columns {missing_headers!r}"
        )

    generated_at = str(document["generated_at"])
    sidecar_sha256 = hashlib.sha256(sidecar_bytes).hexdigest()
    for row_number, row in enumerate(reader, start=2):
        run_id_value = row.get("run_id")
        run_id = run_id_value.strip() if isinstance(run_id_value, str) else None
        try:
            if not run_id:
                raise _RowError("run_id is missing or empty")
            metadata = index.get(run_id)
            if metadata is None:
                raise _RowError("run_id is absent from the v6 sidecar")
            attempt_id = _attempt_id(run_id)
            if attempt_id in known_ids:
                issues.append(
                    ImportIssue(row_number, run_id, "attempt_id already present")
                )
                continue
            record = _build_record(
                row,
                metadata,
                sidecar_path=sidecar_path,
                csv_path=resolved_csv,
                sidecar_sha256=sidecar_sha256,
                source_csv_sha256=actual_sha256,
                generated_at=generated_at,
            )
        except (_RowError, EvidenceImportError, AttemptLedgerError) as exc:
            issues.append(ImportIssue(row_number, run_id, str(exc)))
            continue
        append_attempt(record, target)
        known_ids.add(record["attempt_id"])
        imported += 1

    return ImportSummary(
        imported=imported,
        skipped=len(issues),
        issues=tuple(issues),
        ledger_path=target,
    )


__all__ = [
    "BENCHMARK_SCHEMA_VERSION",
    "BENCHMARK_USAGE_SOURCE",
    "EvidenceImportError",
    "ImportIssue",
    "ImportSummary",
    "import_benchmark_evidence",
]
