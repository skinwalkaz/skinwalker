#!/usr/bin/env python3
"""Deterministically validate the WP-0.2 repository policy bundle.

Standard library only. Exit codes: 0 pass, 1 findings, 2 usage/input error.
Real sibling access is a human-only operation and is refused unless the human
confirmation environment variable is set. Agent tests use synthetic peer trees
inside the ignored repository-local .policy-test-tmp directory.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_ROOT = REPO_ROOT / ".policy-test-tmp"
PROFILE = "policy/repository-profile.json"
MANIFEST = "policy/shared-files.sha256"

SHARED_FILES = (
    ".opencode/agents/ab-qa.md",
    ".opencode/agents/implementer.md",
    ".opencode/agents/manager.md",
    ".opencode/agents/review/correctness.md",
    ".opencode/agents/review/evidence.md",
    ".opencode/agents/review/security.md",
    ".opencode/commands/task-start.md",
    "AGENTS.md",
    "docs/agent-workflow.md",
    "docs/build-plan.md",
    "docs/decisions/0001-controlled-agent-workflow.md",
    "docs/repository-policy.md",
    "opencode.jsonc",
    "tests/test_repository_policy.py",
    "tools/validate_repository_policy.py",
)

COMMON_LOCAL_FILES = (
    ".gitignore",
    "docs/evidence/2026-11-04-wp-0.2-policy-validation.txt",
    PROFILE,
)

PLAN_SHA256 = "82431e56488a97f7c8768a7078f915778d1e4ea4dff14fed2da495a2316a9eb8"
SOURCE_COMMIT = "63b39b809413ced3a0b3b58f3a24e96394f8f11a"
SOURCE_REPOSITORY = "skinwalkaz/skinwalker"
REPORT_PATH = "docs/evidence/2026-11-04-wp-0.2-policy-validation.txt"
REPOSITORY_PROFILES = {
    "skinwalker": {
        "area": "skinwalker",
        "plan_role": "canonical",
        "local_files": (
            "docs/decisions/0003-dual-repository-policy-sync.md",
        ),
    },
    "azure-soc-range": {
        "area": "azure",
        "plan_role": "controlled-mirror",
        "local_files": (
            "docs/decisions/0002-dual-repository-policy-sync.md",
            "README.md",
        ),
    },
}
PROFILE_CONTROL_FIELDS = {
    "paid_service_default": False,
    "out_of_pocket_target_usd": 0,
    "azure_credit_target_less_than_usd": 25,
    "absolute_cost_ceiling_without_explicit_approval_usd": 40,
}
MANAGER_PREFLIGHT_SHELL = frozenset({
    "git status*",
    "git branch --show-current*",
    "git rev-parse HEAD",
    "git diff*",
    "git log -1 --oneline",
    "shasum -a 256 -c policy/shared-files.sha256",
})
GIT_LOG_PREALLOW_DENY = "git log*"
SHELL_NARROWING_DENIES = (
    "git difftool*",
    "git diff *--no-index*",
    "git *--help*",
    "git help*",
    "git *--show-signature*",
    "git *--output*",
    "git *--ext-diff*",
    "git *--textconv*",
    "git *-c *",
    "git *--config-env*",
    "git *--exec-path*",
    "git *--paginate*",
    "git *--no-pager*",
    "git *core.pager*",
    "git *pager.*",
    "git *diff.external*",
    "*;*",
    "*&&*",
    "*||*",
    "*|*",
    "*>*",
    "*<*",
    "*$(*",
    "*${*",
    "*`*",
    "*\n*",
    r"*\n*",
)
ROOT_PERMISSION_SEQUENCE = (
    ("*", "*", "ask"),
    ("read", "*", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("external_directory", "*", "deny"),
    ("shell", "git status*", "allow"),
    ("shell", "git diff*", "allow"),
    ("shell", GIT_LOG_PREALLOW_DENY, "deny"),
    ("shell", "git log -1 --oneline", "allow"),
    ("shell", "git branch --show-current*", "allow"),
    ("shell", "git rev-parse HEAD", "allow"),
    ("shell", "shasum -a 256 -c policy/shared-files.sha256", "allow"),
    *(("shell", resource, "deny") for resource in SHELL_NARROWING_DENIES),
    ("shell", "git commit*", "deny"),
    ("shell", "git push*", "deny"),
    ("shell", "git merge*", "deny"),
    ("shell", "terraform apply*", "deny"),
    ("shell", "terraform destroy*", "deny"),
    ("shell", "az *", "deny"),
    ("shell", "rm *", "deny"),
)
MANAGER_PERMISSION_SEQUENCE = (
    ("edit", "*", "deny"),
    ("shell", "*", "deny"),
    ("shell", "git status*", "allow"),
    ("shell", "git branch --show-current*", "allow"),
    ("shell", "git rev-parse HEAD", "allow"),
    ("shell", "git diff*", "allow"),
    ("shell", GIT_LOG_PREALLOW_DENY, "deny"),
    ("shell", "git log -1 --oneline", "allow"),
    ("shell", "shasum -a 256 -c policy/shared-files.sha256", "allow"),
    *(("shell", resource, "deny") for resource in SHELL_NARROWING_DENIES),
    ("subagent", "*", "deny"),
    ("subagent", "implementer", "allow"),
    ("subagent", "ab-qa", "allow"),
    ("subagent", "review/correctness", "allow"),
    ("subagent", "review/security", "allow"),
    ("subagent", "review/evidence", "allow"),
)
CORRECTIVE_PATHS = frozenset({
    ".opencode/agents/manager.md",
    "opencode.jsonc",
    "tools/validate_repository_policy.py",
    "tests/test_repository_policy.py",
    "docs/repository-policy.md",
    "policy/repository-profile.json",
    "policy/shared-files.sha256",
    "docs/decisions/0003-dual-repository-policy-sync.md",
    REPORT_PATH,
})
CORRECTIVE_IMMUTABLE_HASHES = {
    ".gitignore": "9a2d473bf7cba2e910d1f794b4a45fcc33500c0921efa7fe73319ad5e88a6d29",
    ".opencode/agents/ab-qa.md": "a40d1cd91e6e958d537195b2ba52495518d8d63cf8dc85c79bdeae6781c701cb",
    ".opencode/agents/implementer.md": "b028b1abf6ee2bdd46b19c4ffc0fc29c981868124bde63893eec133ff35c889f",
    ".opencode/agents/review/correctness.md": "06b50f0efd12d681c8e42ccaecb7d2f09c4788863bd5dc05a76806ab05f34eb3",
    ".opencode/agents/review/evidence.md": "a954e33a9a2bbdb9aaef7a21d8ecbfe75c2124ea426913bcaabc16d3e25c555c",
    ".opencode/agents/review/security.md": "4135b2c99d6aa28e30e6ea6bafe58a4eef36b3a64a1fde900e452fd681d11554",
    ".opencode/commands/task-start.md": "8347bd1ae10c8d7550b479d29fef2f6a248aa488e732526b814dda2f3b8977d2",
    "AGENTS.md": "ed08f939f992fc04684b103b2973d299ea45f465ba89efe712258cea524f76cc",
    "docs/agent-workflow.md": "997e9385222706038785c0f63f56d208431725e58731546f8386a529e854e004",
    "docs/build-plan.md": "82431e56488a97f7c8768a7078f915778d1e4ea4dff14fed2da495a2316a9eb8",
    "docs/decisions/0001-controlled-agent-workflow.md": "f0773e7e0537d79fe43847716b2bed775dcddbd014cbb0c91fc2d466e7866e4a",
}
PORCELAIN_V1_TRACKED = frozenset({
    " M", " D", " T", " A", " R", " C",
    "M ", "MM", "MD", "MT",
    "A ", "AM", "AD", "AT",
    "D ",
    "R ", "RM", "RD", "RT",
    "C ", "CM", "CD", "CT",
    "T ", "TM", "TD", "TT",
})
PORCELAIN_V1_UNMERGED = frozenset({"DD", "AU", "UD", "UA", "DU", "AA", "UU"})

SECRET_PATTERNS = (
    ("AWS access-key shape", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub token shape", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("private-key marker", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Azure connection string", re.compile(r"AccountKey=[A-Za-z0-9+/=]{20,}")),
)


class InputError(Exception):
    """Raised for CLI input that cannot safely be processed."""


class DuplicateJSONKey(ValueError):
    """Raised when policy JSON contains a duplicate object key."""


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(text: str):
    return json.loads(text, object_pairs_hook=_object_without_duplicates)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_file(root: Path, rel: str, label: str) -> tuple[Path | None, str | None]:
    relative = Path(rel)
    if relative.is_absolute() or ".." in relative.parts:
        return None, f"{label}: path must be a contained relative path: {rel}"
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                return None, f"{label}: symlink is forbidden: {rel}"
        except OSError as exc:
            return None, f"{label}: cannot inspect path: {rel}: {exc}"
    try:
        root_resolved = root.resolve(strict=True)
        resolved = (root / relative).resolve(strict=True)
    except OSError as exc:
        return None, f"{label}: missing or inaccessible file: {rel}: {exc}"
    if not _inside(resolved, root_resolved):
        return None, f"{label}: path escapes expected root: {rel}"
    if not resolved.is_file():
        return None, f"{label}: required path is not a file: {rel}"
    return resolved, None


def _safe_directory(root: Path, rel: str,
                    label: str) -> tuple[Path | None, str | None]:
    relative = Path(rel)
    if relative.is_absolute() or ".." in relative.parts:
        return None, f"{label}: directory must be a contained relative path: {rel}"
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None, f"{label}: directory symlink is forbidden: {rel}"
    try:
        root_resolved = root.resolve(strict=True)
        resolved = current.resolve(strict=True)
    except OSError as exc:
        return None, f"{label}: missing or inaccessible directory: {rel}: {exc}"
    if not _inside(resolved, root_resolved) or not resolved.is_dir():
        return None, f"{label}: directory escapes expected root or is not a directory: {rel}"
    return resolved, None


def _read_text(path: Path, findings: list[str], label: str) -> str | None:
    try:
        data = path.read_bytes()
        return data.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        findings.append(f"{label}: unreadable UTF-8 file: {exc}")
        return None


def _load_profile(root: Path) -> tuple[dict | None, list[str]]:
    path, problem = _safe_file(root, PROFILE, "profile")
    if problem:
        return None, [problem]
    try:
        assert path is not None
        profile = _load_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError,
            DuplicateJSONKey) as exc:
        return None, [f"profile: malformed JSON: {exc}"]
    if not isinstance(profile, dict):
        return None, ["profile: root must be an object"]
    return profile, []


def _profile_spec(profile: dict | None) -> dict | None:
    """Return a local-file spec only for an exact approved identity tuple."""
    if profile is None:
        return None
    repository = profile.get("repository")
    spec = REPOSITORY_PROFILES.get(repository)
    if spec is None:
        return None
    if (profile.get("area"), profile.get("plan_role")) != (
        spec["area"], spec["plan_role"]
    ):
        return None
    return spec


def _git_origin_repository(root: Path) -> str | None:
    """Return the local Git origin repository name, without network access."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=root, text=True, capture_output=True, check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value:
        return None
    name = value.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or None


def _actual_repository_name(root: Path) -> str | None:
    """Return the real checkout identity; synthetic trees are deliberately unbound."""
    if root.resolve() != REPO_ROOT.resolve():
        return None
    origin = _git_origin_repository(root)
    return origin or root.name


def required_files(root: Path) -> tuple[str, ...]:
    profile, _ = _load_profile(root)
    spec = _profile_spec(profile)
    names = set((*SHARED_FILES, *COMMON_LOCAL_FILES, MANIFEST))
    if spec is not None:
        names.update(spec["local_files"])
    return tuple(sorted(names))


def check_required_files(root: Path) -> list[str]:
    findings = []
    for rel in required_files(root):
        _, problem = _safe_file(root, rel, "required")
        if problem:
            findings.append(problem)
    return findings


def parse_manifest(root: Path) -> tuple[dict[str, str], list[str]]:
    findings: list[str] = []
    path, problem = _safe_file(root, MANIFEST, "manifest")
    if problem:
        return {}, [problem]
    assert path is not None
    text = _read_text(path, findings, MANIFEST)
    if text is None:
        return {}, findings
    entries: dict[str, str] = {}
    previous = ""
    for number, line in enumerate(text.splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            findings.append(f"manifest: malformed line {number}")
            continue
        digest, rel = parts
        if rel in entries:
            findings.append(f"manifest: duplicate path: {rel}")
        if previous and rel <= previous:
            findings.append(f"manifest: paths are not strictly sorted at: {rel}")
        if rel == MANIFEST:
            findings.append("manifest: must exclude itself")
        entries[rel] = digest
        previous = rel
    expected = set(SHARED_FILES)
    for rel in sorted(expected - set(entries)):
        findings.append(f"manifest: missing shared path: {rel}")
    for rel in sorted(set(entries) - expected):
        findings.append(f"manifest: unexpected path: {rel}")
    return entries, findings


def check_manifest(root: Path) -> list[str]:
    entries, findings = parse_manifest(root)
    for rel in sorted(set(entries) & set(SHARED_FILES)):
        path, problem = _safe_file(root, rel, "manifest")
        if problem:
            findings.append(problem)
        elif path is not None and sha256(path) != entries[rel]:
            findings.append(f"manifest: SHA-256 mismatch: {rel}")
    return findings


def check_profile(root: Path) -> list[str]:
    findings: list[str] = []
    profile, load_findings = _load_profile(root)
    if load_findings:
        return load_findings
    assert profile is not None
    repository = profile.get("repository")
    spec = REPOSITORY_PROFILES.get(repository)
    if spec is None:
        choices = ", ".join(sorted(REPOSITORY_PROFILES))
        return [f"profile: repository must be one of: {choices}"]
    actual_repository = _actual_repository_name(root)
    if actual_repository is not None and actual_repository != repository:
        findings.append(
            "profile: repository must match actual repository identity "
            f"{actual_repository!r}, got {repository!r}"
        )
    expected = {
        "schema_version": 1,
        "repository": repository,
        "area": spec["area"],
        "plan_role": spec["plan_role"],
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "plan_path": "docs/build-plan.md",
        "plan_sha256": PLAN_SHA256,
        "cloud_write_default": False,
        "task_id": "WP-0.2",
        "requirement_id": "PROG-00",
        "estimated_incremental_cost_usd": 0,
        "actual_incremental_cost_usd": 0,
        **PROFILE_CONTROL_FIELDS,
    }
    for key in sorted(expected):
        actual = profile.get(key)
        if type(actual) is not type(expected[key]) or actual != expected[key]:
            findings.append(
                f"profile: {key} must be {expected[key]!r}, got {actual!r}"
            )
    extras = sorted(set(profile) - set(expected))
    for key in extras:
        findings.append(f"profile: unexpected key: {key}")
    plan = root / "docs/build-plan.md"
    if plan.is_file() and sha256(plan) != PLAN_SHA256:
        findings.append("profile: canonical plan SHA-256 does not match plan_sha256")
    return findings


def _decode_manager_scalar(value: str, line: int) -> tuple[str | None, str | None]:
    if not value:
        return None, f"permissions: empty manager scalar at line {line}"
    if not value.startswith('"'):
        if '"' in value or "\\" in value:
            return None, f"permissions: malformed manager scalar at line {line}"
        return value, None
    if len(value) < 2 or not value.endswith('"'):
        return None, f"permissions: malformed quoted manager scalar at line {line}"
    body = value[1:-1]
    decoded: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            decoded.append(char)
            index += 1
            continue
        if index + 1 >= len(body):
            return None, f"permissions: trailing escape in manager scalar at line {line}"
        escaped = body[index + 1]
        if escaped == "n":
            decoded.append("\n")
        elif escaped in ('"', "\\"):
            decoded.append(escaped)
        else:
            return None, (
                f"permissions: unsupported manager escape \\{escaped} at line {line}"
            )
        index += 2
    return "".join(decoded), None


def parse_manager_permissions(text: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Parse the constrained manager permission list while preserving order."""
    findings: list[str] = []
    parts = text.split("---", 2)
    if len(parts) < 3:
        return [], ["permissions: manager policy has malformed frontmatter"]
    lines = parts[1].splitlines()
    indexes = [index for index, line in enumerate(lines) if line == "permissions:"]
    if len(indexes) != 1:
        return [], ["permissions: manager must define one permissions list"]
    permission_lines = lines[indexes[0] + 1:]
    raw_entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for number, line in enumerate(permission_lines, indexes[0] + 2):
        if not line.strip():
            continue
        if line.startswith("  - "):
            if current is not None:
                raw_entries.append(current)
            current = {}
            content = line[4:]
        elif line.startswith("    ") and current is not None:
            content = line[4:]
        else:
            findings.append(f"permissions: malformed manager entry line {number}")
            continue
        if ":" not in content:
            findings.append(f"permissions: malformed manager key/value line {number}")
            continue
        key, raw_value = (part.strip() for part in content.split(":", 1))
        if key in current:
            findings.append(
                f"permissions: duplicate manager key {key!r} at line {number}"
            )
            continue
        value, problem = _decode_manager_scalar(raw_value, number)
        if problem:
            findings.append(problem)
            continue
        assert value is not None
        current[key] = value
    if current is not None:
        raw_entries.append(current)
    allowed_keys = {"action", "resource", "effect"}
    entries: list[tuple[str, str, str]] = []
    for index, entry in enumerate(raw_entries, 1):
        for key in sorted(set(entry) - allowed_keys):
            findings.append(
                f"permissions: manager entry {index} has unknown key {key!r}"
            )
        for key in sorted(allowed_keys - set(entry)):
            findings.append(
                f"permissions: manager entry {index} is missing key {key!r}"
            )
        if set(entry) == allowed_keys:
            entries.append((entry["action"], entry["resource"], entry["effect"]))
    return entries, findings


def permission_effect(entries: list[tuple[str, str, str]], command: str) -> str | None:
    """Model ordered last-match shell rules for deterministic policy tests."""
    effect = None
    for action, resource, candidate_effect in entries:
        if action == "shell" and fnmatch.fnmatchcase(command, resource):
            effect = candidate_effect
    return effect


def check_permissions(root: Path) -> list[str]:
    findings: list[str] = []
    path, problem = _safe_file(root, "opencode.jsonc", "permissions")
    if problem:
        return [problem]
    try:
        assert path is not None
        config = _load_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError,
            DuplicateJSONKey) as exc:
        return [f"permissions: malformed opencode.jsonc: {exc}"]
    permissions = config.get("permissions") if isinstance(config, dict) else None
    if not isinstance(permissions, list):
        return ["permissions: permissions must be a list"]
    ordered_triples = []
    permission_keys = {"action", "resource", "effect"}
    for index, item in enumerate(permissions, 1):
        if not isinstance(item, dict):
            findings.append(f"permissions: root entry {index} must be an object")
            continue
        for key in sorted(set(item) - permission_keys):
            findings.append(f"permissions: root entry {index} has unknown key {key!r}")
        for key in sorted(permission_keys - set(item)):
            findings.append(f"permissions: root entry {index} is missing key {key!r}")
        if set(item) == permission_keys:
            triple = (item["action"], item["resource"], item["effect"])
            if not all(isinstance(value, str) for value in triple):
                findings.append(
                    f"permissions: root entry {index} values must all be strings"
                )
            elif triple[2] not in {"allow", "ask", "deny"}:
                findings.append(
                    f"permissions: root entry {index} has unknown effect {triple[2]!r}"
                )
            else:
                ordered_triples.append(triple)
    duplicate_root = [
        triple for triple, count in Counter(ordered_triples).items() if count > 1
    ]
    for triple in sorted(duplicate_root):
        findings.append(f"permissions: duplicate root permission triple: {triple!r}")
    if tuple(ordered_triples) != ROOT_PERMISSION_SEQUENCE:
        findings.append("permissions: root permission sequence does not match approved policy")
    triples = set(ordered_triples)
    required = {
        ("external_directory", "*", "deny"),
        ("shell", "git commit*", "deny"),
        ("shell", "git push*", "deny"),
        ("shell", "git merge*", "deny"),
        ("shell", "terraform apply*", "deny"),
        ("shell", "terraform destroy*", "deny"),
        ("shell", "az *", "deny"),
        ("shell", "rm *", "deny"),
    }
    for triple in sorted(required - triples):
        findings.append(f"permissions: missing deny: {triple[0]} {triple[1]}")
    for action, resource, effect in sorted(triples):
        if action == "external_directory" and effect == "allow":
            findings.append(f"permissions: forbidden external_directory allow: {resource}")
        if effect == "allow" and isinstance(resource, str) and resource.startswith("/"):
            findings.append(f"permissions: forbidden broad absolute-path allow: {resource}")

    root_shell_allows = {
        resource for action, resource, effect in triples
        if action == "shell" and effect == "allow"
    }
    for resource in sorted(MANAGER_PREFLIGHT_SHELL - root_shell_allows):
        findings.append(f"permissions: missing root preflight allow: {resource}")
    for resource in sorted(root_shell_allows - MANAGER_PREFLIGHT_SHELL):
        findings.append(f"permissions: forbidden root shell allow: {resource}")

    root_shell_denies = {
        resource for action, resource, effect in ordered_triples
        if action == "shell" and effect == "deny"
    }
    for resource in SHELL_NARROWING_DENIES:
        if resource not in root_shell_denies:
            findings.append(f"permissions: missing root narrowing deny: {resource}")
    root_allow_indexes = [
        index for index, entry in enumerate(ordered_triples)
        if entry[0] == "shell" and entry[2] == "allow"
    ]
    for resource in SHELL_NARROWING_DENIES:
        indexes = [
            index for index, entry in enumerate(ordered_triples)
            if entry == ("shell", resource, "deny")
        ]
        if indexes and root_allow_indexes and indexes[-1] <= max(root_allow_indexes):
            findings.append(
                f"permissions: root narrowing deny must follow shell allows: {resource}"
            )

    manager_path, problem = _safe_file(
        root, ".opencode/agents/manager.md", "permissions"
    )
    if problem:
        findings.append(problem)
        return findings
    try:
        assert manager_path is not None
        manager_text = manager_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        findings.append(f"permissions: unreadable manager policy: {exc}")
        return findings
    manager_triples, parser_findings = parse_manager_permissions(manager_text)
    findings.extend(parser_findings)
    for index, triple in enumerate(manager_triples, 1):
        if triple[2] not in {"allow", "ask", "deny"}:
            findings.append(
                f"permissions: manager entry {index} has unknown effect {triple[2]!r}"
            )
    duplicate_manager = [
        triple for triple, count in Counter(manager_triples).items() if count > 1
    ]
    for triple in sorted(duplicate_manager):
        findings.append(f"permissions: duplicate manager permission triple: {triple!r}")
    if tuple(manager_triples) != MANAGER_PERMISSION_SEQUENCE:
        findings.append(
            "permissions: manager permission sequence does not match approved policy"
        )
    broad_indexes = [
        index for index, entry in enumerate(manager_triples)
        if entry == ("shell", "*", "deny")
    ]
    if len(broad_indexes) != 1:
        findings.append(
            "permissions: manager requires exactly one broad shell deny"
        )
    manager_shell_allows = [
        resource for action, resource, effect in manager_triples
        if action == "shell" and effect == "allow"
    ]
    allow_counts = Counter(manager_shell_allows)
    for resource in sorted(MANAGER_PREFLIGHT_SHELL):
        if allow_counts[resource] != 1:
            findings.append(
                "permissions: manager preflight allow must occur exactly once: "
                f"{resource} (found {allow_counts[resource]})"
            )
    for resource in sorted(set(manager_shell_allows) - MANAGER_PREFLIGHT_SHELL):
        findings.append(f"permissions: forbidden manager shell allow: {resource}")
    allow_indexes = [
        index for index, entry in enumerate(manager_triples)
        if entry[0] == "shell" and entry[2] == "allow"
    ]
    if (len(broad_indexes) == 1 and allow_indexes
            and any(broad_indexes[0] >= index for index in allow_indexes)):
        findings.append(
            "permissions: manager broad shell deny must precede every preflight allow"
        )
    manager_shell_denies = [
        resource for action, resource, effect in manager_triples
        if action == "shell" and effect == "deny"
    ]
    deny_counts = Counter(manager_shell_denies)
    for resource in SHELL_NARROWING_DENIES:
        if deny_counts[resource] != 1:
            findings.append(
                "permissions: manager narrowing deny must occur exactly once: "
                f"{resource} (found {deny_counts[resource]})"
            )
        indexes = [
            index for index, entry in enumerate(manager_triples)
            if entry == ("shell", resource, "deny")
        ]
        if indexes and allow_indexes and indexes[0] <= max(allow_indexes):
            findings.append(
                f"permissions: manager narrowing deny must follow shell allows: {resource}"
            )
    manager_lower = manager_text.lower()
    for phrase in (
        "run each permitted preflight command individually",
        "do not combine commands",
        "arbitrary shell",
    ):
        if phrase not in manager_lower:
            findings.append(f"permissions: manager missing command-isolation rule: {phrase}")
    return findings


def _topic(root: Path, rel: str,
           groups: tuple[tuple[str, ...], ...]) -> list[str]:
    findings: list[str] = []
    path, problem = _safe_file(root, rel, "policy")
    if problem:
        return [problem]
    try:
        assert path is not None
        text = path.read_text(encoding="utf-8").lower()
    except (OSError, UnicodeDecodeError) as exc:
        return [f"policy: cannot read {path.name}: {exc}"]
    for alternatives in groups:
        if not any(term in text for term in alternatives):
            findings.append(
                f"policy: {path.name} missing topic: {' or '.join(alternatives)}"
            )
    return findings


def check_policy_topics(root: Path) -> list[str]:
    findings = _topic(root, "docs/repository-policy.md", (
        ("branch",), ("review",), ("secret",), ("fixture",), ("evidence",),
        ("generated",), ("license",), ("verified",), ("cloud write",),
        ("cost",), ("sibling repository",), ("human operator",),
    ))
    findings.extend(_topic(root, "AGENTS.md", (
        ("must not access",), ("sibling",), ("human operator",),
        ("commit",), ("push",), ("merge",), ("destructive deletion",),
        ("terraform apply",), ("terraform destroy",), ("azure cli",),
        ("only a human", "only the human"), ("verified",),
    )))
    return findings


def check_gitignore(root: Path) -> list[str]:
    path, problem = _safe_file(root, ".gitignore", "gitignore")
    if problem:
        return [problem]
    try:
        assert path is not None
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [f"gitignore: unreadable: {exc}"]
    findings: list[str] = []
    if "/.policy-test-tmp/" not in lines:
        findings.append("gitignore: missing narrow /.policy-test-tmp/ rule")
    broad = {"*", "docs/", "policy/", "tests/", "tools/", ".opencode/"}
    for value in sorted(broad & set(lines)):
        findings.append(f"gitignore: forbidden broad rule: {value}")
    return findings


def check_format(root: Path) -> list[str]:
    findings: list[str] = []
    for rel in required_files(root):
        path, problem = _safe_file(root, rel, "format")
        if problem:
            findings.append(problem)
            continue
        try:
            assert path is not None
            data = path.read_bytes()
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"format: {rel}: not readable UTF-8: {exc}")
            continue
        if b"\r" in data:
            findings.append(f"format: {rel}: CR/CRLF line ending")
        if data and not data.endswith(b"\n"):
            findings.append(f"format: {rel}: missing final LF")
        for number, line in enumerate(text.splitlines(), 1):
            if line.rstrip(" \t") != line:
                findings.append(f"format: {rel}:{number}: trailing whitespace")
    return findings


def check_secrets(root: Path) -> list[str]:
    findings: list[str] = []
    for rel in required_files(root):
        path, problem = _safe_file(root, rel, "secrets")
        if problem:
            findings.append(problem)
            continue
        assert path is not None
        text = _read_text(path, findings, f"secrets: {rel}")
        if text is None:
            continue
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"secrets: {rel}: obvious {name}")
    return findings


def changed_paths(root: Path) -> tuple[list[str], list[str]]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=root, text=False, capture_output=True, check=False,
        )
    except OSError as exc:
        return [], [f"changes: cannot execute git status: {exc}"]
    if result.returncode != 0:
        return [], [f"changes: git status failed with exit {result.returncode}"]
    data = result.stdout
    if not isinstance(data, bytes):
        return [], ["changes: git status returned non-bytes output"]
    if data and not data.endswith(b"\0"):
        return [], ["changes: malformed NUL status output: missing final NUL"]
    records = data.split(b"\0")
    if records and records[-1] == b"":
        records.pop()
    paths: list[str] = []
    index = 0
    while index < len(records):
        record = records[index]
        if len(record) < 4 or record[2:3] != b" ":
            return [], [
                f"changes: malformed NUL status record at index {index + 1}"
            ]
        try:
            status_code = record[:2].decode("ascii")
        except UnicodeDecodeError:
            return [], [
                f"changes: non-ASCII status code at record {index + 1}"
            ]
        if status_code == "!!":
            return [], [
                "changes: ignored status '!!' is invalid without ignored-file mode"
            ]
        if (status_code != "??"
                and status_code not in PORCELAIN_V1_TRACKED
                and status_code not in PORCELAIN_V1_UNMERGED):
            return [], [
                f"changes: invalid porcelain-v1 XY status {status_code!r} "
                f"at record {index + 1}"
            ]
        destination = record[3:]
        if not destination:
            return [], [
                f"changes: empty path in status record {index + 1}"
            ]
        paths.append(os.fsdecode(destination))
        if "R" in status_code or "C" in status_code:
            index += 1
            if index >= len(records) or not records[index]:
                return [], [
                    f"changes: rename/copy record {index} is missing its source path"
                ]
            paths.append(os.fsdecode(records[index]))
        index += 1
    return sorted(set(paths)), []


def check_immutable_index(
    root: Path,
    immutable_hashes: dict[str, str] | None = None,
) -> list[str]:
    """Validate index mode/blob only for immutable paths with staged changes."""
    approved = CORRECTIVE_IMMUTABLE_HASHES if immutable_hashes is None else immutable_hashes
    findings: list[str] = []
    for rel, expected_digest in sorted(approved.items()):
        try:
            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet", "--", rel],
                cwd=root, text=False, capture_output=True, check=False,
            )
        except OSError as exc:
            findings.append(f"index: cannot inspect staged state for {rel}: {exc}")
            continue
        if staged.returncode == 0:
            continue
        if staged.returncode != 1:
            findings.append(
                f"index: staged-state command failed for {rel} with exit "
                f"{staged.returncode}"
            )
            continue
        try:
            listing = subprocess.run(
                ["git", "ls-files", "--stage", "-z", "--", rel],
                cwd=root, text=False, capture_output=True, check=False,
            )
        except OSError as exc:
            findings.append(f"index: cannot inspect index entry for {rel}: {exc}")
            continue
        if listing.returncode != 0:
            findings.append(
                f"index: ls-files failed for {rel} with exit {listing.returncode}"
            )
            continue
        data = listing.stdout
        if not isinstance(data, bytes):
            findings.append(f"index: ls-files returned non-bytes output for {rel}")
            continue
        if not data:
            findings.append(f"index: staged deletion or missing stage-0 entry: {rel}")
            continue
        if not data.endswith(b"\0"):
            findings.append(f"index: malformed ls-files output for {rel}: missing NUL")
            continue
        records = data[:-1].split(b"\0")
        parsed: list[tuple[str, str, int, bytes]] = []
        malformed = False
        for record in records:
            metadata, separator, path_bytes = record.partition(b"\t")
            fields = metadata.split(b" ")
            if separator != b"\t" or len(fields) != 3 or not path_bytes:
                malformed = True
                break
            mode_bytes, oid_bytes, stage_bytes = fields
            try:
                mode = mode_bytes.decode("ascii")
                oid = oid_bytes.decode("ascii")
                stage = int(stage_bytes.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                malformed = True
                break
            if (not re.fullmatch(r"[0-9]{6}", mode)
                    or not re.fullmatch(r"[0-9a-f]{40,64}", oid)
                    or stage not in {0, 1, 2, 3}):
                malformed = True
                break
            parsed.append((mode, oid, stage, path_bytes))
        if malformed:
            findings.append(f"index: malformed ls-files stage record for {rel}")
            continue
        expected_path = os.fsencode(rel)
        if any(entry[3] != expected_path for entry in parsed):
            findings.append(f"index: ls-files returned unexpected path for {rel}")
            continue
        if len(parsed) != 1 or parsed[0][2] != 0:
            findings.append(f"index: conflict or multiple stages for {rel}")
            continue
        mode, _oid, _stage, _path = parsed[0]
        if mode != "100644":
            findings.append(
                f"index: immutable path mode must be 100644, got {mode}: {rel}"
            )
            continue
        try:
            blob = subprocess.run(
                ["git", "cat-file", "blob", f":{rel}"],
                cwd=root, text=False, capture_output=True, check=False,
            )
        except OSError as exc:
            findings.append(f"index: cannot hash staged blob for {rel}: {exc}")
            continue
        if blob.returncode != 0:
            findings.append(
                f"index: cat-file failed for {rel} with exit {blob.returncode}"
            )
            continue
        if not isinstance(blob.stdout, bytes):
            findings.append(f"index: cat-file returned non-bytes output for {rel}")
            continue
        if hashlib.sha256(blob.stdout).hexdigest() != expected_digest:
            findings.append(f"index: staged blob SHA-256 mismatch: {rel}")
    return findings


def check_corrective_scope(root: Path, paths: list[str],
                           check_index: bool = True) -> list[str]:
    findings: list[str] = []
    for rel, expected in sorted(CORRECTIVE_IMMUTABLE_HASHES.items()):
        path, problem = _safe_file(root, rel, "changes")
        if problem:
            findings.append(problem)
        elif path is not None and sha256(path) != expected:
            findings.append(f"changes: immutable corrective-scope hash mismatch: {rel}")
    for rel in paths:
        if rel.startswith(".github/workflows/"):
            findings.append(f"changes: WP-0.2 forbids workflow change: {rel}")
        elif rel in CORRECTIVE_PATHS:
            continue
        elif rel in CORRECTIVE_IMMUTABLE_HASHES:
            continue
        else:
            findings.append(f"changes: path outside corrective nine-path scope: {rel}")
    if check_index:
        findings.extend(check_immutable_index(root))
    return findings


def check_changes(root: Path) -> list[str]:
    paths, findings = changed_paths(root)
    profile, _ = _load_profile(root)
    if profile and profile.get("repository") == "skinwalker":
        findings.extend(check_corrective_scope(root, paths))
        return findings
    allowed_paths = frozenset(required_files(root))
    for rel in paths:
        if rel.startswith(".github/workflows/"):
            findings.append(f"changes: WP-0.2 forbids workflow change: {rel}")
        elif rel not in allowed_paths:
            findings.append(f"changes: path outside WP-0.2 allowlist: {rel}")
    return findings


def check_peer(root: Path, peer_root: Path) -> list[str]:
    peer = peer_root.resolve()
    synthetic = SYNTHETIC_ROOT.resolve()
    if not _inside(peer, synthetic) and os.environ.get(
        "REPOSITORY_POLICY_HUMAN_PEER_VALIDATION"
    ) != "1":
        raise InputError(
            "external peer root refused by agent-local policy; real peer mode is human-only"
        )
    if not peer.is_dir():
        raise InputError(f"peer root is not a directory: {peer_root}")
    findings: list[str] = []
    for rel in SHARED_FILES:
        local, local_problem = _safe_file(root, rel, "peer local")
        other, other_problem = _safe_file(peer, rel, "peer")
        if local_problem:
            findings.append(local_problem)
        if other_problem:
            findings.append(other_problem)
        if (local is not None and other is not None
                and sha256(local) != sha256(other)):
            findings.append(f"peer: shared-file drift: {rel}")
    return findings


def validate_tree(root: Path, include_changes: bool = False) -> list[str]:
    findings = check_required_files(root)
    if findings:
        return sorted(set(findings))
    for check in (
        check_manifest, check_profile, check_permissions,
        check_policy_topics, check_gitignore, check_format,
    ):
        findings.extend(check(root))
    if include_changes:
        findings.extend(check_changes(root))
    return sorted(set(findings))


def validate_local(root: Path) -> list[str]:
    return validate_tree(root, include_changes=True)


def render(mode: str, findings: list[str]) -> str:
    lines = [f"MODE: {mode}"]
    if findings:
        lines.append(f"FAIL: {len(findings)} finding(s)")
        lines.extend(f"FINDING {index}: {value}"
                     for index, value in enumerate(sorted(findings), 1))
    else:
        lines.append("PASS: 0 findings")
    return "\n".join(lines) + "\n"


def evidence_report(validation_output: str, root: Path) -> str:
    profile, _ = _load_profile(root)
    repository = profile.get("repository", "unknown") if profile else "unknown"
    return (
        "WP-0.2 / PROG-00 repository policy validation\n"
        "Date: 2026-11-09\n"
        "Status: Collected\n"
        f"Repository: {repository}\n"
        f"Source repository: {SOURCE_REPOSITORY}\n"
        f"Source commit: {SOURCE_COMMIT}\n"
        "Canonical hotfix baseline HEAD (operator-supplied): "
        "139e05801ab54a08bf1dcc4246532fcb1672188e\n"
        "Canonical prior WP-0.2 evidence remains preserved at that committed "
        "HEAD; this regenerated Collected template covers only the compatibility "
        "hotfix.\n"
        "Candidate state: uncommitted post-commit compatibility hotfix "
        "working tree\n"
        "Production command: python3 tools/validate_repository_policy.py "
        f"--report {REPORT_PATH}\n"
        "Scope: agent-local repository files only\n"
        f"Working directory: {root}\n"
        "Capture convention: canonical assembled transcripts merge stdout and "
        "stderr in emission order unless a command explicitly records separate "
        "streams.\n"
        "Execution attribution: Python and test commands are OpenCode harness "
        "local verification coordinated by the manager under harness tool "
        "permissions, not manager-frontmatter shell execution.\n"
        "External services contacted: none\n"
        "Peer repositories accessed: none\n"
        "Cloud resources changed: none\n"
        "Estimated incremental cost USD: 0\n"
        "Actual incremental cost USD: 0\n\n"
        "Operator-supplied Azure compatibility context\n"
        "---------------------------------------------\n"
        "The operator reported, without providing Azure repository access, that "
        "the canonical suite fails as "
        "test_real_skinwalker_profile_has_exact_cost_controls in the approved "
        "azure-soc-range repository because the then-current test hard-codes "
        "repository == skinwalker. The operator also reported that Azure "
        "repository-specific required/allowed files omit README.md, which is an "
        "approved Azure-local WP-0.2 file. This artifact records that context "
        "only; no Azure or sibling repository was accessed, listed, read, "
        "hashed, or validated.\n\n"
        "Hotfix scope\n"
        "------------\n"
        "The profile model now carries an explicit local_files tuple per exact "
        "approved identity. Skinwalker requires only its local ADR-0003. The "
        "Azure profile requires its local ADR-0002 plus README.md. "
        "required_files() adds every approved local file, and the non-Skinwalker "
        "changed-path allowlist derives from required_files(). README.md remains "
        "outside SHARED_FILES and the shared manifest. The real-repository "
        "profile test is identity-generic and validates area, plan_role, and "
        "exact cost control types and values for either approved identity. "
        "The validator also binds the real repository profile to the local Git "
        "origin repository name (or the checkout directory name when no origin "
        "exists), so a canonical tree cannot switch to the Azure profile to "
        "bypass corrective-scope and immutable-hash enforcement. Synthetic "
        "trees remain unbound and cover both identities without Azure access.\n\n"
        "Agent-local validator result\n"
        "----------------------------\n"
        + validation_output
        + "\nComplete agent-local command transcripts\n"
        "----------------------------------------\n"
        "NOT RECORDED BY THIS COMMAND. Append actual commands, working "
        "directories, exit codes, stdout/stderr, warnings, skips, and failures.\n\n"
        "Authoritative pre-edit inventory\n"
        "--------------------------------\n"
        "NOT RECORDED BY THIS COMMAND. Append the operator-supplied authoritative "
        "path/size/SHA-256 inventory and failed-attempt record.\n\n"
        "Final candidate inventory and comparison\n"
        "----------------------------------------\n"
        "NOT RECORDED BY THIS COMMAND. Append actual final path/size/SHA-256 "
        "output and comparison with the authoritative pre-edit inventory.\n\n"
        "Failures, warnings, skips, and exclusions\n"
        "----------------------------------------\n"
        "NOT RECORDED BY THIS COMMAND. Append actual outcomes, including zero "
        "counts only when supported by command transcripts.\n\n"
        "Hotfix path inventory\n"
        "---------------------\n"
        "NOT RECORDED BY THIS COMMAND. Append actual pre-edit and final "
        "path/size/SHA-256 rows for the five operator-authorized hotfix paths.\n\n"
        "Immutable corrective-scope hash provenance and limitation\n"
        "---------------------------------------------------------\n"
        "The eleven immutable paths remain .gitignore plus ten disallowed "
        "canonical shared files. Their approved SHA-256 values are unchanged. "
        "Historical transcript limitations disclosed by the prior WP-0.2 "
        "candidate still apply; this hotfix does not invent older shells.\n\n"
        "Residual permission and report limitations\n"
        "------------------------------------------\n"
        "Six operator-mandated preflight shell allows remain in place (three "
        "Git prefix wildcards, two exact Git commands, and one shasum command). "
        "Ordered narrowing denies are defense in depth, not proof that every "
        "Git/config/helper execution path is impossible. Atomic report "
        "replacement narrows but cannot portably eliminate every final "
        "filesystem race window.\n\n"
        "Future human-operator actions (NOT RUN; NOT EVIDENCE)\n"
        "------------------------------------------------\n"
        "1. Assemble actual hotfix command transcripts and inventories.\n"
        "2. Review the canonical and Azure copies in the peer repository.\n"
        "3. Decide whether evidence is Verified.\n"
        "No peer-repository result or cloud state is claimed here.\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-format", action="store_true")
    modes.add_argument("--check-secrets", action="store_true")
    parser.add_argument("--report", metavar="PATH")
    parser.add_argument("--peer-root", metavar="PATH")
    return parser


def validated_report_path(root: Path, requested: str) -> Path:
    if requested != REPORT_PATH:
        raise InputError(f"report path must be exactly {REPORT_PATH}")
    path, problem = _safe_file(root, REPORT_PATH, "report")
    if problem:
        raise InputError(problem)
    assert path is not None
    return path


def _regular_identity_nofollow(path: Path) -> os.stat_result:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise InputError(f"report target cannot be opened safely: {exc}") from exc
    try:
        identity = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISREG(identity.st_mode):
        raise InputError("report destination must be a regular file")
    return identity


def write_report_atomic(root: Path, requested: str, content: str) -> None:
    target = validated_report_path(root, requested)
    parent, problem = _safe_directory(root, str(Path(REPORT_PATH).parent), "report")
    if problem:
        raise InputError(problem)
    assert parent is not None
    initial_target = _regular_identity_nofollow(target)
    initial_parent = os.stat(parent, follow_symlinks=False)
    if not stat.S_ISDIR(initial_parent.st_mode):
        raise InputError("report destination must be a regular file in a regular directory")
    fd = -1
    temporary: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(prefix=".wp02-report-", dir=parent)
        temporary = Path(temporary_name)
        temporary_stat = os.fstat(fd)
        if not stat.S_ISREG(temporary_stat.st_mode):
            raise InputError("report temporary path is not a regular file")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            fd = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        current_target = _regular_identity_nofollow(target)
        current_parent = os.stat(parent, follow_symlinks=False)
        if ((current_target.st_dev, current_target.st_ino) !=
                (initial_target.st_dev, initial_target.st_ino)):
            raise InputError("report destination changed before atomic replacement")
        if ((current_parent.st_dev, current_parent.st_ino) !=
                (initial_parent.st_dev, initial_parent.st_ino)):
            raise InputError("report parent changed before atomic replacement")
        if target.is_symlink() or not stat.S_ISREG(current_target.st_mode):
            raise InputError("report destination became non-regular or a symlink")
        os.replace(temporary, target)
        temporary = None
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.report:
            validated_report_path(REPO_ROOT, args.report)
        if args.check_format:
            mode = "format"
            findings = check_format(REPO_ROOT)
        elif args.check_secrets:
            mode = "secrets"
            findings = check_secrets(REPO_ROOT)
        else:
            mode = "local"
            findings = validate_local(REPO_ROOT)
        if args.peer_root:
            mode += "+peer"
            findings.extend(check_peer(REPO_ROOT, Path(args.peer_root)))
        output = render(mode, sorted(set(findings)))
        if args.report:
            write_report_atomic(
                REPO_ROOT, args.report, evidence_report(output, REPO_ROOT)
            )
        sys.stdout.write(output)
        return 1 if findings else 0
    except InputError as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
