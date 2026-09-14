"""Stage one channel instance credential for an isolated harness run.

Credential files remain in the router's state directory.  This module only
resolves those files and copies one of them into a temporary home using the
authentication layout expected by a supported harness.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

DEFAULT_CREDENTIALS_DIR = Path("~/.local/state/lee-llm-router/credentials")
"""Directory containing channel-instance credential JSON files."""

__all__ = [
    "DEFAULT_CREDENTIALS_DIR",
    "CredentialStagingError",
    "resolve_credential_path",
    "stage_harness_home",
]


class CredentialStagingError(Exception):
    """Raised when a credential cannot be resolved or staged safely."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind


# The paths are relative to the temporary HOME.  HOME is supplied for every
# harness; the second tuple item names any additional harness-specific
# environment variables and their relative directory under that HOME.
_HARNESS_AUTH_LAYOUTS: dict[str, tuple[Path, tuple[tuple[str, Path], ...]]] = {
    "opencode": (
        Path(".local/share/opencode/auth.json"),
        (),
    ),
    "pi": (
        Path(".pi/agent/auth.json"),
        (("PI_CODING_AGENT_DIR", Path(".pi/agent")),),
    ),
}


def resolve_credential_path(credential_ref: str, *, root: Path | None = None) -> Path:
    """Resolve and validate a channel instance credential reference.

    Args:
        credential_ref: Relative credential identifier, such as
            ``"opencode-go/b"``.
        root: Optional credential directory override, primarily for callers
            using an isolated state directory or tests.

    Returns:
        The existing regular JSON credential file.

    Raises:
        CredentialStagingError: If the referenced path is not a regular file.
    """
    credential_path = (root or DEFAULT_CREDENTIALS_DIR).expanduser() / (
        f"{credential_ref}.json"
    )
    if not credential_path.is_file():
        raise CredentialStagingError(
            f"Credential file does not exist or is not a regular file: "
            f"{credential_path}",
            kind="missing_credential",
        )
    return credential_path


def stage_harness_home(
    harness: str, credential_path: Path
) -> AbstractContextManager[dict[str, str]]:
    """Stage one credential in a temporary home for a supported harness.

    Args:
        harness: Harness name.  Only ``"opencode"`` and ``"pi"`` are
            supported by this JSON-file staging mechanism.
        credential_path: An already-resolved regular credential file.

    Returns:
        A context manager yielding environment overrides for the harness
        subprocess.

    Raises:
        CredentialStagingError: If ``harness`` is not supported.
    """
    layout = _HARNESS_AUTH_LAYOUTS.get(harness)
    if layout is None:
        raise CredentialStagingError(
            f"Credential staging is not supported for harness {harness!r}",
            kind="unsupported_harness",
        )
    return _stage_harness_home(credential_path, layout)


@contextmanager
def _stage_harness_home(
    credential_path: Path,
    layout: tuple[Path, tuple[tuple[str, Path], ...]],
) -> AbstractContextManager[dict[str, str]]:
    """Stage a credential using a previously validated harness layout."""
    auth_relative_path, extra_env = layout
    staging_home = Path(tempfile.mkdtemp(prefix="lee-llm-router-cred-"))
    try:
        auth_path = staging_home / auth_relative_path
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(credential_path, auth_path)

        env = {"HOME": str(staging_home)}
        env.update(
            {
                variable: str(staging_home / relative_directory)
                for variable, relative_directory in extra_env
            }
        )
        yield env
    finally:
        shutil.rmtree(staging_home, ignore_errors=True)
