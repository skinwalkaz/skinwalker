#!/usr/bin/env python3
"""Validate the WP-0.1 issue/label/board manifest against the build plan.

Task WP-0.1 -- Create issue boards and requirement labels.

Gate: "Every task links to one requirement and one acceptance test."

The gate is enforced literally: every work-package task in the plan's Work
Breakdown Structure must be assigned to exactly one requirement (program-level
WP-0 tasks are owned by a program requirement such as PROG-00), and the
``excluded_from_requirements`` list must remain empty. Any nonempty list is a
gate failure; exclusions can never substitute for requirement ownership.

This tool uses only the Python standard library. The manifest is written in a
small, deliberately restricted YAML subset; unsupported YAML syntax fails
visibly instead of being silently ignored.

Checks performed
----------------
1. Structural: manifest parses under the restricted subset; required keys and
   fields exist; no duplicate keys; every referenced label is defined; and
   the common issue labels ``type:requirement`` and ``evidence:required``
   exist.
2. Truth: ``source_of_truth`` resolves to the plan file supplied on the
   command line; it must be relative and is resolved from the manifest's own
   location.
3. Requirement coverage: every ``#### SKW-*`` / ``#### AZ-*`` heading in the
   build plan has exactly one issue, and the manifest has no extras. Program
   requirements (``PROG-*``) are title-checked against the ``### WP-0`` WBS
   heading. Duplicate requirement ids are rejected.
4. Task coverage: every work-package row is assigned to exactly one
   requirement; invented task ids and duplicate assignments are rejected;
   ``excluded_from_requirements`` must be empty.
5. Acceptance links: every mapped task has a non-empty ``acceptance`` and a
   ``plan_verification`` string matching the plan's Verification cell
   (modulo whitespace, case, and trailing sentence period).
6. Boards: exactly one board per supported area, and every board has a
   Deferred (``status:deferred``) column; every column targets a defined
   label.

Exit codes: 0 = pass, 1 = findings, 2 = usage/input error.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path, PurePath

WBS_HEADING = "## Work Breakdown Structure"
REQ_HEADING_RE = re.compile(r"^#### ((?:SKW|AZ)-\d{2})\s+(.+)$", re.MULTILINE)
PROGRAM_HEADING_RE = re.compile(
    r"^### WP-0\s+(.+?)\s+estimated \d+ hours\s*$", re.MULTILINE
)
TASK_RE = re.compile(r"^WP-\d+\.\d+$")
ID_PREFIX_AREA = {"SKW": "skinwalker", "AZ": "azure", "PROG": "program"}
DEFERRED_LABEL = "status:deferred"
REQUIRED_ISSUE_LABELS = {"type:requirement", "evidence:required"}
MAX_PARSE_DEPTH = 64


class ManifestError(Exception):
    """Raised for manifest or plan input that cannot be parsed."""


# --------------------------------------------------------------------------
# Restricted YAML-subset parser
# --------------------------------------------------------------------------

def _tokenize(text: str) -> list[tuple[int, str]]:
    tokens: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        tokens.append((indent, stripped))
    return tokens


def parse_manifest_text(text: str):
    """Parse the restricted YAML subset into plain dicts/lists/strings."""
    tokens = _tokenize(text)
    if not tokens:
        raise ManifestError("manifest is empty")
    if tokens[0][0] != 0:
        raise ManifestError("first non-comment line must not be indented")
    value, idx = _parse_block(tokens, 0, tokens[0][0], depth=0)
    if idx != len(tokens):
        raise ManifestError(
            f"unexpected content at line ending {tokens[idx][1]!r} "
            "(unsupported indentation or YAML feature)"
        )
    return value


def _split_key_value(content: str, where: str) -> tuple[str, str]:
    sep = content.find(": ")
    if sep != -1:
        return content[:sep], content[sep + 2:]
    if content.endswith(":"):
        return content[:-1], ""
    raise ManifestError(f"cannot find 'key:' in {content!r} ({where})")


def _parse_block(tokens, idx, indent, depth):
    if depth > MAX_PARSE_DEPTH:
        raise ManifestError(
            f"nesting exceeds supported depth of {MAX_PARSE_DEPTH}"
        )
    if tokens[idx][1].startswith("- "):
        return _parse_sequence(tokens, idx, indent, depth)
    return _parse_mapping(tokens, idx, indent, depth)


def _parse_sequence(tokens, idx, indent, depth):
    items: list = []
    while idx < len(tokens) and tokens[idx][0] == indent and tokens[idx][1].startswith("- "):
        content = tokens[idx][1][2:].strip()
        idx += 1
        sub: list[tuple[int, str]] = []
        while idx < len(tokens) and tokens[idx][0] > indent:
            sub.append(tokens[idx])
            idx += 1
        if not content:
            if not sub:
                raise ManifestError("empty sequence item")
            item, used = _parse_block(sub, 0, sub[0][0], depth + 1)
            if used != len(sub):
                raise ManifestError("unexpected content inside sequence item")
            items.append(item)
            continue
        if ": " not in content and not content.endswith(":"):
            if sub:
                raise ManifestError(
                    f"scalar sequence item {content!r} cannot have nested keys"
                )
            items.append(_scalar(content))
            continue
        key, value = _split_key_value(content, "sequence item")
        if value == "":
            raise ManifestError(
                f"sequence item key {key!r} has no inline value"
            )
        # Parse the item as a general mapping block: the dash-line content is
        # re-based at indent+2 and continues with the collected sub tokens.
        virtual = [(indent + 2, content)] + sub
        item, used = _parse_block(virtual, 0, indent + 2, depth + 2)
        if used != len(virtual):
            raise ManifestError(
                f"unexpected content under sequence item key {key!r}"
            )
        items.append(item)
    if not items:
        raise ManifestError("empty sequence at current indent")
    return items, idx


def _parse_mapping(tokens, idx, indent, depth):
    result: dict = {}
    while idx < len(tokens) and tokens[idx][0] == indent and not tokens[idx][1].startswith("- "):
        key, value = _split_key_value(tokens[idx][1], "mapping")
        if key in result:
            raise ManifestError(f"duplicate key {key!r} in mapping")
        idx += 1
        if value != "":
            if idx < len(tokens) and tokens[idx][0] > indent:
                raise ManifestError(
                    f"inline value for key {key!r} cannot also have nested lines"
                )
            result[key] = _scalar(value)
        else:
            if idx >= len(tokens) or tokens[idx][0] <= indent:
                raise ManifestError(f"key {key!r} has no value block")
            child, idx = _parse_block(tokens, idx, tokens[idx][0], depth + 1)
            result[key] = child
    return result, idx


def _scalar(value: str):
    value = value.strip()
    if value.startswith("[") or value.startswith("{"):
        if value == "[]":
            return []  # the manifest's only supported empty container
        raise ManifestError(f"unsupported YAML scalar syntax: {value!r}")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


# --------------------------------------------------------------------------
# Plan reconciliation
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join(text.split()).lower().rstrip(".")


def _task_major(task_id: str) -> int:
    """Return the package number of 'WP-<major>.<minor>' (WP-0.1 -> 0)."""
    return int(task_id[3:].split(".")[0])


def parse_plan(path: Path) -> tuple[dict, dict, str]:
    """Return ({requirement_id: title}, {task_id: verification}, program_title).

    Requirement headings are ``#### SKW-*`` / ``#### AZ-*`` entries anywhere in
    the plan. Task rows come from the ``## Work Breakdown Structure`` tables.
    The program heading is the ``### WP-0 `` entry of the WBS.
    """
    text = path.read_text(encoding="utf-8")

    requirements: dict[str, str] = {}
    for match in REQ_HEADING_RE.finditer(text):
        req_id, title = match.group(1), match.group(2).strip()
        if req_id in requirements:
            raise ManifestError(f"plan defines heading {req_id} more than once")
        requirements[req_id] = title

    program_heading = PROGRAM_HEADING_RE.search(text)
    if program_heading is None:
        raise ManifestError("plan WBS has no '### WP-0' program heading")

    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == WBS_HEADING), None)
    if start is None:
        raise ManifestError(f"plan has no {WBS_HEADING!r} section")
    end = next(
        (i for i in range(start + 1, len(lines))
         if lines[i].startswith("## ")),
        len(lines),
    )
    tasks: dict[str, str] = {}
    for line in lines[start + 1: end]:
        row = line.strip()
        if not row.startswith("| WP-"):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) < 5:
            raise ManifestError(f"plan WBS row has too few columns: {row!r}")
        task_id = cells[0].split()[0]
        if not TASK_RE.match(task_id):
            raise ManifestError(f"malformed task id {task_id!r} in plan WBS")
        if task_id in tasks:
            raise ManifestError(f"plan WBS defines {task_id} more than once")
        tasks[task_id] = cells[-1]
    return requirements, tasks, program_heading.group(1).strip()


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate(manifest_path: Path, plan_path: Path) -> tuple[list[str], dict]:
    """Return (findings, summary). An empty findings list means the gate passes."""
    findings: list[str] = []
    summary: dict = {}
    add = findings.append

    try:
        manifest = parse_manifest_text(manifest_path.read_text(encoding="utf-8"))
        plan_reqs, plan_tasks, program_title = parse_plan(plan_path)
    except (ManifestError, RecursionError, UnicodeDecodeError, OSError, TypeError) as exc:
        return [f"parse error: {exc}"], {}

    # The manifest root must be a mapping. A sequence root (top-level list items)
    # parses cleanly but cannot carry named top-level keys; guard it here so the
    # exit-1 parse-error contract holds instead of an uncaught TypeError below.
    if not isinstance(manifest, dict):
        return [
            "parse error: manifest root must be a mapping of top-level keys, "
            f"got {type(manifest).__name__}"
        ], {}

    # --- top-level keys -------------------------------------------------------
    for key in ("version", "source_of_truth", "labels", "boards",
                "excluded_from_requirements", "requirements"):
        if key not in manifest:
            add(f"missing required top-level key {key!r}")
    if findings:
        return findings, summary

    # --- source of truth ------------------------------------------------------
    truth = manifest["source_of_truth"]
    if not isinstance(truth, str):
        add(f"parse error: source_of_truth must be a string, got "
            f"{type(truth).__name__}")
        return findings, summary
    if not truth or "\x00" in truth:
        add("parse error: source_of_truth must be a non-empty path without "
            "control characters such as NUL")
        return findings, summary
    try:
        truth_is_absolute = PurePath(truth).is_absolute()
    except (ValueError, OSError) as exc:
        add(f"parse error: source_of_truth {truth!r} is not a usable path: {exc}")
        return findings, summary
    if truth_is_absolute:
        add(f"parse error: source_of_truth {truth!r} must be a relative path, "
            "resolved from the manifest's own location")
        return findings, summary
    plan_resolved = plan_path.resolve()
    manifest_root = manifest_path.resolve().parent
    # Bind truth to the manifest's own location only: never to the launch CWD
    # (a worktree checkout therefore rebinds to the worktree's docs/ directory).
    try:
        candidates = [
            (manifest_root.parent / truth).resolve(),
            (manifest_root / truth).resolve(),
        ]
    except (ValueError, OSError) as exc:
        add(f"parse error: source_of_truth {truth!r} is not a usable path: {exc}")
        return findings, summary
    if plan_resolved not in candidates:
        add(f"source_of_truth {truth!r} does not resolve to the supplied plan "
            f"{plan_resolved}")

    # --- labels ----------------------------------------------------------------
    labels = manifest["labels"]
    if not isinstance(labels, list) or not labels:
        add("'labels' must be a non-empty list")
        labels = []
    label_names: list[str] = []
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name")
            if not name:
                add(f"label entry is missing 'name': {label!r}")
                continue
            label_names.append(name)
            if not label.get("color"):
                add(f"label {name!r} is missing a color")
            if not label.get("description"):
                add(f"label {name!r} is missing a description")
        else:
            add(f"label entry must be a mapping: {label!r}")
    for name, count in Counter(label_names).items():
        if count > 1:
            add(f"label {name!r} is defined {count} times")
    defined_labels = set(label_names)
    for required_label in sorted(REQUIRED_ISSUE_LABELS - defined_labels):
        add(f"missing mandatory issue label {required_label!r}")
    summary["label_count"] = len(label_names)

    # --- requirements ------------------------------------------------------------
    requirements = manifest["requirements"]
    if not isinstance(requirements, list) or not requirements:
        add("'requirements' must be a non-empty list")
        requirements = []

    assignments: dict[str, str] = {}
    related_references: list[tuple[str, str]] = []
    manifest_ids: list[str] = []
    deliverable_issues: list[str] = []
    id_counts: Counter = Counter()
    for req in requirements:
        if not isinstance(req, dict):
            add(f"requirement entry must be a mapping: {req!r}")
            continue
        req_id = req.get("id")
        manifest_ids.append(str(req_id))
        id_counts[str(req_id)] += 1
    for raw_id, count in id_counts.items():
        if count > 1:
            add(f"requirement id {raw_id!r} is defined {count} times "
                f"(exactly one is required)")
    seen_ids: dict[str, bool] = {}

    for req in requirements:
        if not isinstance(req, dict):
            continue
        req_id = req.get("id")
        prefix = str(req_id).split("-")[0]
        if id_counts[str(req_id)] > 1 and seen_ids.get(str(req_id)):
            continue  # duplicates are already reported; check first occurrence only
        seen_ids[str(req_id)] = True
        in_plan = str(req_id) in plan_reqs
        area = req.get("area")
        title = req.get("title")

        if prefix not in ID_PREFIX_AREA and not in_plan:
            add(f"requirement id {req_id!r} has no matching '#### ' heading in "
                f"the plan and no supported prefix")
            continue
        elif prefix not in ID_PREFIX_AREA:
            add(f"requirement {req_id} matches plan heading but uses unsupported "
                f"prefix")
        elif in_plan:
            # SKW/AZ requirement anchored to a '#### ' plan heading.
            if area != ID_PREFIX_AREA[prefix]:
                add(f"requirement {req_id} area {area!r} does not match prefix "
                    f"{prefix!r}")
            if title != plan_reqs[str(req_id)]:
                add(f"requirement {req_id} title {title!r} does not match plan "
                    f"heading {plan_reqs[str(req_id)]!r}")
            expected_anchor = (str(req_id) + "-" + plan_reqs[str(req_id)]) \
                .lower().replace(" ", "-")
            if req.get("plan_anchor") != expected_anchor:
                add(f"requirement {req_id} plan_anchor {req.get('plan_anchor')!r} "
                    f"does not match plan heading (expected {expected_anchor!r})")
        elif prefix == "PROG":
            # Program requirement anchored to the '### WP-0' WBS heading.
            if area != "program":
                add(f"program requirement {req_id} area {area!r} must be 'program'")
            if title != program_title:
                add(f"program requirement {req_id} title {title!r} does not match "
                    f"the plan WBS program heading {program_title!r}")
        else:
            add(f"requirement id {req_id!r} has no matching '#### ' heading in "
                f"the plan")

        priority_label = f"priority:{req.get('priority')}"
        if priority_label not in defined_labels:
            add(f"requirement {req_id} references undefined priority label "
                f"{priority_label!r}")
        area_label = f"area:{area}"
        if area_label not in defined_labels:
            add(f"requirement {req_id} references undefined area label {area_label!r}")

        work_packages = req.get("work_packages") or []
        if not work_packages:
            add(f"requirement {req_id} has no work_packages")
        for wp in work_packages:
            if not isinstance(wp, dict):
                add(f"requirement {req_id} work-package entry must be a mapping: "
                    f"{wp!r}")
                continue
            task_id = wp.get("task")
            if not task_id or not TASK_RE.match(str(task_id)):
                add(f"requirement {req_id} has invalid task id {task_id!r}")
                continue
            major = _task_major(str(task_id))
            if prefix == "PROG" and major != 0:
                add(f"program requirement {req_id} owns non-program task {task_id!r}")
            elif prefix in ("SKW", "AZ") and major == 0:
                add(f"requirement {req_id} cannot own program task {task_id!r}")
            if task_id in assignments:
                if assignments[task_id] == str(req_id):
                    add(f"task {task_id} is listed twice under {req_id}")
                else:
                    add(f"task {task_id} is assigned to both {assignments[task_id]} "
                        f"and {req_id}")
            else:
                assignments[task_id] = str(req_id)
            if not wp.get("acceptance"):
                add(f"task {task_id} is missing an 'acceptance' statement")
            verification = wp.get("plan_verification")
            if not verification:
                add(f"task {task_id} is missing 'plan_verification'")
            elif task_id in plan_tasks and \
                    _norm(verification) != _norm(plan_tasks[task_id]):
                add(f"task {task_id} plan_verification {verification!r} does not "
                    f"match plan verification {plan_tasks[task_id]!r}")
            # Tasks absent from the plan WBS are reported by the coverage
            # reconciliation below; the comparison itself is skipped here.
        related = req.get("related_tasks")
        if related is not None and not isinstance(related, list):
            # Type finding alone; do not iterate a scalar value (this branch
            # also keeps a non-iterable entry tripping a TypeError below).
            add(f"requirement {req_id} 'related_tasks' must be a list")
            continue
        for rel in (related or []):
            rel = str(rel)
            if not TASK_RE.match(rel):
                add(f"requirement {req_id} related task {rel!r} is not a task id")
            else:
                related_references.append((req_id, rel))
        deliverable_issues.append(f"[{req_id}] {req.get('title')} [labels: "
                                  f"type:requirement {priority_label} "
                                  f"area:{area} status:ready evidence:required]")

    summary["issue_count"] = len(manifest_ids)
    summary["deliverable_issues"] = deliverable_issues
    summary["task_requirement"] = dict(assignments)

    # --- exclusions (strictly forbidden by the literal 57-task gate) ---------------
    exclusions = manifest["excluded_from_requirements"]
    if not isinstance(exclusions, list):
        add("'excluded_from_requirements' must be an empty list")
        exclusions = []
    elif exclusions:
        add("'excluded_from_requirements' must be empty; every plan WBS task "
            "must map to exactly one requirement")
    excluded_ids: list[str] = []
    for entry in exclusions:
        if not isinstance(entry, dict):
            add(f"exclusion entry must be a mapping: {entry!r}")
            continue
        task_id = entry.get("task")
        if not task_id or not TASK_RE.match(str(task_id)):
            add(f"exclusion entry has invalid or missing 'task': {entry!r}")
            continue
        if not str(task_id).startswith("WP-0."):
            add(f"excluded task {task_id!r} is not a WP-0 program task")
        if not entry.get("reason"):
            add(f"excluded task {task_id} is missing a reason")
        excluded_ids.append(str(task_id))
    for task_id, count in Counter(excluded_ids).items():
        if count > 1:
            add(f"excluded task {task_id!r} is listed {count} times "
                f"(exactly one is required)")
    summary["excluded_count"] = len(excluded_ids)

    # --- boards: exactly one per supported area, with a Deferred column ------------
    supported_areas = set()
    for req in requirements:
        if isinstance(req, dict) and req.get("id"):
            prefix = str(req["id"]).split("-")[0]
            if prefix == "PROG":
                supported_areas.add("program")
            elif prefix in ID_PREFIX_AREA:
                supported_areas.add(ID_PREFIX_AREA[prefix])

    boards = manifest["boards"]
    if not isinstance(boards, list) or not boards:
        add("'boards' must be a non-empty list")
        boards = []
    board_names: list[str] = []
    boards_by_area: Counter = Counter()
    for board in boards:
        if not isinstance(board, dict):
            add(f"board entry must be a mapping: {board!r}")
            continue
        board_name = board.get("name")
        if not board_name:
            add(f"board entry is missing 'name': {board!r}")
            continue
        board_names.append(board_name)
        board_area = board.get("filter_area")
        if board_area not in ID_PREFIX_AREA.values():
            add(f"board {board_name!r} has unsupported filter_area {board_area!r}")
        else:
            boards_by_area[board_area] += 1
        columns = board.get("columns") or []
        seen_columns: set[str] = set()
        has_deferred = False
        if not columns:
            add(f"board {board_name!r} has no columns")
        for column in columns:
            if not isinstance(column, dict):
                add(f"board {board_name!r} has a column entry that is not a mapping")
                continue
            col_name = column.get("name")
            if not col_name:
                add(f"board {board_name!r} has a column entry without 'name'")
                continue
            if col_name in seen_columns:
                add(f"board {board_name!r} repeats column {col_name!r}")
            seen_columns.add(col_name)
            col_label = column.get("label")
            if not col_label:
                add(f"board {board_name!r} column {col_name!r} has no label")
            elif col_label not in defined_labels:
                add(f"board {board_name!r} column {col_name!r} targets undefined "
                    f"label {col_label!r}")
            if col_label == DEFERRED_LABEL:
                has_deferred = True
        if not has_deferred:
            add(f"board {board_name!r} must include a Deferred column with label "
                f"'{DEFERRED_LABEL}'")
    for name, count in Counter(board_names).items():
        if count > 1:
            add(f"board {name!r} is defined {count} times")
    summary["board_count"] = len(board_names)

    for area in sorted(supported_areas):
        count = boards_by_area.get(area, 0)
        if count != 1:
            add(f"supported area {area!r} is covered by {count} boards "
                f"(exactly one is required)")
    for area, _count in boards_by_area.items():
        if area not in supported_areas:
            add(f"board area {area!r} has no supported requirements")

    # related_tasks cross-references are evaluated after all work_packages are
    # collected so the result is independent of requirement order in the file.
    for req_id, rel in related_references:
        if rel not in plan_tasks:
            add(f"requirement {req_id} related task {rel!r} does not exist in "
                f"the plan WBS")
        elif assignments.get(rel) == str(req_id):
            add(f"requirement {req_id} related task {rel!r} duplicates its own "
                f"work_packages assignment")

    for req_id in sorted(set(plan_reqs) - set(manifest_ids)):
        add(f"plan requirement {req_id} has no issue in the manifest")
    for req_id in sorted(set(manifest_ids) - set(plan_reqs)):
        raw_prefix = str(req_id).split("-")[0]
        if raw_prefix not in ("PROG",):
            add(f"manifest requirement {req_id} has no '#### ' heading in the plan")

    # --- coverage reconciliation -------------------------------------------------------
    mapped = set(assignments)
    excluded = set(excluded_ids)
    for task_id in sorted(mapped - set(plan_tasks)):
        add(f"task {task_id} is not present in the plan WBS")
    for task_id in sorted(mapped & excluded):
        add(f"task {task_id} is both assigned to {assignments[task_id]} and "
            f"listed under excluded_from_requirements")
    for task_id in sorted(excluded - set(plan_tasks)):
        add(f"excluded task {task_id} does not exist in the plan WBS")
    for task_id in sorted(set(plan_tasks) - mapped - excluded):
        add(f"plan task {task_id} is neither assigned to a requirement nor "
            f"explicitly excluded")

    summary["plan_task_count"] = len(plan_tasks)
    summary["mapped_task_count"] = len(assignments)
    return findings, summary


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: validate_issue_manifest.py MANIFEST PLAN", file=sys.stderr)
        return 2
    manifest_path = Path(argv[0])
    plan_path = Path(argv[1])
    for path in (manifest_path, plan_path):
        if not path.is_file():
            print(f"error: file not found: {path}", file=sys.stderr)
            return 2

    findings, summary = validate(manifest_path, plan_path)
    if findings:
        print(f"FAIL: {len(findings)} finding(s)")
        for i, finding in enumerate(findings, 1):
            print(f"FINDING {i}: {finding}")
        return 1

    print(
        f"OK: {summary['issue_count']} requirement issues, "
        f"{summary['mapped_task_count']} mapped tasks, "
        f"{summary['excluded_count']} excluded tasks, "
        f"{summary['plan_task_count']} plan WBS tasks, "
        f"{summary['board_count']} boards, "
        f"{summary['label_count']} labels"
    )
    for line in summary["deliverable_issues"]:
        print(f"issue: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
