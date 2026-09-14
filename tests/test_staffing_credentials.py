"""Tests for isolated channel-instance credential staging."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lee_llm_router.staffing.credentials import (
    CredentialStagingError,
    resolve_credential_path,
    stage_harness_home,
)

_FAKE_CREDENTIAL = b'{"fake": "credential"}\n'


def _write_credential(tmp_path: Path) -> Path:
    """Write a fabricated credential fixture and return its path."""
    credential_path = tmp_path / "credential.json"
    credential_path.write_bytes(_FAKE_CREDENTIAL)
    return credential_path


def test_resolve_credential_path_uses_credential_ref(tmp_path):
    """A nested credential reference resolves beneath the supplied root."""
    credential_path = tmp_path / "opencode-go" / "b.json"
    credential_path.parent.mkdir()
    credential_path.write_bytes(_FAKE_CREDENTIAL)

    resolved = resolve_credential_path("opencode-go/b", root=tmp_path)

    assert resolved == credential_path


def test_resolve_credential_path_missing_credential(tmp_path):
    """A missing reference fails closed with a stable error kind."""
    with pytest.raises(CredentialStagingError) as raised:
        resolve_credential_path("opencode-go/missing", root=tmp_path)

    assert raised.value.kind == "missing_credential"


def test_stage_opencode_home_copies_credential_and_cleans_up(tmp_path):
    """OpenCode receives its auth file beneath the staged HOME."""
    credential_path = _write_credential(tmp_path)

    with stage_harness_home("opencode", credential_path) as env:
        staging_home = Path(env["HOME"])
        auth_path = staging_home / ".local/share/opencode/auth.json"

        assert auth_path.read_bytes() == _FAKE_CREDENTIAL
        assert auth_path.read_bytes() == credential_path.read_bytes()

    assert not staging_home.exists()


def test_stage_pi_home_copies_credential_and_cleans_up(tmp_path):
    """Pi receives HOME and its explicit agent-directory override."""
    credential_path = _write_credential(tmp_path)

    with stage_harness_home("pi", credential_path) as env:
        staging_home = Path(env["HOME"])
        pi_agent_dir = Path(env["PI_CODING_AGENT_DIR"])
        auth_path = pi_agent_dir / "auth.json"

        assert pi_agent_dir == staging_home / ".pi/agent"
        assert auth_path.read_bytes() == _FAKE_CREDENTIAL
        assert auth_path.read_bytes() == credential_path.read_bytes()

    assert not staging_home.exists()


def test_stage_omp_is_unsupported_before_temp_directory_creation(tmp_path, monkeypatch):
    """Unsupported harnesses fail closed without allocating a staging home."""
    credential_path = _write_credential(tmp_path)

    def unexpected_mkdtemp(*args, **kwargs):
        pytest.fail("unsupported harness allocated a temporary directory")

    monkeypatch.setattr(tempfile, "mkdtemp", unexpected_mkdtemp)

    with pytest.raises(CredentialStagingError) as raised:
        stage_harness_home("omp", credential_path)

    assert raised.value.kind == "unsupported_harness"


def test_stage_home_cleans_up_on_exception(tmp_path):
    """The temporary home is removed when the caller's block raises."""
    credential_path = _write_credential(tmp_path)

    with pytest.raises(RuntimeError, match="stop"):
        with stage_harness_home("opencode", credential_path) as env:
            staging_home = Path(env["HOME"])
            raise RuntimeError("stop")

    assert not staging_home.exists()
