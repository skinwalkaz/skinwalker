#!/usr/bin/env python3
"""Validate WP-0.3 evidence and Azure cost ledger Markdown tables."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

EVIDENCE_COLUMNS = (
    "Evidence ID",
    "Claim",
    "Requirement",
    "Evidence path or link",
    "Verification command",
    "Git commit",
    "Date",
    "Reviewer",
    "Status",
)
COST_COLUMNS = (
    "Date",
    "Deployment profile",
    "Resources started",
    "Resources destroyed",
    "Estimated retail cost",
    "Credit consumed",
    "Actual charge",
    "Trial days remaining",
    "Notes",
)
STATUSES = {"Open", "Collected", "Needs Review", "Verified", "Failed", "Superseded"}
EVIDENCE_ID = re.compile(r"(?:E|SAMPLE)-(?:SKW|AZ)-\d{3}\Z")
REQUIREMENT_ID = re.compile(r"(?:PROG|SKW|AZ)-\d{2}\Z")
COMMIT = re.compile(r"(?:PENDING|[0-9a-f]{7,40})\Z")
VERIFIED_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
SEPARATOR = re.compile(r":?-{3,}:?\Z")
SAMPLE_MARKER = re.compile(r"(?<!\w)SAMPLE ONLY(?!\w)", re.IGNORECASE)
PLACEHOLDERS = {
    "unassigned",
    "tbd",
    "todo",
    "pending",
    "n/a",
    "na",
    "none",
    "-",
    "placeholder",
    "sample",
}
PLACEHOLDER_REFERENCES = PLACEHOLDERS | {"docs/evidence/example.txt"}


def cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [value.strip() for value in stripped[1:-1].split("|")]


def read_table(
    path: Path, expected: tuple[str, ...]
) -> tuple[list[dict[str, str]], list[str]]:
    findings: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [], [f"{path}: cannot read UTF-8 ledger: {exc}"]
    header_index = next(
        (i for i, line in enumerate(lines) if tuple(cells(line)) == expected), None
    )
    if header_index is None:
        return [], [f"{path}: missing exact required header"]
    if header_index + 1 >= len(lines):
        return [], [f"{path}: missing separator row"]
    separator = cells(lines[header_index + 1])
    if len(separator) != len(expected) or any(
        not SEPARATOR.fullmatch(value) for value in separator
    ):
        findings.append(f"{path}: malformed separator row")
    rows: list[dict[str, str]] = []
    interrupted = False
    for number, line in enumerate(lines[header_index + 2 :], header_index + 3):
        if interrupted:
            if cells(line):
                findings.append(
                    f"{path}:{number}: pipe-delimited row appears after table interruption"
                )
            continue
        if not line.strip():
            interrupted = True
            continue
        values = cells(line)
        if not values:
            interrupted = True
            continue
        if len(values) != len(expected):
            findings.append(
                f"{path}:{number}: expected {len(expected)} cells, got {len(values)}"
            )
            continue
        rows.append(dict(zip(expected, values)))
    if not rows:
        findings.append(f"{path}: table has no data rows")
    return rows, findings


def valid_date(value: str) -> bool:
    try:
        return dt.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def validate_evidence(path: Path) -> tuple[int, int, list[str]]:
    rows, findings = read_table(path, EVIDENCE_COLUMNS)
    seen: set[str] = set()
    sample_count = 0
    live_count = 0
    for index, row in enumerate(rows, 1):
        prefix = f"{path}:row {index}"
        for key, value in row.items():
            if not value:
                findings.append(f"{prefix}: empty {key}")
        evidence_id = row["Evidence ID"]
        if not EVIDENCE_ID.fullmatch(evidence_id):
            findings.append(f"{prefix}: invalid Evidence ID")
        if evidence_id in seen:
            findings.append(f"{prefix}: duplicate Evidence ID")
        seen.add(evidence_id)
        id_marks_sample = evidence_id.startswith("SAMPLE-")
        claim_marks_sample = SAMPLE_MARKER.search(row["Claim"]) is not None
        is_sample = id_marks_sample or claim_marks_sample
        if is_sample:
            sample_count += 1
            if not claim_marks_sample:
                findings.append(f"{prefix}: sample claim must say SAMPLE ONLY")
            if not id_marks_sample:
                findings.append(
                    f"{prefix}: SAMPLE ONLY claim must use a SAMPLE- Evidence ID"
                )
        else:
            live_count += 1
        if not REQUIREMENT_ID.fullmatch(row["Requirement"]):
            findings.append(f"{prefix}: invalid Requirement")
        command = row["Verification command"]
        if len(command) < 3 or not (command.startswith("`") and command.endswith("`")):
            findings.append(
                f"{prefix}: verification command must be backtick-wrapped"
            )
        if not COMMIT.fullmatch(row["Git commit"]):
            findings.append(f"{prefix}: invalid Git commit")
        if not valid_date(row["Date"]):
            findings.append(f"{prefix}: invalid ISO date")
        if row["Status"] not in STATUSES:
            findings.append(f"{prefix}: invalid Status")
        if row["Status"] == "Verified":
            if is_sample:
                findings.append(f"{prefix}: sample evidence cannot be Verified")
            if not VERIFIED_COMMIT.fullmatch(row["Git commit"]):
                findings.append(
                    f"{prefix}: Verified evidence requires exactly 40 lowercase "
                    "hex commit characters"
                )
            if row["Reviewer"].strip().casefold() in PLACEHOLDERS:
                findings.append(
                    f"{prefix}: Verified evidence reviewer cannot be a placeholder"
                )
            reference = row["Evidence path or link"]
            if reference.strip().casefold() in PLACEHOLDER_REFERENCES:
                findings.append(
                    f"{prefix}: Verified evidence reference cannot be a sample or placeholder"
                )
    return sample_count, live_count, findings


def nonnegative_decimal(value: str) -> bool:
    try:
        number = Decimal(value)
        return number.is_finite() and number >= 0
    except InvalidOperation:
        return False


def validate_cost(path: Path) -> tuple[int, int, list[str]]:
    rows, findings = read_table(path, COST_COLUMNS)
    sample_count = 0
    live_count = 0
    for index, row in enumerate(rows, 1):
        prefix = f"{path}:row {index}"
        for key, value in row.items():
            if not value:
                findings.append(f"{prefix}: empty {key}")
        if not valid_date(row["Date"]):
            findings.append(f"{prefix}: invalid ISO date")
        for key in ("Estimated retail cost", "Credit consumed", "Actual charge"):
            if not nonnegative_decimal(row[key]):
                findings.append(f"{prefix}: {key} must be a nonnegative number")
        try:
            days = int(row["Trial days remaining"])
            if days < 0 or str(days) != row["Trial days remaining"]:
                raise ValueError
        except ValueError:
            findings.append(
                f"{prefix}: Trial days remaining must be a nonnegative integer"
            )
        if "SAMPLE ONLY" in row["Deployment profile"]:
            sample_count += 1
            if "SAMPLE ONLY" not in row["Notes"]:
                findings.append(f"{prefix}: sample notes must say SAMPLE ONLY")
        else:
            live_count += 1
    return sample_count, live_count, findings


def repository_name(root: Path) -> str:
    profile = root / "policy/repository-profile.json"
    try:
        value = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read repository profile: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("repository profile JSON root must be an object")
    name = value.get("repository")
    if not isinstance(name, str) or name not in {"skinwalker", "azure-soc-range"}:
        raise ValueError("repository profile has unsupported identity")
    return name


def validate(root: Path) -> tuple[int, int, int, int, list[str]]:
    evidence_sample, evidence_live, findings = validate_evidence(
        root / "docs/evidence-ledger.md"
    )
    cost_sample = 0
    cost_live = 0
    try:
        name = repository_name(root)
    except ValueError as exc:
        findings.append(str(exc))
        return (
            evidence_sample,
            evidence_live,
            cost_sample,
            cost_live,
            sorted(set(findings)),
        )
    if name == "azure-soc-range":
        cost_sample, cost_live, cost_findings = validate_cost(
            root / "docs/cost-ledger.md"
        )
        findings.extend(cost_findings)
    return evidence_sample, evidence_live, cost_sample, cost_live, sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args(argv)
    evidence_sample, evidence_live, cost_sample, cost_live, findings = validate(
        args.root.resolve()
    )
    if findings:
        print(f"FAIL: {len(findings)} finding(s)")
        for finding in findings:
            print(f"FINDING: {finding}")
        return 1
    print(
        "OK: "
        f"evidence sample rows={evidence_sample}, evidence live rows={evidence_live}, "
        f"cost sample rows={cost_sample}, cost live rows={cost_live}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
