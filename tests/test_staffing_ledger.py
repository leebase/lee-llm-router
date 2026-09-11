"""Focused P1-3 tests for the append-only attempt ledger.

Authority: D209 via docs/staffing/phase1-contracts.md §Ledger, rollup, and
imports. The ledger is append-only JSONL at
``~/.local/state/lee-llm-router/attempts/<hostname>.jsonl`` with a test-only
state root override; every record is validated against the committed
attempt-record v2 schema before any append and again on read; a short write
raises and is never retried; no rewrite, truncate, or update path exists.

Every test uses ``tmp_path`` and ``monkeypatch`` only: no real state directory
is touched, no env override other than the app-named ones is set, and no
provider is called. All records are the scratch fixtures from P1-2.
"""

from __future__ import annotations

import ast
import json
import os
import socket
import sys
from pathlib import Path

import pytest

from lee_llm_router import events
from lee_llm_router.providers.base import LLMRouterError
from lee_llm_router.staffing import ledger as ledger_module
from lee_llm_router.staffing.ledger import (
    ATTEMPT_RECORD_SCHEMA_PATH,
    ATTEMPTS_FILE_ENV_VAR,
    ATTEMPTS_STATE_ROOT_ENV_VAR,
    DEFAULT_ATTEMPTS_DIR,
    AttemptLedgerError,
    ShortWriteError,
    append_attempt,
    attempt_record_validator,
    encode_attempt,
    load_attempt_record_schema,
    read_attempts,
    resolve_attempts_path,
    validate_attempt,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RECORD = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "staffing"
    / "attempt-record-router-run-unavailable.json"
)
ESCALATION_RECORD = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "staffing"
    / "attempt-record-router-run-escalation.json"
)
ALL_FIXTURE_RECORDS = [
    "attempt-record-agent-orch.json",
    "attempt-record-benchmark-run.json",
    "attempt-record-router-run-unavailable.json",
    "attempt-record-router-run-escalation.json",
    "attempt-record-import-agent-orch-unclassed.json",
    "attempt-record-agent-orch-raw-attempt.json",
]


@pytest.fixture
def valid_record() -> dict:
    return json.loads(FIXTURE_RECORD.read_text(encoding="utf-8"))


@pytest.fixture
def escalation_record() -> dict:
    return json.loads(ESCALATION_RECORD.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def clean_override_env(monkeypatch):
    """Keep the real state out of every test: no override vars are inherited."""
    monkeypatch.delenv(ATTEMPTS_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv(ATTEMPTS_STATE_ROOT_ENV_VAR, raising=False)


# ---------------------------------------------------------------------------
# Schema loading (committed Draft 2020-12 attempt-record v2)
# ---------------------------------------------------------------------------


def test_committed_schema_is_loaded_and_cached() -> None:
    schema = load_attempt_record_schema()
    assert ATTEMPT_RECORD_SCHEMA_PATH.is_file()
    assert schema["properties"]["schema_version"]["const"] == 2
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert load_attempt_record_schema() is schema


def test_validator_accepts_the_p1_2_fixture(valid_record: dict) -> None:
    assert not list(attempt_record_validator().iter_errors(valid_record))


# ---------------------------------------------------------------------------
# Path resolution: default, env overrides, explicit — never touching real state
# ---------------------------------------------------------------------------


def test_env_override_names_are_app_specific_never_home() -> None:
    for var in (ATTEMPTS_FILE_ENV_VAR, ATTEMPTS_STATE_ROOT_ENV_VAR):
        assert var.startswith("LEE_LLM_ROUTER_"), var
        assert "HOME" not in var
    assert "~" in str(DEFAULT_ATTEMPTS_DIR)
    assert str(DEFAULT_ATTEMPTS_DIR).endswith("lee-llm-router/attempts")


def test_default_path_is_per_host_jsonl_under_the_state_dir() -> None:
    resolved = resolve_attempts_path()
    assert resolved.name == f"{socket.gethostname()}.jsonl"
    assert resolved.parent == DEFAULT_ATTEMPTS_DIR.expanduser()
    assert "~" not in str(resolved)


def test_file_env_var_overrides_the_default(tmp_path, monkeypatch) -> None:
    from_env = tmp_path / "state" / "attempts.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(from_env))
    assert resolve_attempts_path() == from_env


def test_state_root_env_var_overrides_the_state_dir(tmp_path, monkeypatch) -> None:
    root = tmp_path / "alt-root"
    monkeypatch.setenv(ATTEMPTS_STATE_ROOT_ENV_VAR, str(root))
    resolved = resolve_attempts_path()
    assert resolved == root / "attempts" / f"{socket.gethostname()}.jsonl"
    assert not resolved.exists(), "resolution must not create anything"


def test_explicit_path_beats_both_env_overrides(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(tmp_path / "from-file-env.jsonl"))
    monkeypatch.setenv(ATTEMPTS_STATE_ROOT_ENV_VAR, str(tmp_path / "from-root-env"))
    explicit = tmp_path / "explicit.jsonl"
    assert resolve_attempts_path(explicit) == explicit


def test_file_env_var_beats_state_root_env_var(tmp_path, monkeypatch) -> None:
    from_file = tmp_path / "from-file-env.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(from_file))
    monkeypatch.setenv(ATTEMPTS_STATE_ROOT_ENV_VAR, str(tmp_path / "from-root-env"))
    assert resolve_attempts_path() == from_file


def test_append_uses_env_path_when_none_given(tmp_path, monkeypatch) -> None:
    from_env = tmp_path / "state" / "attempts.jsonl"
    monkeypatch.setenv(ATTEMPTS_FILE_ENV_VAR, str(from_env))
    assert append_attempt(json.loads(FIXTURE_RECORD.read_text())) == from_env
    assert len(read_attempts(from_env)) == 1


# ---------------------------------------------------------------------------
# Append: validation before write, single line, permissions, order
# ---------------------------------------------------------------------------


def test_valid_append_then_read_round_trips(tmp_path, valid_record) -> None:
    ledger = tmp_path / "attempts.jsonl"
    written = append_attempt(valid_record, ledger)
    assert written == ledger
    assert read_attempts(ledger) == [valid_record]


def test_multiple_appends_keep_file_order(
    tmp_path, valid_record, escalation_record
) -> None:
    ledger = tmp_path / "attempts.jsonl"
    append_attempt(valid_record, ledger)
    append_attempt(escalation_record, ledger)
    append_attempt(valid_record, ledger)

    records = read_attempts(ledger)
    assert [r["attempt_id"] for r in records] == [
        "pi-run-0001",
        "pi-run-0002",
        "pi-run-0001",
    ]
    assert records[1]["parent_attempt_id"] == "pi-run-0001"


def test_invalid_record_is_refused_before_file_creation(tmp_path, valid_record) -> None:
    ledger = tmp_path / "nested" / "attempts.jsonl"
    bad = dict(valid_record)
    bad["schema_version"] = 1
    with pytest.raises(AttemptLedgerError, match="schema_version"):
        append_attempt(bad, ledger)
    assert not ledger.exists()
    assert not ledger.parent.exists(), "validation happens before any mkdir"


def test_malformed_mapping_is_refused_before_any_write(tmp_path, valid_record) -> None:
    ledger = tmp_path / "attempts.jsonl"
    bad = dict(valid_record)
    bad["verdict"] = "accepted"  # v1 vocabulary; the schema rejects it
    with pytest.raises(AttemptLedgerError, match="\\$.verdict"):
        append_attempt(bad, ledger)
    assert not ledger.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_append_creates_private_file_and_directory(tmp_path, valid_record) -> None:
    ledger = tmp_path / "state" / "attempts" / "host.jsonl"
    append_attempt(valid_record, ledger)
    assert os.stat(ledger).st_mode & 0o777 == 0o600
    assert os.stat(ledger.parent).st_mode & 0o777 == 0o700


def test_embedded_newline_text_stays_one_physical_line(tmp_path, valid_record) -> None:
    record = dict(valid_record)
    record["selection"] = dict(record["selection"], reason="line one\nline two")
    ledger = tmp_path / "attempts.jsonl"

    append_attempt(record, ledger)

    raw = ledger.read_bytes()
    assert raw.count(b"\n") == 1
    assert read_attempts(ledger) == [record]


def test_encoding_is_compact_utf8_with_trailing_newline(valid_record) -> None:
    line = encode_attempt(valid_record)
    expected = json.dumps(
        valid_record, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    assert line == expected + b"\n"
    assert "scratch" in line.decode("utf-8")  # non-ASCII-safe content survives
    assert line.count(b"\n") == 1


def test_encode_rejects_schema_invalid_record(valid_record) -> None:
    bad = dict(valid_record)
    del bad["attempt_id"]
    with pytest.raises(AttemptLedgerError, match="attempt_id"):
        encode_attempt(bad)


def test_validate_attempt_raises_with_all_violations(valid_record) -> None:
    bad = dict(valid_record)
    bad["schema_version"] = 1
    bad["record_kind"] = "interactive"
    with pytest.raises(AttemptLedgerError) as excinfo:
        validate_attempt(bad)
    message = str(excinfo.value)
    assert "$.schema_version" in message and "$.record_kind" in message


# ---------------------------------------------------------------------------
# Single physical write: short write raises, no loop, no retry, no rewrite
# ---------------------------------------------------------------------------


def test_short_write_raises_once_and_never_retries(
    tmp_path, monkeypatch, valid_record
) -> None:
    ledger = tmp_path / "attempts.jsonl"
    calls: list[int] = []
    real_write = os.write

    def short_write(fd, data):
        calls.append(len(data))
        return real_write(fd, data[:5])

    monkeypatch.setattr(ledger_module.os, "write", short_write)
    with pytest.raises(ShortWriteError, match="short write"):
        append_attempt(valid_record, ledger)
    assert len(calls) == 1, "exactly one os.write: no loop, no retry"
    # The five bytes landed (O_APPEND); nothing else was ever written.
    full_line = encode_attempt(valid_record)
    assert ledger.read_bytes() == full_line[:5]
    with pytest.raises(AttemptLedgerError):
        read_attempts(ledger)


def test_short_write_error_is_not_swallowed_or_wrapped(
    tmp_path, monkeypatch, valid_record
) -> None:
    ledger = tmp_path / "attempts.jsonl"

    def zero_write(fd, data):
        return 0

    monkeypatch.setattr(ledger_module.os, "write", zero_write)
    with pytest.raises(ShortWriteError):
        append_attempt(valid_record, ledger)
    assert isinstance(ShortWriteError(1, "x"), OSError)
    assert not issubclass(ShortWriteError, AttemptLedgerError)
    assert not ledger.exists() or ledger.stat().st_size == 0


def test_module_has_exactly_one_append_only_write_path() -> None:
    """Inspection: a single O_APPEND os.write and no rewrite/truncate path."""
    source = Path(ledger_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    opens = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "open"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
    ]
    assert len(opens) == 1, "exactly one os.open call site"
    flags = opens[0].args[1]
    assert isinstance(flags, ast.BinOp) and isinstance(flags.op, ast.BitOr)
    flag_names = {
        node.attr
        for node in ast.walk(flags)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    }
    assert flag_names == {"O_WRONLY", "O_CREAT", "O_APPEND"}, flag_names

    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
        and node.func.attr == "write"
    ]
    assert len(writes) == 1, "exactly one os.write call site"

    identifiers = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for forbidden in ("truncate", "ftruncate", "lseek", "fdatasync"):
        assert forbidden not in identifiers, forbidden
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for mode in ("w", "a", "r+", "w+"):
        assert mode not in literals, f"no file mode {mode!r} anywhere"

    # No update/rewrite/truncate API is exposed.
    for name in dir(ledger_module):
        assert "truncat" not in name and "rewrite" not in name and "update" not in name


def test_module_imports_no_network_subprocess_or_provider_logic() -> None:
    source = Path(ledger_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    roots = {name.split(".")[0] for name in imported}
    assert roots == {
        "__future__",
        "json",
        "math",
        "os",
        "socket",
        "pathlib",
        "typing",
        "jsonschema",
        "lee_llm_router",  # providers.base LLMRouterError only
    }
    forbidden = {"subprocess", "requests", "httpx", "urllib", "http"}
    assert not roots & forbidden


def test_ledger_errors_chain_into_llm_router_error() -> None:
    assert issubclass(AttemptLedgerError, LLMRouterError)
    assert issubclass(ShortWriteError, OSError)


def test_short_write_semantics_match_events_ledger() -> None:
    assert ShortWriteError.__doc__ == events.ShortWriteError.__doc__
    assert issubclass(ShortWriteError, OSError)
    assert not issubclass(ShortWriteError, events.ShortWriteError)


# ---------------------------------------------------------------------------
# Read: strict validation, order, fail-closed diagnostics
# ---------------------------------------------------------------------------


def test_read_attempts_preserves_file_order(
    tmp_path, valid_record, escalation_record
) -> None:
    ledger = tmp_path / "attempts.jsonl"
    append_attempt(valid_record, ledger)
    append_attempt(escalation_record, ledger)
    records = read_attempts(ledger)
    assert [r["attempt_id"] for r in records] == ["pi-run-0001", "pi-run-0002"]
    assert records[0]["verdict"] == "unverified"
    assert records[1]["verdict"] == "fail"


def test_read_attempts_skips_blank_lines(tmp_path, valid_record) -> None:
    ledger = tmp_path / "attempts.jsonl"
    append_attempt(valid_record, ledger)
    with open(ledger, "a", encoding="utf-8") as handle:
        handle.write("\n   \n")
    append_attempt(valid_record, ledger)
    assert len(read_attempts(ledger)) == 2


def test_read_attempts_fails_closed_on_malformed_json(tmp_path, valid_record) -> None:
    ledger = tmp_path / "attempts.jsonl"
    append_attempt(valid_record, ledger)
    with open(ledger, "a", encoding="utf-8") as handle:
        handle.write('{"broken": \n')
    append_attempt(valid_record, ledger)

    with pytest.raises(AttemptLedgerError) as excinfo:
        read_attempts(ledger)
    message = str(excinfo.value)
    assert str(ledger) in message, "diagnostic names the path"
    assert ":2:" in message, "diagnostic names the 1-based line number"
    assert "not valid JSON" in message


def test_read_attempts_fails_closed_on_non_object_line(tmp_path, valid_record) -> None:
    ledger = tmp_path / "attempts.jsonl"
    append_attempt(valid_record, ledger)
    with open(ledger, "a", encoding="utf-8") as handle:
        handle.write("42\n")

    with pytest.raises(AttemptLedgerError) as excinfo:
        read_attempts(ledger)
    assert str(ledger) in str(excinfo.value)
    assert ":2:" in str(excinfo.value)
    assert "not a JSON object" in str(excinfo.value)


def test_read_attempts_fails_closed_on_schema_invalid_record(
    tmp_path, valid_record
) -> None:
    ledger = tmp_path / "attempts.jsonl"
    bad = dict(valid_record)
    bad["usage"]["input_tokens"] = -5
    with open(ledger, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(bad, separators=(",", ":")) + "\n")

    with pytest.raises(AttemptLedgerError) as excinfo:
        read_attempts(ledger)
    message = str(excinfo.value)
    assert str(ledger) in message
    assert ":1:" in message
    assert "$.usage.input_tokens" in message
    assert "minimum" in message


def test_read_attempts_returns_nothing_after_a_bad_line(tmp_path, valid_record) -> None:
    """Fail closed: a good first line is never returned past a bad second."""
    ledger = tmp_path / "attempts.jsonl"
    append_attempt(valid_record, ledger)
    with open(ledger, "a", encoding="utf-8") as handle:
        handle.write("{\n")

    with pytest.raises(AttemptLedgerError):
        read_attempts(ledger)


def test_missing_ledger_file_raises_file_not_found(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        read_attempts(tmp_path / "absent.jsonl")


# ---------------------------------------------------------------------------
# P1-9 gate: evidence-truth rules the schema cannot express portably
# ---------------------------------------------------------------------------


def test_reproducer_class_role_mutation_without_key_update_is_refused(
    tmp_path, escalation_record
) -> None:
    """Astra repro 1: role mutated to 'review' while class_key stays impl/….

    class_record fields and the canonical class_key must be mutually
    consistent for reliable evidence joins; no class-to-model lookup exists.
    """
    bad = dict(escalation_record)
    bad["class_record"] = dict(bad["class_record"], role="review")
    assert bad["class_record"]["class_key"] == (
        "impl/judge/authority+persistence/m/python"
    )
    for call in (validate_attempt, encode_attempt):
        with pytest.raises(AttemptLedgerError, match="class_record.class_key"):
            call(bad)
        with pytest.raises(AttemptLedgerError, match="canonical reconstruction"):
            call(bad)
    ledger = tmp_path / "attempts.jsonl"
    with pytest.raises(AttemptLedgerError, match="class_record.class_key"):
        append_attempt(bad, ledger)
    assert not ledger.exists(), "refused before any byte or directory exists"


def test_consistent_class_record_mutation_still_validates(escalation_record) -> None:
    """The check joins evidence; it never blocks a consistent class block."""
    good = dict(escalation_record)
    good["class_record"] = dict(
        good["class_record"],
        role="review",
        class_key="review/judge/authority+persistence/m/python",
    )
    validate_attempt(good)  # must not raise


def test_unsorted_or_unsorted_key_tags_never_break_the_join(
    escalation_record,
) -> None:
    """The reconstruction sorts tags, so tag order in the list is free."""
    good = dict(escalation_record)
    good["class_record"] = dict(
        good["class_record"], domain_tags=["persistence", "authority"]
    )
    validate_attempt(good)  # canonical key is unchanged: still 'authority+…'


@pytest.mark.parametrize("figure", [float("nan"), float("inf"), float("-inf")])
def test_reproducer_nonfinite_cost_figure_is_refused_everywhere(
    tmp_path, escalation_record, figure
) -> None:
    """Astra repro 2: NaN prices must never reach the strict-JSONL ledger.

    jsonschema cannot express finiteness portably, so validate_attempt rejects
    non-finite floats, encode_attempt additionally encodes with
    allow_nan=False, and read_attempts fails closed on lines json.loads would
    otherwise parse back as NaN.
    """
    bad = dict(escalation_record)
    bad["cost"] = {
        "basis": ["list", "marginal"],
        "usd_list": figure,
        "usd_marginal": 0.008,
    }
    for call in (validate_attempt, encode_attempt):
        with pytest.raises(AttemptLedgerError, match="non-finite float"):
            call(bad)
    ledger = tmp_path / "attempts.jsonl"
    with pytest.raises(AttemptLedgerError, match="non-finite float"):
        append_attempt(bad, ledger)
    assert not ledger.exists()


def test_nonfinite_float_deep_inside_a_payload_is_refused(escalation_record) -> None:
    bad = dict(escalation_record)
    bad["wall_clock_ms"] = float("inf")
    with pytest.raises(AttemptLedgerError) as excinfo:
        encode_attempt(bad)
    assert "$.wall_clock_ms" in str(excinfo.value)


def test_encode_never_emits_nonfinite_json_tokens(escalation_record) -> None:
    """Even without validate_attempt, allow_nan=False keeps JSON strict."""
    bad = dict(escalation_record)
    bad["wall_clock_ms"] = float("nan")
    with pytest.raises(ValueError):  # surfaced as AttemptLedgerError by encode
        json.dumps(bad, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    with pytest.raises(AttemptLedgerError):
        encode_attempt(bad)


def test_read_attempts_fails_closed_on_a_nan_line(tmp_path, escalation_record) -> None:
    """json.loads parses the NaN token; the read path must reject it."""
    ledger = tmp_path / "attempts.jsonl"
    line = json.dumps(escalation_record, separators=(",", ":")).replace(
        '"wall_clock_ms":null', '"wall_clock_ms":NaN'
    )
    assert "NaN" in line
    ledger.write_text(line + "\n", encoding="utf-8")

    with pytest.raises(AttemptLedgerError) as excinfo:
        read_attempts(ledger)
    message = str(excinfo.value)
    assert str(ledger) in message and ":1:" in message
    assert "non-finite float" in message


def test_nonstring_domain_tags_fail_closed_not_crash(
    tmp_path, escalation_record
) -> None:
    """Malformed class_record tags raise AttemptLedgerError, never TypeError.

    Review finding: _evidence_violations joined the tags before schema errors
    were returned, so domain_tags=[1, 2] leaked 'TypeError: sequence item 0:
    expected str instance, int found' on both the validate/write and read
    paths. The gate must fail closed on external JSONL instead.
    """
    bad = dict(escalation_record)
    bad["class_record"] = dict(bad["class_record"], domain_tags=[1, 2])
    for call in (validate_attempt, encode_attempt):
        with pytest.raises(AttemptLedgerError, match="class_record.domain_tags"):
            call(bad)
    append_ledger = tmp_path / "append.jsonl"
    with pytest.raises(AttemptLedgerError, match="class_record.domain_tags"):
        append_attempt(bad, append_ledger)
    assert not append_ledger.exists(), "refused before any byte or directory exists"

    ledger = tmp_path / "read.jsonl"
    ledger.write_text(json.dumps(bad, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(AttemptLedgerError) as excinfo:
        read_attempts(ledger)
    message = str(excinfo.value)
    assert str(ledger) in message and ":1:" in message
    assert "$.class_record.domain_tags" in message


def test_missing_required_class_record_field_fails_closed_not_crash(
    tmp_path, escalation_record
) -> None:
    """A class_record missing a required component must not KeyError.

    Review finding: _evidence_violations indexed class_record fields directly,
    so a missing domain_tags leaked 'KeyError: domain_tags' before the schema
    'required' error could be returned. Both paths must fail closed.
    """
    bad = dict(escalation_record)
    bad["class_record"] = {
        key: value for key, value in bad["class_record"].items() if key != "domain_tags"
    }
    for call in (validate_attempt, encode_attempt):
        with pytest.raises(AttemptLedgerError, match="domain_tags"):
            call(bad)
    append_ledger = tmp_path / "append.jsonl"
    with pytest.raises(AttemptLedgerError, match="domain_tags"):
        append_attempt(bad, append_ledger)
    assert not append_ledger.exists(), "refused before any byte or directory exists"

    ledger = tmp_path / "read.jsonl"
    ledger.write_text(json.dumps(bad, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(AttemptLedgerError) as excinfo:
        read_attempts(ledger)
    message = str(excinfo.value)
    assert str(ledger) in message and ":1:" in message
    assert "domain_tags" in message


def test_reproducer_unavailable_usage_with_retained_counters_is_refused(
    tmp_path, escalation_record
) -> None:
    """Astra repro 3: unavailable must never hide numeric token evidence."""
    bad = dict(escalation_record)
    bad["usage"] = {
        "basis": "unavailable",
        "unavailable_reason": "text mode",
        "input_tokens": 1200,
        "output_tokens": 340,
    }
    for call in (validate_attempt, encode_attempt):
        with pytest.raises(AttemptLedgerError, match="not of type 'null'"):
            call(bad)
    ledger = tmp_path / "attempts.jsonl"
    with pytest.raises(AttemptLedgerError, match="input_tokens"):
        append_attempt(bad, ledger)
    assert not ledger.exists()


def test_unavailable_usage_with_null_or_absent_counters_still_validates(
    escalation_record,
) -> None:
    """Positive real-row shape: unavailable carries null/absent counters."""
    good = dict(escalation_record)
    good["usage"] = {
        "basis": "unavailable",
        "unavailable_reason": "text mode",
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
    }
    validate_attempt(good)  # must not raise


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_RECORDS)
def test_p1_9_legacy_import_and_live_records_round_trip(tmp_path, fixture_name) -> None:
    """Positive: the gate accepts every legacy, import, and live fixture."""
    record = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "staffing" / fixture_name).read_text(
            encoding="utf-8"
        )
    )
    ledger = tmp_path / "roundtrip.jsonl"
    append_attempt(record, ledger)
    assert read_attempts(ledger) == [record]
