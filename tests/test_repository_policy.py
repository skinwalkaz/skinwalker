"""WP-0.2 repository-policy validator tests (standard-library unittest)."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.validate_repository_policy import (  # noqa: E402
    MANIFEST,
    MANAGER_PREFLIGHT_SHELL,
    PROFILE_CONTROL_FIELDS,
    PORCELAIN_V1_TRACKED,
    PORCELAIN_V1_UNMERGED,
    REPORT_PATH,
    REPOSITORY_PROFILES,
    SHELL_NARROWING_DENIES,
    SHARED_FILES,
    SYNTHETIC_ROOT,
    check_corrective_scope,
    check_format,
    check_immutable_index,
    check_manifest,
    check_peer,
    check_permissions,
    check_policy_topics,
    check_profile,
    check_required_files,
    check_secrets,
    changed_paths,
    evidence_report,
    main,
    parse_manager_permissions,
    permission_effect,
    render,
    required_files,
    validate_tree,
    validate_local,
    validated_report_path,
    write_report_atomic,
    InputError,
)


def copy_files(destination: Path, names=None) -> None:
    if names is None:
        names = required_files(REPO_ROOT)
    for rel in names:
        source = REPO_ROOT / rel
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def configure_profile(root: Path, repository: str) -> None:
    """Convert a synthetic tree to one of the two approved profile tuples."""
    profile_path = root / "policy/repository-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    current_spec = REPOSITORY_PROFILES.get(profile.get("repository"))
    target_spec = REPOSITORY_PROFILES[repository]
    target_adr = root / target_spec["local_adr"]
    if not target_adr.is_file():
        if current_spec is None:
            raise AssertionError("synthetic source profile has no approved identity")
        source_adr = root / current_spec["local_adr"]
        target_adr.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_adr, target_adr)
    profile.update({
        "repository": repository,
        "area": target_spec["area"],
        "plan_role": target_spec["plan_role"],
    })
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")


class TreeCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SYNTHETIC_ROOT.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SYNTHETIC_ROOT)
        self.root = Path(self.temp.name)
        copy_files(self.root)

    def tearDown(self):
        self.temp.cleanup()


class LocalPolicyTests(TreeCase):
    def test_real_repository_passes_local_policy(self):
        self.assertEqual(validate_local(REPO_ROOT), [])

    def test_required_files_present(self):
        self.assertEqual(check_required_files(self.root), [])

    def test_real_skinwalker_profile_has_exact_cost_controls(self):
        profile = json.loads(
            (REPO_ROOT / "policy/repository-profile.json").read_text(encoding="utf-8")
        )
        self.assertEqual(profile["repository"], "skinwalker")
        for key, expected in PROFILE_CONTROL_FIELDS.items():
            self.assertIs(type(profile[key]), type(expected), key)
            self.assertEqual(profile[key], expected, key)

    def test_format_passes(self):
        self.assertEqual(check_format(self.root), [])

    def test_missing_file_is_finding(self):
        (self.root / "docs/repository-policy.md").unlink()
        self.assertTrue(any(
            "required: missing or inaccessible file: docs/repository-policy.md"
            in value for value in check_required_files(self.root)
        ))

    def test_default_cli_passes(self):
        self.assertEqual(main([]), 0)

    def test_secret_mode_passes_real_explicit_files(self):
        self.assertEqual(main(["--check-secrets"]), 0)

    def test_report_outside_repository_is_input_error(self):
        self.assertEqual(main(["--report", "../outside-policy-report.txt"]), 2)

    def test_report_cannot_overwrite_source_or_manifest(self):
        for rel in ("tools/validate_repository_policy.py", MANIFEST):
            with self.subTest(rel=rel):
                before = hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest()
                self.assertEqual(main(["--report", rel]), 2)
                after = hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest()
                self.assertEqual(before, after)

    def test_obvious_secret_shape_is_detected_in_synthetic_tree(self):
        path = self.root / "docs/repository-policy.md"
        synthetic_shape = "A" + "KIA" + ("0" * 16)
        path.write_text(path.read_text(encoding="utf-8") + synthetic_shape + "\n",
                        encoding="utf-8")
        self.assertTrue(any("AWS access-key shape" in value
                            for value in check_secrets(self.root)))

    def test_synthetic_azure_profile_passes_without_shared_file_edits(self):
        configure_profile(self.root, "azure-soc-range")
        self.assertEqual(validate_tree(self.root), [])
        profile = json.loads(
            (self.root / "policy/repository-profile.json").read_text(encoding="utf-8")
        )
        for key, expected in PROFILE_CONTROL_FIELDS.items():
            self.assertIs(type(profile[key]), type(expected), key)
            self.assertEqual(profile[key], expected, key)
        required = required_files(self.root)
        self.assertIn("docs/decisions/0002-dual-repository-policy-sync.md", required)
        self.assertNotIn("docs/decisions/0003-dual-repository-policy-sync.md", required)

    def test_evidence_template_reserves_unrecorded_sections(self):
        report = evidence_report("MODE: local\nPASS: 0 findings\n", REPO_ROOT)
        self.assertIn("Complete agent-local command transcripts", report)
        self.assertIn("Authoritative pre-edit inventory", report)
        self.assertIn("Final candidate inventory and comparison", report)
        self.assertIn("Failures, warnings, skips, and exclusions", report)
        self.assertIn("NOT RECORDED BY THIS COMMAND", report)
        self.assertIn("NOT RUN; NOT EVIDENCE", report)

    def test_manifest_exactly_matches_all_shared_files(self):
        rows = []
        for line in (REPO_ROOT / MANIFEST).read_text(encoding="utf-8").splitlines():
            digest, path = line.split("  ", 1)
            rows.append((path, digest))
        self.assertEqual([path for path, _ in rows], sorted(SHARED_FILES))
        self.assertEqual(len(rows), len(SHARED_FILES))
        for path, digest in rows:
            actual = hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()
            self.assertEqual(digest, actual, path)

    def test_required_policy_symlink_is_rejected_without_reading_target(self):
        target = self.root / "harmless-local-target.txt"
        target.write_text("harmless synthetic target\n", encoding="utf-8")
        policy = self.root / "docs/repository-policy.md"
        policy.unlink()
        policy.symlink_to(target)
        findings = check_required_files(self.root)
        self.assertTrue(any("symlink is forbidden" in value for value in findings),
                        findings)

    def test_report_symlink_is_rejected_without_reading_target(self):
        target = self.root / "harmless-report-target.txt"
        target.write_text("harmless synthetic target\n", encoding="utf-8")
        report = self.root / "docs/evidence/2026-11-04-wp-0.2-policy-validation.txt"
        report.unlink()
        report.symlink_to(target)
        with self.assertRaises(InputError):
            validated_report_path(self.root, REPORT_PATH)

    def test_atomic_report_write_replaces_only_approved_regular_target(self):
        report = self.root / REPORT_PATH
        write_report_atomic(self.root, REPORT_PATH, "synthetic report\n")
        self.assertEqual(report.read_text(encoding="utf-8"), "synthetic report\n")
        self.assertEqual(list(report.parent.glob(".wp02-report-*")), [])

    def test_atomic_report_failure_preserves_target_and_cleans_temp(self):
        report = self.root / REPORT_PATH
        before = report.read_bytes()
        with patch("tools.validate_repository_policy.os.replace",
                   side_effect=OSError("synthetic replace failure")):
            with self.assertRaises(OSError):
                write_report_atomic(self.root, REPORT_PATH, "replacement\n")
        self.assertEqual(report.read_bytes(), before)
        self.assertEqual(list(report.parent.glob(".wp02-report-*")), [])


class PermissionBoundaryTests(TreeCase):
    def _config(self) -> tuple[Path, dict]:
        path = self.root / "opencode.jsonc"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def _drop(self, resource: str) -> list[str]:
        path, config = self._config()
        config["permissions"] = [
            item for item in config["permissions"]
            if item.get("resource") != resource
        ]
        path.write_text(json.dumps(config), encoding="utf-8")
        return check_permissions(self.root)

    def test_external_directory_deny_is_required(self):
        findings = self._drop("*")
        self.assertTrue(any("external_directory" in value for value in findings))

    def test_manager_read_only_preflight_permissions_are_exact(self):
        self.assertEqual(check_permissions(self.root), [])
        text = (self.root / ".opencode/agents/manager.md").read_text(encoding="utf-8")
        for resource in MANAGER_PREFLIGHT_SHELL:
            self.assertIn(f'resource: "{resource}"\n    effect: allow', text)
        self.assertIn('resource: "*"\n    effect: deny', text)
        self.assertIn("Run each permitted preflight command individually", text)
        self.assertIn("Do not combine commands", text)

    def test_manager_arbitrary_or_dangerous_shell_allow_is_forbidden(self):
        path = self.root / ".opencode/agents/manager.md"
        text = path.read_text(encoding="utf-8")
        insertion = (
            '  - action: shell\n'
            '    resource: "git commit*"\n'
            '    effect: allow\n'
        )
        path.write_text(text.replace("  - action: subagent\n", insertion
                                     + "  - action: subagent\n", 1), encoding="utf-8")
        self.assertTrue(any("forbidden manager shell allow: git commit*" in value
                            for value in check_permissions(self.root)))

    def test_manager_broad_shell_deny_is_required(self):
        path = self.root / ".opencode/agents/manager.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            '  - action: shell\n    resource: "*"\n    effect: deny\n', "", 1
        )
        path.write_text(text, encoding="utf-8")
        self.assertTrue(any("manager is missing broad shell deny" in value
                            or "exactly one broad shell deny" in value
                            for value in check_permissions(self.root)))

    def test_manager_parser_accepts_key_reordering_and_rejects_dangerous_allow(self):
        path = self.root / ".opencode/agents/manager.md"
        text = path.read_text(encoding="utf-8")
        entry = (
            '  - effect: allow\n'
            '    resource: "git commit*"\n'
            '    action: shell\n'
        )
        path.write_text(text.replace("  - action: subagent\n", entry
                                     + "  - action: subagent\n", 1), encoding="utf-8")
        findings = check_permissions(self.root)
        self.assertTrue(any("forbidden manager shell allow: git commit*" in value
                            for value in findings), findings)

    def test_manager_parser_rejects_unknown_field(self):
        path = self.root / ".opencode/agents/manager.md"
        text = path.read_text(encoding="utf-8").replace(
            '    effect: deny\n', '    effect: deny\n    note: forbidden\n', 1
        )
        path.write_text(text, encoding="utf-8")
        self.assertTrue(any("unknown key 'note'" in value
                            for value in check_permissions(self.root)))

    def test_manager_parser_rejects_duplicate_key(self):
        path = self.root / ".opencode/agents/manager.md"
        text = path.read_text(encoding="utf-8").replace(
            '    effect: deny\n', '    effect: deny\n    effect: deny\n', 1
        )
        path.write_text(text, encoding="utf-8")
        self.assertTrue(any("duplicate manager key 'effect'" in value
                            for value in check_permissions(self.root)))

    def test_manager_parser_rejects_duplicate_approved_allow(self):
        path = self.root / ".opencode/agents/manager.md"
        text = path.read_text(encoding="utf-8")
        block = (
            '  - action: shell\n'
            '    resource: "git status*"\n'
            '    effect: allow\n'
        )
        path.write_text(text.replace(block, block + block, 1), encoding="utf-8")
        self.assertTrue(any("git status* (found 2)" in value
                            for value in check_permissions(self.root)))

    def test_manager_parser_rejects_missing_field(self):
        path = self.root / ".opencode/agents/manager.md"
        text = path.read_text(encoding="utf-8").replace(
            '  - action: shell\n'
            '    resource: "git status*"\n'
            '    effect: allow\n',
            '  - action: shell\n'
            '    resource: "git status*"\n',
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assertTrue(any("is missing key 'effect'" in value
                            for value in check_permissions(self.root)))

    def test_manager_shell_deny_moved_after_allows_fails(self):
        path = self.root / ".opencode/agents/manager.md"
        text = path.read_text(encoding="utf-8")
        broad = '  - action: shell\n    resource: "*"\n    effect: deny\n'
        anchor = (
            '  - action: shell\n'
            '    resource: "shasum -a 256 -c policy/shared-files.sha256"\n'
            '    effect: allow\n'
        )
        text = text.replace(broad, "", 1).replace(anchor, anchor + broad, 1)
        path.write_text(text, encoding="utf-8")
        self.assertTrue(any("must precede every preflight allow" in value
                            for value in check_permissions(self.root)))

    def test_root_unauthorized_shell_allow_is_rejected(self):
        path, config = self._config()
        config["permissions"].append(
            {"action": "shell", "resource": "python3 *", "effect": "allow"}
        )
        path.write_text(json.dumps(config), encoding="utf-8")
        self.assertTrue(any("forbidden root shell allow: python3 *" in value
                            for value in check_permissions(self.root)))

    def test_manager_wildcard_allow_ask_and_trailing_shell_ask_are_rejected(self):
        mutations = (
            ('*', '*', 'allow'),
            ('*', '*', 'ask'),
            ('shell', 'git status*', 'ask'),
        )
        for action, resource, effect in mutations:
            with self.subTest(action=action, resource=resource, effect=effect):
                copy_files(self.root, (".opencode/agents/manager.md",))
                path = self.root / ".opencode/agents/manager.md"
                text = path.read_text(encoding="utf-8")
                entry = (
                    f'  - action: {action}\n'
                    f'    resource: "{resource}"\n'
                    f'    effect: {effect}\n'
                )
                path.write_text(text.replace("---\n\nYou are", entry
                                             + "---\n\nYou are", 1), encoding="utf-8")
                findings = check_permissions(self.root)
                self.assertTrue(any("manager permission sequence" in value
                                    for value in findings), findings)

    def test_root_wildcard_allow_ask_and_trailing_shell_ask_are_rejected(self):
        mutations = (
            {"action": "*", "resource": "*", "effect": "allow"},
            {"action": "*", "resource": "*", "effect": "ask"},
            {"action": "shell", "resource": "git status*", "effect": "ask"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                copy_files(self.root, ("opencode.jsonc",))
                path, config = self._config()
                config["permissions"].append(mutation)
                path.write_text(json.dumps(config), encoding="utf-8")
                findings = check_permissions(self.root)
                self.assertTrue(any("root permission sequence" in value
                                    for value in findings), findings)

    def test_manager_and_root_unknown_effects_are_rejected(self):
        manager_path = self.root / ".opencode/agents/manager.md"
        manager_text = manager_path.read_text(encoding="utf-8").replace(
            '    effect: allow\n', '    effect: permit\n', 1
        )
        manager_path.write_text(manager_text, encoding="utf-8")
        self.assertTrue(any("unknown effect 'permit'" in value
                            for value in check_permissions(self.root)))
        copy_files(self.root, (".opencode/agents/manager.md",))
        root_path, config = self._config()
        config["permissions"][0]["effect"] = "permit"
        root_path.write_text(json.dumps(config), encoding="utf-8")
        self.assertTrue(any("unknown effect 'permit'" in value
                            for value in check_permissions(self.root)))

    def test_root_duplicate_permission_and_malformed_object_are_rejected(self):
        path, config = self._config()
        config["permissions"].append(dict(config["permissions"][0]))
        path.write_text(json.dumps(config), encoding="utf-8")
        findings = check_permissions(self.root)
        self.assertTrue(any("duplicate root permission triple" in value
                            for value in findings), findings)
        copy_files(self.root, ("opencode.jsonc",))
        path, config = self._config()
        config["permissions"].append(
            {"action": "shell", "resource": "git status*", "unknown": "allow"}
        )
        path.write_text(json.dumps(config), encoding="utf-8")
        findings = check_permissions(self.root)
        self.assertTrue(any("unknown key 'unknown'" in value for value in findings),
                        findings)

    def test_root_duplicate_json_key_is_rejected(self):
        path = self.root / "opencode.jsonc"
        text = path.read_text(encoding="utf-8").replace(
            '  "default_agent": "manager",',
            '  "default_agent": "manager",\n  "default_agent": "manager",',
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assertTrue(any("duplicate JSON key: default_agent" in value
                            for value in check_permissions(self.root)))

    def test_narrowing_denies_follow_allows_and_reject_dangerous_forms(self):
        manager_text = (self.root / ".opencode/agents/manager.md").read_text(
            encoding="utf-8"
        )
        manager_entries, findings = parse_manager_permissions(manager_text)
        self.assertEqual(findings, [])
        config = json.loads((self.root / "opencode.jsonc").read_text(encoding="utf-8"))
        root_entries = [
            (item["action"], item["resource"], item["effect"])
            for item in config["permissions"]
        ]
        for resource in SHELL_NARROWING_DENIES:
            self.assertIn(("shell", resource, "deny"), manager_entries)
            self.assertIn(("shell", resource, "deny"), root_entries)
        clean = (
            "git status --short", "git branch --show-current", "git rev-parse HEAD",
            "git diff --stat", "git log -1 --oneline",
            "shasum -a 256 -c policy/shared-files.sha256",
        )
        dangerous = (
            "git difftool --tool=external", "git diff x --no-index y",
            "git status --help", "git help status", "git log -h",
            "git log --help", "git log --show-signature",
            "git log --format=%GG", "git log -2", "git log -1 --oneline --all",
            "git status --output=written", "git diff --ext-diff",
            "git log --textconv", "git status -c core.pager=cat",
            "git status --config-env=x=y", "git status --exec-path=/x",
            "git status --paginate", "git status --no-pager",
            "git status core.pager=cat", "git diff diff.external=tool",
            "git status > file", "git status < file", "git status; rm file",
            "git status && rm file", "git status || rm file", "git status | cat",
            "git status $(command)", "git status ${value}", "git status `command`",
            "git status\\nrm file", "git status --short\nrm file",
        )
        for entries in (manager_entries, root_entries):
            for command in clean:
                self.assertEqual(permission_effect(entries, command), "allow", command)
            for command in dangerous:
                self.assertEqual(permission_effect(entries, command), "deny", command)

    def test_external_directory_allow_is_forbidden(self):
        path, config = self._config()
        config["permissions"].append(
            {"action": "external_directory", "resource": "*", "effect": "allow"}
        )
        path.write_text(json.dumps(config), encoding="utf-8")
        self.assertTrue(any("forbidden external_directory allow" in value
                            for value in check_permissions(self.root)))

    def test_git_boundaries_cannot_be_weakened(self):
        for resource in ("git commit*", "git push*", "git merge*"):
            with self.subTest(resource=resource):
                self.assertTrue(any(resource in value for value in self._drop(resource)))
                copy_files(self.root, ("opencode.jsonc",))

    def test_cloud_boundaries_cannot_be_weakened(self):
        for resource in ("terraform apply*", "terraform destroy*", "az *"):
            with self.subTest(resource=resource):
                self.assertTrue(any(resource in value for value in self._drop(resource)))
                copy_files(self.root, ("opencode.jsonc",))

    def test_destructive_delete_boundary_cannot_be_weakened(self):
        self.assertTrue(any("rm *" in value for value in self._drop("rm *")))

    def test_human_verified_boundary_cannot_be_weakened(self):
        path = self.root / "AGENTS.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("Only the human operator", "An automated agent")
        text = text.replace("Only a human", "An automated agent")
        path.write_text(text, encoding="utf-8")
        findings = check_policy_topics(self.root)
        self.assertTrue(any("only a human" in value for value in findings), findings)


class MutationTests(TreeCase):
    def test_changed_shared_byte_fails_manifest(self):
        path = self.root / "docs/repository-policy.md"
        path.write_text(path.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        self.assertIn(
            "manifest: SHA-256 mismatch: docs/repository-policy.md",
            check_manifest(self.root),
        )

    def test_malformed_profile_is_visible(self):
        (self.root / "policy/repository-profile.json").write_text("{", encoding="utf-8")
        self.assertTrue(check_profile(self.root)[0].startswith("profile: malformed JSON:"))

    def test_wrong_profile_plan_hash_is_finding(self):
        path = self.root / "policy/repository-profile.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        profile["plan_sha256"] = "0" * 64
        path.write_text(json.dumps(profile), encoding="utf-8")
        self.assertTrue(any("plan_sha256" in value for value in check_profile(self.root)))

    def test_removing_each_cost_control_field_fails_for_both_profiles(self):
        path = self.root / "policy/repository-profile.json"
        for repository in REPOSITORY_PROFILES:
            configure_profile(self.root, repository)
            original = json.loads(path.read_text(encoding="utf-8"))
            for key in PROFILE_CONTROL_FIELDS:
                with self.subTest(repository=repository, key=key):
                    profile = dict(original)
                    del profile[key]
                    path.write_text(json.dumps(profile), encoding="utf-8")
                    self.assertTrue(any(f"profile: {key} must be" in value
                                        for value in check_profile(self.root)))
                    path.write_text(json.dumps(original), encoding="utf-8")

    def test_changing_each_exact_cost_control_value_fails_for_both_profiles(self):
        path = self.root / "policy/repository-profile.json"
        changed = {
            "paid_service_default": True,
            "out_of_pocket_target_usd": 1,
            "azure_credit_target_less_than_usd": 24,
            "absolute_cost_ceiling_without_explicit_approval_usd": 41,
        }
        for repository in REPOSITORY_PROFILES:
            configure_profile(self.root, repository)
            original = json.loads(path.read_text(encoding="utf-8"))
            for key, value in changed.items():
                with self.subTest(repository=repository, key=key):
                    profile = dict(original)
                    profile[key] = value
                    path.write_text(json.dumps(profile), encoding="utf-8")
                    self.assertTrue(any(f"profile: {key} must be" in finding
                                        for finding in check_profile(self.root)))
                    path.write_text(json.dumps(original), encoding="utf-8")

    def test_unknown_profile_key_fails(self):
        path = self.root / "policy/repository-profile.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        profile["unknown_cost_control"] = 0
        path.write_text(json.dumps(profile), encoding="utf-8")
        self.assertIn("profile: unexpected key: unknown_cost_control",
                      check_profile(self.root))

    def test_duplicate_profile_cost_key_is_rejected(self):
        path = self.root / "policy/repository-profile.json"
        text = path.read_text(encoding="utf-8").replace(
            '  "out_of_pocket_target_usd": 0,',
            '  "out_of_pocket_target_usd": 0,\n'
            '  "out_of_pocket_target_usd": 0,',
            1,
        )
        path.write_text(text, encoding="utf-8")
        self.assertTrue(any("duplicate JSON key: out_of_pocket_target_usd" in value
                            for value in check_profile(self.root)))

    def test_source_commit_mutation_fails(self):
        path = self.root / "policy/repository-profile.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        profile["source_commit"] = "0" * 40
        path.write_text(json.dumps(profile), encoding="utf-8")
        self.assertTrue(any("profile: source_commit must be" in value
                            for value in check_profile(self.root)))

    def test_immutable_disallowed_shared_mutation_fails_even_with_manifest_update(self):
        path = self.root / "AGENTS.md"
        path.write_text(path.read_text(encoding="utf-8") + "immutable drift\n",
                        encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = self.root / MANIFEST
        text = manifest.read_text(encoding="utf-8")
        text = text.replace(next(line for line in text.splitlines()
                                 if line.endswith("  AGENTS.md")),
                            f"{digest}  AGENTS.md")
        manifest.write_text(text, encoding="utf-8")
        findings = check_corrective_scope(
            self.root, ["AGENTS.md", MANIFEST], check_index=False
        )
        self.assertIn("changes: immutable corrective-scope hash mismatch: AGENTS.md",
                      findings)

    def test_unexpected_changed_path_fails_corrective_scope(self):
        unexpected = self.root / "unexpected.txt"
        unexpected.write_text("synthetic\n", encoding="utf-8")
        self.assertIn("changes: path outside corrective nine-path scope: unexpected.txt",
                      check_corrective_scope(
                          self.root, ["unexpected.txt"], check_index=False
                      ))

    def test_unknown_repository_is_finding(self):
        path = self.root / "policy/repository-profile.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        profile["repository"] = "unknown-repository"
        path.write_text(json.dumps(profile), encoding="utf-8")
        self.assertTrue(any("repository must be one of" in value
                            for value in check_profile(self.root)))

    def test_wrong_repository_area_role_combinations_fail(self):
        path = self.root / "policy/repository-profile.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        mutations = (
            ("skinwalker", "azure", "canonical"),
            ("skinwalker", "skinwalker", "controlled-mirror"),
            ("azure-soc-range", "skinwalker", "controlled-mirror"),
            ("azure-soc-range", "azure", "canonical"),
        )
        for repository, area, role in mutations:
            with self.subTest(repository=repository, area=area, role=role):
                profile = dict(original)
                profile.update(repository=repository, area=area, plan_role=role)
                path.write_text(json.dumps(profile), encoding="utf-8")
                findings = check_profile(self.root)
                self.assertTrue(any("area" in value or "plan_role" in value
                                    for value in findings), findings)

    def test_changed_plan_byte_is_finding(self):
        path = self.root / "docs/build-plan.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertTrue(any("canonical plan SHA-256" in value
                            for value in check_profile(self.root)))

    def test_trailing_whitespace_is_finding(self):
        path = self.root / "docs/repository-policy.md"
        path.write_text(path.read_text(encoding="utf-8") + "bad  \n", encoding="utf-8")
        self.assertTrue(any("trailing whitespace" in value
                            for value in check_format(self.root)))

    def test_findings_are_stably_sorted(self):
        (self.root / "docs/repository-policy.md").unlink()
        (self.root / "policy/repository-profile.json").write_text("{", encoding="utf-8")
        first = sorted(check_required_files(self.root) + check_profile(self.root))
        second = sorted(check_required_files(self.root) + check_profile(self.root))
        self.assertEqual(first, second)
        output = render("test", list(reversed(first)))
        lines = [line.split(": ", 1)[1] for line in output.splitlines()
                 if line.startswith("FINDING ")]
        self.assertEqual(lines, sorted(lines))


class SyntheticPeerDriftTests(TreeCase):
    def setUp(self):
        super().setUp()
        self.peer = self.root / "peer"
        copy_files(self.peer, SHARED_FILES)

    def test_matching_synthetic_peer_passes(self):
        self.assertEqual(check_peer(REPO_ROOT, self.peer), [])

    def test_synthetic_peer_drift_is_finding(self):
        path = self.peer / "AGENTS.md"
        path.write_text(path.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
        self.assertEqual(check_peer(REPO_ROOT, self.peer), [
            "peer: shared-file drift: AGENTS.md"
        ])

    def test_synthetic_peer_missing_file_is_finding(self):
        (self.peer / "opencode.jsonc").unlink()
        self.assertTrue(any("missing or inaccessible file: opencode.jsonc" in value
                            for value in check_peer(REPO_ROOT, self.peer)))

    def test_synthetic_peer_symlink_escape_is_rejected_without_reading_target(self):
        target = self.root / "harmless-peer-target.txt"
        target.write_text("harmless synthetic target\n", encoding="utf-8")
        peer_file = self.peer / "AGENTS.md"
        peer_file.unlink()
        peer_file.symlink_to(target)
        findings = check_peer(REPO_ROOT, self.peer)
        self.assertTrue(any("peer: symlink is forbidden: AGENTS.md" in value
                            for value in findings), findings)

    def test_non_synthetic_peer_is_refused_for_agent(self):
        candidate = REPO_ROOT / "operator-only-peer"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REPOSITORY_POLICY_HUMAN_PEER_VALIDATION", None)
            with self.assertRaises(InputError):
                check_peer(REPO_ROOT, candidate)


class ImmutableIndexTests(unittest.TestCase):
    PATH = "synthetic-immutable.txt"

    @staticmethod
    def _result(returncode=0, stdout=b"", stderr=b""):
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def _check(self, expected: bytes, responses):
        digest = hashlib.sha256(expected).hexdigest()
        with patch("tools.validate_repository_policy.subprocess.run",
                   side_effect=responses) as mocked:
            findings = check_immutable_index(REPO_ROOT, {self.PATH: digest})
        return findings, mocked

    def _stage_record(self, mode="100644", stage=0):
        oid = "0" * 40
        return f"{mode} {oid} {stage}\t{self.PATH}\0".encode()

    def test_no_staged_change_ignores_baseline_index_blob(self):
        findings, mocked = self._check(
            b"approved-candidate", [self._result(returncode=0)]
        )
        self.assertEqual(findings, [])
        self.assertEqual(mocked.call_count, 1)

    def test_matching_staged_untracked_bytes_and_mode_pass(self):
        approved = b"approved staged bytes\n"
        findings, _ = self._check(approved, [
            self._result(returncode=1),
            self._result(stdout=self._stage_record()),
            self._result(stdout=approved),
        ])
        self.assertEqual(findings, [])

    def test_staged_bytes_differ_while_working_bytes_are_approved(self):
        findings, _ = self._check(b"working bytes match", [
            self._result(returncode=1),
            self._result(stdout=self._stage_record()),
            self._result(stdout=b"different staged bytes"),
        ])
        self.assertIn(
            f"index: staged blob SHA-256 mismatch: {self.PATH}", findings
        )

    def test_staged_executable_or_type_replacement_mode_is_rejected(self):
        for mode in ("100755", "120000", "160000"):
            with self.subTest(mode=mode):
                findings, mocked = self._check(b"approved", [
                    self._result(returncode=1),
                    self._result(stdout=self._stage_record(mode=mode)),
                ])
                self.assertTrue(any("mode must be 100644" in value
                                    for value in findings))
                self.assertEqual(mocked.call_count, 2)

    def test_staged_deletion_is_rejected(self):
        findings, _ = self._check(b"approved", [
            self._result(returncode=1), self._result(stdout=b""),
        ])
        self.assertTrue(any("staged deletion" in value for value in findings))

    def test_conflict_multiple_stages_are_rejected(self):
        records = self._stage_record(stage=1) + self._stage_record(stage=2)
        findings, _ = self._check(b"approved", [
            self._result(returncode=1), self._result(stdout=records),
        ])
        self.assertTrue(any("conflict or multiple stages" in value
                            for value in findings))

    def test_malformed_stage_output_is_rejected(self):
        cases = (b"100644 bad 0\tpath", b"not-a-stage-record\0")
        for output in cases:
            with self.subTest(output=output):
                findings, _ = self._check(b"approved", [
                    self._result(returncode=1), self._result(stdout=output),
                ])
                self.assertTrue(any("malformed" in value for value in findings),
                                findings)

    def test_git_plumbing_command_failures_are_visible(self):
        findings, _ = self._check(
            b"approved", [self._result(returncode=2)]
        )
        self.assertTrue(any("staged-state command failed" in value
                            for value in findings))
        findings, _ = self._check(b"approved", [
            self._result(returncode=1), self._result(returncode=3),
        ])
        self.assertTrue(any("ls-files failed" in value for value in findings))


class ChangedPathParsingTests(unittest.TestCase):
    def _run(self, stdout: bytes, returncode: int = 0):
        completed = subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=b"synthetic"
        )
        with patch("tools.validate_repository_policy.subprocess.run",
                   return_value=completed) as mocked:
            result = changed_paths(REPO_ROOT)
        self.assertEqual(
            mocked.call_args.args[0],
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        )
        return result

    def test_ordinary_spaces_literal_arrow_and_quoted_looking_paths(self):
        paths, findings = self._run(
            b" M ordinary.txt\0?? space name.txt\0"
            b"?? literal -> arrow.txt\0?? \"quoted-looking\".txt\0"
        )
        self.assertEqual(findings, [])
        self.assertEqual(paths, [
            '"quoted-looking".txt', "literal -> arrow.txt", "ordinary.txt",
            "space name.txt",
        ])

    def test_rename_retains_out_of_scope_source_and_allowed_destination(self):
        paths, findings = self._run(
            b"R  docs/repository-policy.md\0outside-source.txt\0"
        )
        self.assertEqual(findings, [])
        self.assertEqual(paths, ["docs/repository-policy.md", "outside-source.txt"])
        scope_findings = check_corrective_scope(REPO_ROOT, paths, check_index=False)
        self.assertIn(
            "changes: path outside corrective nine-path scope: outside-source.txt",
            scope_findings,
        )

    def test_copy_retains_source_and_destination(self):
        paths, findings = self._run(
            b"C  docs/repository-policy.md\0copy-source.txt\0"
        )
        self.assertEqual(findings, [])
        self.assertEqual(paths, ["copy-source.txt", "docs/repository-policy.md"])

    def test_malformed_nul_records_fail_visibly(self):
        cases = (
            (b" M missing-final", "missing final NUL"),
            (b"bad\0", "malformed NUL status record"),
            (b"R  destination\0", "missing its source path"),
            (b"C  destination\0", "missing its source path"),
            (b" R destination\0", "missing its source path"),
            (b" C destination\0", "missing its source path"),
        )
        for stdout, expected in cases:
            with self.subTest(stdout=stdout):
                paths, findings = self._run(stdout)
                self.assertEqual(paths, [])
                self.assertTrue(any(expected in value for value in findings), findings)

    def test_status_command_failure_is_visible(self):
        paths, findings = self._run(b"", returncode=7)
        self.assertEqual(paths, [])
        self.assertEqual(findings, ["changes: git status failed with exit 7"])

    def test_documented_xy_status_table_is_accepted(self):
        statuses = (
            " M", " D", " T", " A", " R", " C",
            "M ", "MM", "MD", "MT", "A ", "AM",
            "AD", "AT", "D ", "R ", "RM", "RD", "RT", "C ",
            "CM", "CD", "CT", "T ", "TM", "TD", "TT",
            "DD", "AU", "UD", "UA", "DU", "AA", "UU", "??",
        )
        for status in statuses:
            with self.subTest(status=status):
                data = f"{status} path".encode() + b"\0"
                expected = ["path"]
                if "R" in status or "C" in status:
                    data += b"source\0"
                    expected = ["path", "source"]
                paths, findings = self._run(data)
                self.assertEqual(findings, [])
                self.assertEqual(paths, sorted(expected))

    def test_unknown_impossible_and_ignored_xy_statuses_are_rejected(self):
        explicit = {"ZZ", "?M", "M?", "  ", "!!", "DM"}
        documented = set(PORCELAIN_V1_TRACKED) | set(PORCELAIN_V1_UNMERGED) | {"??"}
        generated = {
            first + second
            for first in " MADRCTU?!"
            for second in " MADRCTU?!"
            if first + second not in documented
        }
        for status in sorted(explicit | generated):
            with self.subTest(status=status):
                paths, findings = self._run(f"{status} path\0".encode())
                self.assertEqual(paths, [])
                self.assertTrue(findings)

    def test_rename_copy_marker_in_either_position_consumes_source(self):
        for status in ("R ", "C ", " R", " C"):
            with self.subTest(status=status):
                paths, findings = self._run(
                    f"{status} destination".encode() + b"\0source\0"
                )
                self.assertEqual(findings, [])
                self.assertEqual(paths, ["destination", "source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
