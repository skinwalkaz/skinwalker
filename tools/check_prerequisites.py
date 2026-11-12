#!/usr/bin/env python3
"""Collect and validate a sanitized, local-only prerequisite report."""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SCHEMA_VERSION = "1"
EXECUTABLES = ("git", "python3", "terraform", "az")
FIELDS = (
    "Schema-Version",
    "OS-Family",
    "OS-Version",
    "CPU-Architecture",
    "Git-Version",
    "Python-Version",
    "Executable-git",
    "Executable-python3",
    "Executable-terraform",
    "Executable-az",
)
PRIVACY_PATTERNS = (
    ("home-directory path", re.compile(r"(?:/Users/|/home/|[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/])", re.I)),
    ("absolute path", re.compile(r"(?:^|[\s:=])/(?:private|var|etc|opt|usr|tmp)/")),
    ("email address", re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")),
    ("authorization token", re.compile(r"\b(?:Bearer\s+|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})", re.I)),
    ("JWT-like token", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
)
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
VERSION = re.compile(r"\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.]+)?\Z")
OS_FAMILIES = {"Darwin", "Linux", "Windows"}
ARCHITECTURE = re.compile(r"(?:x86_64|AMD64|arm64|aarch64|i[3-6]86|ppc64le|s390x|riscv64)\Z")


class CollectionError(RuntimeError):
    """Raised when an available required tool cannot report its version safely."""


def _version(command: list[str], prefix: str, runner: Callable = subprocess.run) -> str:
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CollectionError(f"{command[0]} version command failed") from exc
    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0 or not output.startswith(prefix):
        raise CollectionError(f"{command[0]} version command failed")
    value = output[len(prefix):].strip().split()[0]
    if not VERSION.fullmatch(value):
        raise CollectionError(f"{command[0]} returned an unsupported version format")
    return value


def collect(
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable = subprocess.run,
) -> dict[str, str]:
    """Collect only allowlisted local facts; executable paths are discarded."""
    availability = {
        name: "Available" if which(name) is not None else "Unavailable"
        for name in EXECUTABLES
    }
    git_version = (
        _version(["git", "--version"], "git version ", runner)
        if availability["git"] == "Available"
        else "Unavailable"
    )
    python_version = (
        _version(["python3", "--version"], "Python ", runner)
        if availability["python3"] == "Available"
        else "Unavailable"
    )
    family = platform.system()
    os_version = platform.mac_ver()[0] if family == "Darwin" else platform.release()
    return {
        "Schema-Version": SCHEMA_VERSION,
        "OS-Family": family,
        "OS-Version": os_version,
        "CPU-Architecture": platform.machine(),
        "Git-Version": git_version,
        "Python-Version": python_version,
        **{f"Executable-{name}": availability[name] for name in EXECUTABLES},
    }


def render(report: dict[str, str]) -> str:
    """Render fields in schema order regardless of mapping insertion order."""
    return "\n".join(f"{field}: {report.get(field, '')}" for field in FIELDS) + "\n"


def validate(text: str) -> list[str]:
    """Return deterministic findings for malformed or sensitive report text."""
    findings: list[str] = []
    for label, pattern in PRIVACY_PATTERNS:
        if pattern.search(text):
            findings.append(f"privacy-sensitive content: {label}")

    values: dict[str, str] = {}
    observed: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line:
            findings.append(f"line {number}: empty line")
            continue
        if ": " not in line:
            findings.append(f"line {number}: malformed field")
            continue
        name, value = line.split(": ", 1)
        if name not in FIELDS:
            findings.append(f"line {number}: unknown field {name!r}")
            continue
        if name in values:
            findings.append(f"line {number}: duplicate field {name!r}")
            continue
        observed.append(name)
        values[name] = value
        if not value:
            findings.append(f"line {number}: empty field {name!r}")

    missing = [field for field in FIELDS if field not in values]
    for field in missing:
        findings.append(f"missing field {field!r}")
    if not missing and observed != list(FIELDS):
        findings.append("fields are not in required order")

    for field, value in values.items():
        if not value:
            continue
        if field == "Schema-Version" and value != SCHEMA_VERSION:
            findings.append("unsupported Schema-Version")
        elif field == "OS-Family" and value not in OS_FAMILIES:
            findings.append("invalid sanitized value for 'OS-Family'")
        elif field == "OS-Version" and not VERSION.fullmatch(value):
            findings.append("invalid version value for 'OS-Version'")
        elif field == "CPU-Architecture" and not ARCHITECTURE.fullmatch(value):
            findings.append("invalid sanitized value for 'CPU-Architecture'")
        elif field.startswith("Executable-") and value not in {"Available", "Unavailable"}:
            findings.append(f"invalid availability value for {field!r}")
        elif field in {"Git-Version", "Python-Version"}:
            if value != "Unavailable" and not VERSION.fullmatch(value):
                findings.append(f"invalid version value for {field!r}")
        elif field not in {"Schema-Version", "OS-Family", "OS-Version", "CPU-Architecture"} and not TOKEN.fullmatch(value):
            findings.append(f"invalid sanitized value for {field!r}")
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", type=Path, metavar="REPORT")
    args = parser.parse_args(argv)
    try:
        text = (
            args.validate.read_text(encoding="utf-8")
            if args.validate
            else render(collect())
        )
    except (CollectionError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    findings = validate(text)
    if findings:
        print(f"FAIL: {len(findings)} finding(s)")
        for finding in findings:
            print(f"FINDING: {finding}")
        return 1
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
