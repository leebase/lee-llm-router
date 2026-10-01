"""Trusted host configuration for an argv-only provider transport."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


class ExecutorSpecError(ValueError):
    """The privileged executor configuration or host binding is invalid."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExecutorSpecError("duplicate JSON field")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ExecutorSpecError("nonfinite JSON value")


@dataclass(frozen=True)
class ExecutorSpec:
    """Validated transport and supervisor binding; contains no new grants."""

    employee_id: str
    parent_transaction_id: str
    gap_id: str
    argv_prefix: tuple[str, ...]
    source_sha256: str

    def validate_binding(self, employee_id: str, unit_id: str, decision: Any) -> None:
        """Compare the spec with independently supplied host authority."""
        if (
            employee_id != self.employee_id
            or unit_id != self.parent_transaction_id
            or not isinstance(decision, dict)
            or decision.get("unit_id") != unit_id
        ):
            raise ExecutorSpecError("executor employee/parent binding mismatch")
        dispatch = decision.get("dispatch")
        gaps = decision.get("gaps")
        if (
            not isinstance(dispatch, dict)
            or not isinstance(dispatch.get("targets"), list)
            or self.gap_id not in dispatch["targets"]
            or not isinstance(gaps, list)
            or sum(
                isinstance(gap, dict)
                and gap.get("id") == self.gap_id
                and gap.get("state") in ("OPEN", "BLOCKED")
                for gap in gaps
            )
            != 1
        ):
            raise ExecutorSpecError("executor gap must be an active decision target")

    def binding_environment(self, attempt_id: str) -> Mapping[str, str]:
        """Return read-only host context for the trusted launcher, not authority."""
        return MappingProxyType(
            {
                "LEE_EMPLOYEE_ID": self.employee_id,
                "LEE_EMPLOYEE_PARENT_ID": self.parent_transaction_id,
                "LEE_EMPLOYEE_GAP_ID": self.gap_id,
                "LEE_EMPLOYEE_ATTEMPT_ID": attempt_id,
            }
        )

    def provenance_note(self, attempt_id: str) -> str:
        """Return binding evidence without disclosing launcher arguments."""
        return "protected-executor-v1 " + json.dumps(
            dict(
                attempt_id=attempt_id,
                employee_id=self.employee_id,
                parent_transaction_id=self.parent_transaction_id,
                gap_id=self.gap_id,
                source_sha256=self.source_sha256,
            ),
            sort_keys=True,
        )


def load_executor_spec(path: str) -> ExecutorSpec:
    """Read a bounded canonical nonsymlink host spec with strict v1 fields.

    Args:
        path: Privileged host configuration path, never worker input.

    Returns:
        An immutable validated executor specification.

    Raises:
        ExecutorSpecError: Invalid file, JSON, shape, bounds or executable.
    """
    try:
        source = Path(path)
        if not source.is_absolute() or str(source.resolve(strict=True)) != path:
            raise ExecutorSpecError("executor spec must be canonical and nonsymlink")
        with os.fdopen(
            os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb"
        ) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ExecutorSpecError("executor spec must be a regular file")
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ExecutorSpecError("executor spec exceeds 65536 bytes")
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        fields = {
            "version",
            "employee_id",
            "parent_transaction_id",
            "gap_id",
            "argv_prefix",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ExecutorSpecError("executor spec fields must match v1 exactly")
        if type(value["version"]) is not int or value["version"] != 1:
            raise ExecutorSpecError("executor spec version must be integer 1")
        for key in ("employee_id", "parent_transaction_id", "gap_id"):
            item = value[key]
            if (
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 256
                or any(ord(c) < 32 for c in item)
            ):
                raise ExecutorSpecError("invalid executor binding string")
        argv = value["argv_prefix"]
        if (
            not isinstance(argv, list)
            or not 1 <= len(argv) <= 32
            or any(
                not isinstance(arg, str) or not arg or len(arg) > 4096 or "\x00" in arg
                for arg in argv
            )
        ):
            raise ExecutorSpecError("invalid bounded literal argv_prefix")
        executable = Path(argv[0])
        if (
            not executable.is_absolute()
            or str(executable.resolve(strict=True)) != argv[0]
            or not executable.is_file()
            or not os.access(executable, os.X_OK)
        ):
            raise ExecutorSpecError(
                "executor must be canonical regular executable, no symlink"
            )
        return ExecutorSpec(
            value["employee_id"],
            value["parent_transaction_id"],
            value["gap_id"],
            tuple(argv),
            hashlib.sha256(raw).hexdigest(),
        )
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ExecutorSpecError(str(exc)) from exc
