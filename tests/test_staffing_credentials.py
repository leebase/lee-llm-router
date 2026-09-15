"""Tests for isolated channel-instance credential staging."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

import pytest

from lee_llm_router.staffing.credentials import (
    CredentialStagingError,
    resolve_credential_path,
    stage_harness_home,
)

_FAKE_CREDENTIAL_DATA = {
    "type": "api",
    "key": "secret",
    "instance_id": "b",
    "placed_at": "2026-09-14T00:00:00Z",
    "placed_by": "test-suite",
}
_FAKE_CREDENTIAL = json.dumps(_FAKE_CREDENTIAL_DATA).encode("utf-8")


def _write_credential(tmp_path: Path, data: dict | None = None) -> Path:
    """Write a fabricated credential fixture and return its path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    credential_path = tmp_path / "credential.json"
    if data is not None:
        credential_path.write_text(json.dumps(data), encoding="utf-8")
    else:
        credential_path.write_bytes(_FAKE_CREDENTIAL)
    return credential_path


def test_resolve_credential_path_uses_credential_ref(tmp_path):
    """A nested credential reference resolves beneath the supplied root."""
    credential_path = tmp_path / "opencode-go" / "b.json"
    credential_path.parent.mkdir(parents=True, exist_ok=True)
    credential_path.write_bytes(_FAKE_CREDENTIAL)

    resolved = resolve_credential_path("opencode-go/b", root=tmp_path)

    assert resolved == credential_path


def test_resolve_credential_path_missing_credential(tmp_path):
    """A missing reference fails closed with a stable error kind."""
    with pytest.raises(CredentialStagingError) as raised:
        resolve_credential_path("opencode-go/missing", root=tmp_path)

    assert raised.value.kind == "missing_credential"


def test_resolve_credential_path_path_traversal_rejected_before_existence(tmp_path):
    """A traversal credential_ref is rejected before existence check."""
    creds_root = tmp_path / "credentials"
    creds_root.mkdir()

    # Even if the traversal target exists on the test machine, it must be rejected
    outside_target = tmp_path / "target.json"
    outside_target.write_bytes(_FAKE_CREDENTIAL)

    with pytest.raises(CredentialStagingError) as raised:
        resolve_credential_path("../target", root=creds_root)
    assert raised.value.kind == "invalid_credential_ref"

    with pytest.raises(CredentialStagingError) as raised2:
        resolve_credential_path("../outside/ref", root=creds_root)
    assert raised2.value.kind == "invalid_credential_ref"

    with pytest.raises(CredentialStagingError) as raised3:
        resolve_credential_path("/abs/outside/ref", root=creds_root)
    assert raised3.value.kind == "invalid_credential_ref"


def test_resolve_credential_path_rejects_backslash(tmp_path):
    """Any credential reference containing a backslash is rejected."""
    creds_root = tmp_path / "credentials"
    creds_root.mkdir()

    for ref in ("opencode-go\\b", "..\\outside\\ref", "\\abs\\ref", "nested\\dir/b"):
        with pytest.raises(CredentialStagingError) as raised:
            resolve_credential_path(ref, root=creds_root)
        assert raised.value.kind == "invalid_credential_ref"


def test_stage_opencode_home_wraps_provider_key_and_strips_bookkeeping(tmp_path):
    """OpenCode receives auth.json wrapped under provider_key without bookkeeping."""
    credential_path = _write_credential(tmp_path)

    with stage_harness_home(
        "opencode", credential_path, provider_key="opencode-go"
    ) as env:
        staging_home = Path(env["HOME"])
        auth_path = staging_home / ".local/share/opencode/auth.json"

        assert auth_path.is_file()
        assert stat.S_IMODE(auth_path.stat().st_mode) == 0o600
        parsed = json.loads(auth_path.read_text(encoding="utf-8"))
        assert parsed == {"opencode-go": {"type": "api", "key": "secret"}}

    assert not staging_home.exists()


def test_stage_pi_home_wraps_provider_key_and_strips_bookkeeping(tmp_path):
    """Pi receives auth.json under provider_key and agent-dir override."""
    credential_path = _write_credential(tmp_path)

    with stage_harness_home("pi", credential_path, provider_key="opencode-go") as env:
        staging_home = Path(env["HOME"])
        pi_agent_dir = Path(env["PI_CODING_AGENT_DIR"])
        auth_path = pi_agent_dir / "auth.json"

        assert pi_agent_dir == staging_home / ".pi/agent"
        assert auth_path.is_file()
        assert stat.S_IMODE(auth_path.stat().st_mode) == 0o600
        parsed = json.loads(auth_path.read_text(encoding="utf-8"))
        assert parsed == {"opencode-go": {"type": "api_key", "key": "secret"}}

    assert not staging_home.exists()


def test_stage_harness_home_staged_file_mode_0600(tmp_path):
    """Staged auth files have permissions mode 0600 for both harnesses."""
    credential_path = _write_credential(tmp_path)

    with stage_harness_home(
        "opencode", credential_path, provider_key="opencode-go"
    ) as env:
        opencode_auth = Path(env["HOME"]) / ".local/share/opencode/auth.json"
        assert stat.S_IMODE(opencode_auth.stat().st_mode) == 0o600

    with stage_harness_home("pi", credential_path, provider_key="opencode-go") as env:
        pi_auth = Path(env["PI_CODING_AGENT_DIR"]) / "auth.json"
        assert stat.S_IMODE(pi_auth.stat().st_mode) == 0o600


def test_stage_harness_home_malformed_credential_missing_keys(tmp_path):
    """Missing or non-string 'key' raises malformed_credential."""
    # Missing 'key'
    cred_no_key = _write_credential(tmp_path / "dir1", {"type": "api"})
    with pytest.raises(CredentialStagingError) as raised1:
        with stage_harness_home("opencode", cred_no_key, provider_key="opencode-go"):
            pass
    assert raised1.value.kind == "malformed_credential"

    # Non-string 'key'
    non_str_key = _write_credential(tmp_path / "dir2", {"key": 123})
    with pytest.raises(CredentialStagingError) as raised2:
        with stage_harness_home("opencode", non_str_key, provider_key="opencode-go"):
            pass
    assert raised2.value.kind == "malformed_credential"

    # Invalid JSON
    invalid_json_file = tmp_path / "dir3" / "credential.json"
    invalid_json_file.parent.mkdir(parents=True, exist_ok=True)
    invalid_json_file.write_text("not json content", encoding="utf-8")
    with pytest.raises(CredentialStagingError) as raised3:
        with stage_harness_home(
            "opencode", invalid_json_file, provider_key="opencode-go"
        ):
            pass
    assert raised3.value.kind == "malformed_credential"

    # Non-dict JSON
    non_dict_file = tmp_path / "dir4" / "credential.json"
    non_dict_file.parent.mkdir(parents=True, exist_ok=True)
    non_dict_file.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    with pytest.raises(CredentialStagingError) as raised4:
        with stage_harness_home("opencode", non_dict_file, provider_key="opencode-go"):
            pass
    assert raised4.value.kind == "malformed_credential"


def test_stage_harness_home_ignores_stored_type(tmp_path):
    """Stored 'type' is ignored; harness literal is used instead."""
    cred_no_type = _write_credential(tmp_path / "no_type", {"key": "secret1"})
    cred_other_type = _write_credential(
        tmp_path / "other_type", {"type": "custom", "key": "secret2"}
    )
    cred_non_str_type = _write_credential(
        tmp_path / "non_str_type", {"type": 999, "key": "secret3"}
    )

    for cred_path, expected_key in [
        (cred_no_type, "secret1"),
        (cred_other_type, "secret2"),
        (cred_non_str_type, "secret3"),
    ]:
        with stage_harness_home(
            "opencode", cred_path, provider_key="opencode-go"
        ) as env:
            auth_path = Path(env["HOME"]) / ".local/share/opencode/auth.json"
            parsed = json.loads(auth_path.read_text(encoding="utf-8"))
            assert parsed == {"opencode-go": {"type": "api", "key": expected_key}}

        with stage_harness_home("pi", cred_path, provider_key="opencode-go") as env:
            auth_path = Path(env["PI_CODING_AGENT_DIR"]) / "auth.json"
            parsed = json.loads(auth_path.read_text(encoding="utf-8"))
            assert parsed == {"opencode-go": {"type": "api_key", "key": expected_key}}


def test_stage_harness_home_invalid_utf8_raises_malformed_credential(tmp_path):
    """A credential file with invalid UTF-8 raises CredentialStagingError."""
    credential_path = tmp_path / "credential.json"
    credential_path.write_bytes(b"\xff\xfe\x00invalid")

    with pytest.raises(CredentialStagingError) as raised:
        with stage_harness_home(
            "opencode", credential_path, provider_key="opencode-go"
        ):
            pass

    assert raised.value.kind == "malformed_credential"
    assert isinstance(raised.value.__cause__, UnicodeDecodeError)


def test_stage_harness_home_oserror_raises_staging_failed(tmp_path, monkeypatch):
    """An OSError during staging operations raises staging_failed."""
    credential_path = _write_credential(tmp_path)

    orig_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if "auth.json" in str(self):
            raise OSError("disk write failed")
        return orig_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(CredentialStagingError) as raised:
        with stage_harness_home(
            "opencode", credential_path, provider_key="opencode-go"
        ):
            pass

    assert raised.value.kind == "staging_failed"
    assert isinstance(raised.value.__cause__, OSError)

    monkeypatch.undo()
    orig_chmod = os.chmod

    def failing_chmod(path, mode, *args, **kwargs):
        if "auth.json" in str(path):
            raise OSError("chmod failed")
        return orig_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(os, "chmod", failing_chmod)

    with pytest.raises(CredentialStagingError) as raised_chmod:
        with stage_harness_home(
            "opencode", credential_path, provider_key="opencode-go"
        ):
            pass

    assert raised_chmod.value.kind == "staging_failed"
    assert isinstance(raised_chmod.value.__cause__, OSError)


def test_stage_omp_is_unsupported_before_temp_directory_creation(tmp_path, monkeypatch):
    """Unsupported harnesses fail closed without allocating a staging home."""
    credential_path = _write_credential(tmp_path)

    def unexpected_mkdtemp(*args, **kwargs):
        pytest.fail("unsupported harness allocated a temporary directory")

    monkeypatch.setattr(tempfile, "mkdtemp", unexpected_mkdtemp)

    with pytest.raises(CredentialStagingError) as raised:
        stage_harness_home("omp", credential_path, provider_key="opencode-go")

    assert raised.value.kind == "unsupported_harness"


def test_stage_home_cleans_up_on_exception(tmp_path):
    """The temporary home is removed when the caller's block raises."""
    credential_path = _write_credential(tmp_path)

    with pytest.raises(RuntimeError, match="stop"):
        with stage_harness_home(
            "opencode", credential_path, provider_key="opencode-go"
        ) as env:
            staging_home = Path(env["HOME"])
            raise RuntimeError("stop")

    assert not staging_home.exists()
