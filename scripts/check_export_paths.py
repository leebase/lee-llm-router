#!/usr/bin/env python3
"""Deterministic export check for user-specific absolute paths (packet P1-4).

Shipped staffing configuration must never carry a user-specific absolute path
(``/home/<user>/...`` or ``/Users/<user>/...``) as a **runtime** value.
Provenance citations are preserved, never laundered:
``docs/staffing/export-path-classification.md`` is the authority for the rule
implemented here.

An occurrence is *provenance* -- allowed -- if and only if it is:

* in a YAML comment (a comment-only line, or the comment part of a line);
* the value of an ``evidence_ref`` key in ``crews.yaml`` -- the one file where
  the classification doc scopes that key by contract;
* a JSON string that is the value of a ``description``, ``source_refs`` or
  ``source_paths`` key -- directly, or as an element of a list directly under
  one of them.

Every other occurrence is *runtime* and fails the check.  The rule is expressed
over parsed structure and line kind -- never over a list of blessed files, line
numbers or paths -- so it stays correct as the configuration changes.

The checker is standard-library only and never imports ``lee_llm_router``, so it
runs as a pre-flight on a tree that does not install.  It reads configuration and
writes nothing.

Exit status: 0 clean, 1 runtime occurrences found, 2 usage or parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

#: Absolute path under a user home directory: /home/<user>/... or /Users/<user>.
#: Deliberately generic -- no user name and no host is hard-coded.
HOME_PATH_RE = re.compile(r"/(?:home|Users)/[^/\s\"'\\]+")

#: JSON keys whose strings document where a value came from, not what it is.
PROVENANCE_JSON_KEYS = frozenset({"description", "source_refs", "source_paths"})

#: YAML key whose value cites the live block a crew was migrated from.
PROVENANCE_YAML_KEY = "evidence_ref"

#: The one file in which ``evidence_ref`` is a provenance citation by contract.
PROVENANCE_YAML_FILE = "crews.yaml"

#: A YAML mapping key at the head of a line, with its colon.
_YAML_KEY_RE = re.compile(r"^(?P<key>[A-Za-z0-9_][A-Za-z0-9_.-]*):(?:\s|$)")

_JSON_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

#: Repository root, derived from this file so the check runs from any directory.
_REPO_ROOT = Path(__file__).resolve().parents[1]

_VALUE_LIMIT = 160


class CheckError(Exception):
    """A usage or parse error that makes the export check inconclusive."""


@dataclass(frozen=True)
class Occurrence:
    """One user-specific absolute path found at a known structural position."""

    line: int
    key_path: str
    match: str
    value: str


@dataclass(frozen=True)
class Finding:
    """One *runtime* occurrence, i.e. a failure of the export check."""

    file: str
    line: int
    key_path: str
    match: str
    value: str

    def as_dict(self) -> dict[str, object]:
        """Return the machine-readable form of this finding."""
        return {
            "file": self.file,
            "line": self.line,
            "key_path": self.key_path,
            "match": self.match,
            "value": self.value,
        }

    def render(self) -> str:
        """Return the human-readable one-line report form."""
        return (
            f"{self.file}:{self.line}: runtime user-specific path {self.match!r} "
            f"in {self.key_path or '<file>'}: {self.value!r}"
        )


@dataclass(frozen=True)
class _Level:
    """One open indentation level of the YAML key path being tracked."""

    indent: int
    path: str


def _clip(text: str) -> str:
    """Collapse whitespace and truncate a value for a single-line report."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= _VALUE_LIMIT:
        return collapsed
    return collapsed[: _VALUE_LIMIT - 3] + "..."


def _comment_start(line: str) -> int | None:
    """Return the index where an unquoted YAML comment starts, else None.

    A ``#`` opens a comment only at the start of a line or after whitespace, and
    never inside a quoted scalar.  This is line-kind logic, so it needs no list
    of known comments.
    """
    quote = ""
    index = 0
    while index < len(line):
        char = line[index]
        if quote == '"':
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quote = ""
        elif quote == "'":
            if char == "'":
                if line[index + 1 : index + 2] == "'":
                    index += 2
                    continue
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            return index
        index += 1
    return None


def _yaml_occurrences(text: str, *, evidence_ref_allowed: bool) -> Iterator[Occurrence]:
    """Yield candidate occurrences in YAML, tracking each one's key path.

    Comment lines and the comment part of any line are skipped outright: a path
    there is documentation and is never read.  ``evidence_ref`` is a provenance
    key only in the one file whose contract defines it
    (``evidence_ref_allowed``); the same key anywhere else is a runtime key.
    The block-scalar ``evidence_ref: |`` form follows from the same rule: every
    content line inherits the open ``evidence_ref`` key at the head of its path.
    """
    stack: list[_Level] = []
    counters: dict[tuple[str, int], int] = {}
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        start = _comment_start(line)
        content = line if start is None else line[:start]
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip(" "))
        body = content[indent:]
        item: _Level | None = None
        if body.startswith("-"):
            body = body[1:]
            inner = len(body) - len(body.lstrip(" "))
            key_indent = indent + 1 + inner
            body = body.lstrip(" ")
            while stack and stack[-1].indent >= indent:
                stack.pop()
            parent = stack[-1].path if stack else ""
            seen = counters.get((parent, indent), 0)
            counters[(parent, indent)] = seen + 1
            item = _Level(indent=indent, path=f"{parent}[{seen}]")
        else:
            key_indent = indent
        head = _YAML_KEY_RE.match(body)
        if head is None:
            if item is not None:
                stack.append(item)
                key_path = item.path
            else:
                key_path = stack[-1].path if stack else ""
        else:
            if item is not None:
                stack.append(item)
            else:
                while stack and stack[-1].indent >= key_indent:
                    stack.pop()
            parent = stack[-1].path if stack else ""
            key = head.group("key")
            key_path = f"{parent}.{key}" if parent else key
            stack.append(_Level(indent=key_indent, path=key_path))
        if evidence_ref_allowed and key_path.rsplit(".", 1)[-1] == PROVENANCE_YAML_KEY:
            continue
        value = _clip(content)
        for match in HOME_PATH_RE.finditer(content):
            yield Occurrence(number, key_path, match.group(0), value)


class _JsonScanner:
    """Minimal JSON reader that records the key path and line of every string."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0
        self._line = 1
        self.strings: list[tuple[int, tuple[str, ...], str]] = []

    def parse(self) -> None:
        """Parse the whole document, recording every string it contains."""
        self._parse_value(())
        self._skip_ws()
        if self._pos != len(self._text):
            raise CheckError("trailing data after the top-level JSON value")

    def _skip_ws(self) -> None:
        text = self._text
        start = self._pos
        while self._pos < len(text) and text[self._pos] in " \t\r\n":
            self._pos += 1
        self._line += text.count("\n", start, self._pos)

    def _advance(self, count: int) -> None:
        self._line += self._text[self._pos : self._pos + count].count("\n")
        self._pos += count

    def _read_string(self, path: tuple[str, ...] | None) -> str:
        if self._pos >= len(self._text) or self._text[self._pos] != '"':
            raise CheckError(f"expected a JSON string on line {self._line}")
        start_line = self._line
        index = self._pos + 1
        decoded: list[str] = []
        while True:
            if index >= len(self._text):
                raise CheckError("unterminated JSON string")
            char = self._text[index]
            if char == "\\":
                escape = self._text[index + 1 : index + 2]
                if escape == "u":
                    try:
                        decoded.append(chr(int(self._text[index + 2 : index + 6], 16)))
                    except ValueError as error:
                        raise CheckError("invalid \\u escape in JSON string") from error
                    index += 6
                else:
                    decoded.append(_JSON_ESCAPES.get(escape, escape))
                    index += 2
                continue
            if char == '"':
                index += 1
                break
            decoded.append(char)
            index += 1
        self._advance(index - self._pos)
        value = "".join(decoded)
        if path is not None:
            self.strings.append((start_line, path, value))
        return value

    def _parse_value(self, path: tuple[str, ...]) -> None:
        self._skip_ws()
        if self._pos >= len(self._text):
            raise CheckError("unexpected end of JSON text")
        char = self._text[self._pos]
        if char == "{":
            self._parse_object(path)
        elif char == "[":
            self._parse_array(path)
        elif char == '"':
            self._read_string(path)
        else:
            self._parse_primitive()

    def _parse_object(self, path: tuple[str, ...]) -> None:
        self._advance(1)
        self._skip_ws()
        if self._text[self._pos : self._pos + 1] == "}":
            self._advance(1)
            return
        while True:
            self._skip_ws()
            key = self._read_string(None)
            self._skip_ws()
            if self._text[self._pos : self._pos + 1] != ":":
                raise CheckError(f"expected ':' on line {self._line}")
            self._advance(1)
            self._parse_value(path + (key,))
            self._skip_ws()
            char = self._text[self._pos : self._pos + 1]
            self._advance(1)
            if char == "}":
                return
            if char != ",":
                raise CheckError(f"expected ',' or '}}' on line {self._line}")

    def _parse_array(self, path: tuple[str, ...]) -> None:
        self._advance(1)
        self._skip_ws()
        if self._text[self._pos : self._pos + 1] == "]":
            self._advance(1)
            return
        index = 0
        while True:
            self._parse_value(path + (f"[{index}]",))
            index += 1
            self._skip_ws()
            char = self._text[self._pos : self._pos + 1]
            self._advance(1)
            if char == "]":
                return
            if char != ",":
                raise CheckError(f"expected ',' or ']' on line {self._line}")

    def _parse_primitive(self) -> None:
        start = self._pos
        while self._pos < len(self._text) and self._text[self._pos] not in ",]} \t\r\n":
            self._advance(1)
        if self._pos == start:
            raise CheckError(f"unexpected character on line {self._line}")


def _render_path(path: tuple[str, ...]) -> str:
    """Render a JSON key path, attaching index segments to their parent."""
    rendered = ""
    for segment in path:
        if segment.startswith("["):
            rendered += segment
        elif rendered:
            rendered += f".{segment}"
        else:
            rendered = segment
    return rendered


def _json_provenance(path: tuple[str, ...]) -> bool:
    """Return True when a string at ``path`` documents provenance, not runtime.

    The string must be the *value* of a provenance key: either directly (the
    path ends at that key) or as an element of a list directly under one (the
    path ends at an ``[index]`` segment whose immediate parent is that key).  A
    mapping merely nested somewhere beneath a provenance key holds runtime data.
    """
    if not path:
        return False
    if path[-1] in PROVENANCE_JSON_KEYS:
        return True
    return (
        len(path) >= 2 and path[-1].startswith("[") and path[-2] in PROVENANCE_JSON_KEYS
    )


def _json_occurrences(text: str) -> Iterator[Occurrence]:
    """Yield candidate occurrences in JSON, with key path and line.

    A string that is the value of ``description``, ``source_refs`` or
    ``source_paths`` -- directly, or as a list element directly under one --
    documents provenance and is allowed; every other string is runtime data.
    """
    scanner = _JsonScanner(text)
    scanner.parse()
    for line, path, text_value in scanner.strings:
        if _json_provenance(path):
            continue
        value = _clip(text_value)
        for match in HOME_PATH_RE.finditer(text_value):
            yield Occurrence(line, _render_path(path), match.group(0), value)


def _scan_file(path: Path, display: str) -> list[Finding]:
    """Return every runtime occurrence in one scanned configuration file."""
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            occurrences = list(_json_occurrences(text))
        else:
            occurrences = list(
                _yaml_occurrences(
                    text, evidence_ref_allowed=path.name == PROVENANCE_YAML_FILE
                )
            )
    except (CheckError, OSError) as error:
        raise CheckError(f"{display}: {error}") from error
    return [
        Finding(
            file=display,
            line=item.line,
            key_path=item.key_path,
            match=item.match,
            value=item.value,
        )
        for item in occurrences
    ]


def _resolve_staffing_dir(root: Path) -> Path | None:
    """Find the staffing configuration directory under a given root."""
    for candidate in (root / "config" / "staffing", root / "staffing", root):
        if candidate.is_dir() and candidate.name == "staffing":
            return candidate
    return None


def _scan_set(staffing: Path) -> list[Path]:
    """Return the files the export check owns: *.yaml plus schema/*.json."""
    files = sorted(staffing.glob("*.yaml"))
    files += sorted((staffing / "schema").glob("*.json"))
    return files


def _display(path: Path, root: Path) -> str:
    """Return a path for the report, relative to the checked root when possible."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the export check and return its exit status."""
    parser = argparse.ArgumentParser(
        prog="check_export_paths.py",
        description=(
            "Fail when shipped staffing configuration carries a user-specific "
            "absolute path (for example /home/<user>/...) as a runtime value. "
            "Provenance is allowed: YAML comment lines, crews.yaml evidence_ref "
            "values, and JSON strings under description/source_refs/source_paths. "
            "Exits 0 "
            "clean, 1 on findings, 2 on usage or parse errors."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(_REPO_ROOT),
        help=(
            "directory to check: the repository root, its config directory, or "
            "the staffing config directory itself (default: the repository that "
            "contains this script)"
        ),
    )
    parser.add_argument(
        "--json", action="store_true", help="emit a machine-readable report"
    )
    args = parser.parse_args(argv)

    root = Path(args.path).expanduser().resolve()
    staffing = _resolve_staffing_dir(root)
    if staffing is None:
        print(
            f"check_export_paths: no config/staffing directory under {root}",
            file=sys.stderr,
        )
        return 2
    files = _scan_set(staffing)
    if not files:
        print(
            f"check_export_paths: no staffing configuration under {staffing}",
            file=sys.stderr,
        )
        return 2

    scanned: list[str] = []
    findings: list[Finding] = []
    try:
        for path in files:
            display = _display(path, root)
            scanned.append(display)
            findings.extend(_scan_file(path, display))
    except CheckError as error:
        print(f"check_export_paths: {error}", file=sys.stderr)
        return 2

    if args.json:
        document = {
            "ok": not findings,
            "root": str(root),
            "files_scanned": scanned,
            "findings": [finding.as_dict() for finding in findings],
        }
        print(json.dumps(document, indent=2, sort_keys=True))
    elif findings:
        for finding in findings:
            print(finding.render())
        print(
            f"check_export_paths: {len(findings)} runtime occurrence(s) in "
            f"{len(scanned)} file(s)"
        )
    else:
        print(f"check_export_paths: clean, {len(scanned)} file(s) scanned")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
