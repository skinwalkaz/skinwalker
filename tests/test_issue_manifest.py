"""Tests for tools/validate_issue_manifest.py (task WP-0.1).

Positive, negative, malformed-input, and failure-path coverage of the
WP-0.1 gate: "Every task links to one requirement and one acceptance test."

Runner: standard-library unittest (also pytest-compatible so the future
WP-1.4 CI suite can pick the same file up unchanged).

    python3 -m unittest discover -s tests
    python3 -m unittest tests.test_issue_manifest -v

The default positive case runs against the real repository manifest and the
real build plan. Negative cases mutate a copy in a temporary directory; the
repository files are never modified.
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.validate_issue_manifest import (  # noqa: E402
    ManifestError,
    parse_manifest_text,
    parse_plan,
    validate,
    main,
)

MANIFEST = REPO_ROOT / ".github/project-bootstrap.yml"
PLAN = REPO_ROOT / "docs/build-plan.md"
MALFORMED = REPO_ROOT / "tests/fixtures/malformed_manifest.yml"


def run_validator(manifest: Path | str, plan: Path) -> tuple[int, str]:
    """Run the validator CLI and return (exit_code, captured_stdout).

    stderr is captured and discarded: expected-failure paths (exit 1 or 2)
    print their diagnostics to stdout as FINDING lines, and the exit-2 stderr
    noise is asserted separately in the dedicated usage tests.
    """
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(io.StringIO()):
        code = main([str(manifest), str(plan)])
    return code, buffer.getvalue()


def mutated(tmp: Path | str, replacements: list[tuple[str, str]]) -> Path:
    """Write a mutated copy of the real manifest into tmp and return its path."""
    tmp = Path(tmp)
    text = MANIFEST.read_text(encoding="utf-8")
    for old, new in replacements:
        if old not in text:
            raise AssertionError(f"mutation seed not found in manifest: {old!r}")
        text = text.replace(old, new, 1)
    path = tmp / "mutated_manifest.yml"
    path.write_text(text, encoding="utf-8")
    return path


class RealRepositoryGateTest(unittest.TestCase):
    """The real manifest must satisfy the WP-0.1 gate against the real plan."""

    def test_real_files_pass_gate(self):
        code, out = run_validator(MANIFEST, PLAN)
        self.assertEqual(code, 0, out)
        self.assertIn("OK: 17 requirement issues", out)
        self.assertIn("57 mapped tasks", out)
        self.assertIn("0 excluded tasks", out)
        self.assertIn("57 plan WBS tasks", out)
        self.assertIn("3 boards", out)
        self.assertIn("13 labels", out)

    def test_every_requirement_issue_is_listed(self):
        code, out = run_validator(MANIFEST, PLAN)
        self.assertEqual(code, 0, out)
        for req_id in (
            "PROG-00",
            "SKW-01", "SKW-02", "SKW-03", "SKW-04",
            "SKW-05", "SKW-06", "SKW-07", "SKW-08",
            "AZ-01", "AZ-02", "AZ-03", "AZ-04",
            "AZ-05", "AZ-06", "AZ-07", "AZ-08",
        ):
            self.assertIn(f"[{req_id}]", out)

    def test_parse_plan_inventory(self):
        requirements, tasks, program_title = parse_plan(PLAN)
        self.assertEqual(len(requirements), 16)
        self.assertEqual(len(tasks), 57)
        self.assertEqual(tasks["WP-11.4"], "Unexpected billable-resource query returns zero")
        self.assertEqual(requirements["SKW-01"], "Package and CLI")
        self.assertEqual(program_title, "Program setup and controls")

    def test_ok_output_reports_real_label_values(self):
        """The OK output must interpolate real priority/area labels (no '*')."""
        code, out = run_validator(MANIFEST, PLAN)
        self.assertEqual(code, 0, out)
        self.assertIn("[SKW-01] Package and CLI [labels: type:requirement "
                      "priority:p0 area:skinwalker status:ready evidence:required]",
                      out)
        self.assertIn("[AZ-02] Infrastructure as code [labels: type:requirement "
                      "priority:p0 area:azure status:ready evidence:required]",
                      out)
        self.assertIn("[PROG-00] Program setup and controls [labels: "
                      "type:requirement priority:p0 area:program status:ready "
                      "evidence:required]", out)
        self.assertNotIn("priority:*", out)
        self.assertNotIn("area:*", out)

    def test_parser_preserves_quoted_and_colon_values(self):
        manifest = parse_manifest_text(MANIFEST.read_text(encoding="utf-8"))
        first_label = manifest["labels"][0]
        self.assertEqual(first_label["name"], "type:requirement")
        self.assertEqual(first_label["color"], "5319E7")
        self.assertEqual(manifest["excluded_from_requirements"], [])
        related = next(
            req for req in manifest["requirements"] if req["id"] == "AZ-08"
        )["related_tasks"]
        self.assertEqual(related, ["WP-11.4"])

    def test_gate_holds_without_exceptions(self):
        """Every plan task maps to exactly one requirement; exclusions are zero."""
        findings, summary = validate(MANIFEST, PLAN)
        self.assertEqual(findings, [])
        self.assertEqual(len(summary["task_requirement"]), 57)
        _, tasks, _ = parse_plan(PLAN)
        for task_id in tasks:
            self.assertIn(task_id, summary["task_requirement"], task_id)

    def test_wp11_4_primary_is_az01_and_az08_cross_references(self):
        findings, summary = validate(MANIFEST, PLAN)
        self.assertEqual(findings, [])
        self.assertEqual(summary["task_requirement"]["WP-11.4"], "AZ-01")
        self.assertEqual(summary["task_requirement"]["WP-11.2"], "AZ-08")
        self.assertEqual(summary["task_requirement"]["WP-11.3"], "AZ-08")
        manifest = parse_manifest_text(MANIFEST.read_text(encoding="utf-8"))
        by_id = {req["id"]: req for req in manifest["requirements"]}
        self.assertIn("WP-11.4", [wp["task"] for wp in by_id["AZ-01"]["work_packages"]])
        self.assertNotIn("WP-11.4", [wp["task"] for wp in by_id["AZ-08"]["work_packages"]])
        self.assertEqual(by_id["AZ-08"].get("related_tasks"), ["WP-11.4"])
        self.assertNotIn("related_tasks", by_id["AZ-01"])
        # Program tasks are owned only by PROG-00.
        for wp_index in ("WP-0.1", "WP-0.2", "WP-0.3", "WP-0.4"):
            self.assertEqual(summary["task_requirement"][wp_index], "PROG-00")


class BoardStructureTest(unittest.TestCase):
    """Directives 4 and 7: exactly one board per supported area; Deferred column."""

    def setUp(self):
        self.manifest = parse_manifest_text(MANIFEST.read_text(encoding="utf-8"))

    def test_exactly_one_board_per_supported_area(self):
        areas = sorted(
            {req["area"] for req in self.manifest["requirements"]}
        )
        boards = self.manifest["boards"]
        board_areas = sorted(board["filter_area"] for board in boards)
        self.assertEqual(board_areas, areas)
        self.assertEqual(len(board_areas), len(set(board_areas)))

    def test_every_board_has_deferred_column(self):
        for board in self.manifest["boards"]:
            labels = {col["label"] for col in board["columns"]}
            self.assertIn("status:deferred", labels, board["name"])


class UsageAndInputErrors(unittest.TestCase):
    def test_missing_manifest_file_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = run_validator(Path(tmp) / "does-not-exist.yml", PLAN)
        self.assertEqual(code, 2)

    def test_missing_plan_file_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = run_validator(MANIFEST, Path(tmp) / "no-plan.md")
        self.assertEqual(code, 2)

    def test_wrong_argument_count_exits_two(self):
        buffer = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(buffer):
            code = main([str(MANIFEST)])
        self.assertEqual(code, 2)
        self.assertIn("usage:", buffer.getvalue())


class GateFailurePaths(unittest.TestCase):
    """Seeded defects must fail the gate with a visible, specific finding."""

    def test_dropped_requirement_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [("- id: SKW-02\n    title: Canonical event model",
                                  "- id: SKW-02X\n    title: Canonical event model")])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("SKW-02X", out)
        self.assertIn("no matching", out)

    def test_renamed_plan_requirement_fails_both_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = PLAN.read_text(encoding="utf-8").replace(
                "#### SKW-02 Canonical event model", "#### AZ-09 Canonical event model"
            )
            plan_copy = Path(tmp) / "az09-plan.md"
            plan_copy.write_text(text, encoding="utf-8")
            code, out = run_validator(MANIFEST, plan_copy)
        self.assertEqual(code, 1, out)
        self.assertIn("plan requirement AZ-09 has no issue in the manifest", out)
        self.assertIn("requirement id 'SKW-02' has no matching '#### ' heading in the plan", out)

    def test_duplicate_requirement_id_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "  - id: SKW-02\n    title: Canonical event model",
                "  - id: SKW-02\n    title: Canonical event model\n"
                "  - id: SKW-02\n    title: Canonical event model",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("requirement id 'SKW-02' is defined 2 times", out)

    def test_duplicate_exclusion_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "excluded_from_requirements: []",
                "excluded_from_requirements:\n"
                "  - task: WP-0.4\n    reason: first synthetic reason\n"
                "  - task: WP-0.4\n    reason: second synthetic reason",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("excluded task 'WP-0.4' is listed 2 times", out)

    def test_well_formed_exclusion_cannot_replace_requirement_mapping(self):
        """WP-0.4 must remain mapped to PROG-00; exclusions are forbidden."""
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [
                (
                    "excluded_from_requirements: []",
                    "excluded_from_requirements:\n"
                    "  - task: WP-0.4\n"
                    "    reason: synthetic well-formed exclusion",
                ),
                (
                    "      - task: WP-0.4\n"
                    "        acceptance: Version and access report exists; no secrets are stored; subscription and trial status are recorded.\n"
                    "        plan_verification: No secrets stored; subscription and trial status recorded\n",
                    "",
                ),
            ])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("'excluded_from_requirements' must be empty", out)
        self.assertNotIn("plan task WP-0.4 is neither assigned", out)

    def test_non_wp0_exclusion_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "excluded_from_requirements: []",
                "excluded_from_requirements:\n"
                "  - task: WP-2.1\n    reason: synthetic negative test",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("excluded task 'WP-2.1' is not a WP-0 program task", out)
        self.assertIn("task WP-2.1 is both assigned to SKW-02 and listed under "
                      "excluded_from_requirements", out)

    def test_exclusion_without_reason_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "excluded_from_requirements: []",
                "excluded_from_requirements:\n"
                "  - task: WP-0.4",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("excluded task WP-0.4 is missing a reason", out)

    def test_unknown_excluded_task_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "excluded_from_requirements: []",
                "excluded_from_requirements:\n"
                "  - task: WP-0.9\n    reason: synthetic unknown task",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("excluded task WP-0.9 does not exist in the plan WBS", out)

    def test_source_of_truth_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_copy = Path(tmp) / "other-plan.md"
            plan_copy.write_text(PLAN.read_text(encoding="utf-8"), encoding="utf-8")
            code, out = run_validator(MANIFEST, plan_copy)
        self.assertEqual(code, 1, out)
        self.assertIn("source_of_truth", out)
        self.assertIn("does not resolve to the supplied plan", out)

    def test_program_requirement_cannot_own_non_program_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "      - task: WP-0.4\n        acceptance: Version and access report",
                "      - task: WP-10.6\n        acceptance: Version and access report",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("program requirement PROG-00 owns non-program task 'WP-10.6'",
                      out)

    def test_board_area_must_cover_each_supported_area_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [("    filter_area: azure", "    filter_area: skinwalker")])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("supported area 'azure' is covered by 0 boards", out)
        self.assertIn("supported area 'skinwalker' is covered by 2 boards", out)

    def test_missing_deferred_column_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = MANIFEST.read_text(encoding="utf-8").replace(
                "      - name: Deferred\n        label: status:deferred\n",
                "",
                1,
            )
            path = Path(tmp) / "no_deferred_manifest.yml"
            path.write_text(text, encoding="utf-8")
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("must include a Deferred column", out)

    def test_duplicate_task_assignment_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [
                ("      - task: WP-2.2",
                 "      - task: WP-2.2\n        plan_verification: Valid and "
                 "malformed fixtures pass\n      - task: WP-2.1"),
            ])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("task WP-2.1 is assigned to both SKW-02 and SKW-03", out)

    def test_task_without_acceptance_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "        acceptance: Schema round-trip and invalid-data tests pass.\n",
                "\n",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("task WP-2.1 is missing an 'acceptance' statement", out)

    def test_verification_text_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "        plan_verification: CLI smoke tests pass",
                "        plan_verification: CLI is tested",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("task WP-1.3 plan_verification 'CLI is tested' does not "
                      "match plan verification 'CLI smoke tests pass'", out)

    def test_board_targets_undefined_label_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "      - name: In Progress\n        label: status:in-progress\n"
                "      - name: Needs Review\n        label: status:needs-review",
                "      - name: In Progress\n        label: status:in-progress\n"
                "      - name: Needs Review\n        label: status:ghost-column",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("status:ghost-column", out)

    def test_invented_task_fails(self):
        """A well-formed task id absent from the plan WBS must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [
                ("      - task: WP-2.2",
                 "      - task: WP-2.6\n"
                 "        acceptance: Invented task that is not in the plan WBS.\n"
                 "        plan_verification: This verification text exists "
                 "nowhere in the plan\n      - task: WP-2.2"),
            ])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("task WP-2.6 is not present in the plan WBS", out)

    def test_unassigned_plan_task_fails(self):
        """The primary gate direction: dropping an assignment must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "      - task: WP-2.1\n        acceptance: Schema round-trip",
                "      - task: WP-2.2\n        acceptance: Schema round-trip",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("plan task WP-2.1 is neither assigned to a requirement "
                      "nor explicitly excluded", out)
        self.assertIn("task WP-2.2 is assigned to both SKW-02 and SKW-03", out)

    def test_non_program_requirement_cannot_own_program_task(self):
        """Mirror of the PROG ownership rule (ab-qa coverage asymmetry)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "      - task: WP-2.1\n        acceptance: Schema round-trip",
                "      - task: WP-0.1\n        acceptance: Schema round-trip",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("requirement SKW-02 cannot own program task 'WP-0.1'", out)

    def test_requirement_title_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "- id: SKW-03\n    title: Telemetry ingestion",
                "- id: SKW-03\n    title: Telemetry capture",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("requirement SKW-03 title 'Telemetry capture' does not "
                      "match plan heading 'Telemetry ingestion'", out)

    def test_requirement_anchor_drift_fails(self):
        """Directive 9: the plan_anchor branch needs its own pinning test."""
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "    plan_anchor: skw-01-package-and-cli",
                "    plan_anchor: skw-01-package-and-cli-fake",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("requirement SKW-01 plan_anchor "
                      "'skw-01-package-and-cli-fake' does not match plan "
                      "heading (expected 'skw-01-package-and-cli')", out)

    def test_related_tasks_scalar_fails_without_crash(self):
        """A non-list related_tasks value must produce the type finding only."""
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "    related_tasks:\n      - WP-11.4",
                "    related_tasks: WP-11.4",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("requirement AZ-08 'related_tasks' must be a list", out)
        self.assertNotIn("is not a task id", out)

    def test_missing_plan_verification_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "        acceptance: Schema round-trip and invalid-data tests pass.\n"
                "        plan_verification: Round-trip and invalid-data tests pass",
                "        acceptance: Schema round-trip and invalid-data tests pass.",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("task WP-2.1 is missing 'plan_verification'", out)

    def test_duplicate_board_name_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "  - name: Azure Requirements",
                "  - name: Skinwalker Requirements",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("board 'Skinwalker Requirements' is defined 2 times", out)

    def test_unsupported_board_area_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "    filter_area: azure",
                "    filter_area: general",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("has unsupported filter_area 'general'", out)
        self.assertIn("supported area 'azure' is covered by 0 boards", out)

    def test_undefined_priority_label_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [("    priority: p0", "    priority: p9")])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("references undefined priority label 'priority:p9'", out)

    def test_missing_type_requirement_label_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "  - name: type:requirement\n"
                "    color: \"5319E7\"\n"
                "    description: Top-level requirement from the approved build plan\n",
                "",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("missing mandatory issue label 'type:requirement'", out)

    def test_missing_evidence_required_label_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "  - name: evidence:required\n"
                "    color: \"006B75\"\n"
                "    description: Cannot close until evidence-ledger entries are human-verified\n",
                "",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("missing mandatory issue label 'evidence:required'", out)

    def test_repeated_board_column_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "      - name: Ready\n        label: status:ready\n"
                "      - name: In Progress",
                "      - name: Ready\n        label: status:ready\n"
                "      - name: Ready\n        label: status:ready\n"
                "      - name: In Progress",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("board 'Skinwalker Requirements' repeats column 'Ready'", out)

    def test_cross_reference_is_order_independent(self):
        """AZ-08 (cross-referencing WP-11.4) may appear before AZ-01 (primary)."""
        text = MANIFEST.read_text(encoding="utf-8")
        marker = "  - id: AZ-08\n"
        az08_block = text[text.index(marker):]
        trimmed = text[:text.index(marker)]
        insert_at = trimmed.index("  - id: AZ-01\n")
        reordered = trimmed[:insert_at] + az08_block + trimmed[insert_at:]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github").mkdir()
            (root / "docs").mkdir()
            # Manifest binding is location-relative, so mirror the repo layout:
            # .github/<manifest> with source_of_truth resolving to docs/<plan>.
            (root / "docs/build-plan.md").write_text(
                PLAN.read_text(encoding="utf-8"), encoding="utf-8")
            path = root / ".github/reordered_manifest.yml"
            path.write_text(reordered, encoding="utf-8")
            code, out = run_validator(path, root / "docs/build-plan.md")
        self.assertEqual(code, 0, out)

    def test_reversed_cross_reference_order_still_passes(self):
        """Cross-referencer after primary is the current manifest order."""
        code, out = run_validator(MANIFEST, PLAN)
        self.assertEqual(code, 0, out)


class MalformedInputTest(unittest.TestCase):
    def test_malformed_fixture_fails_visibly(self):
        code, out = run_validator(MALFORMED, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("parse error", out)
        self.assertIn("unsupported", out)

    def test_excessive_nesting_fails_visibly(self):
        """Pathological nesting must exit 1 with a parse error, never a traceback."""
        deep = "\n".join("  " * level + f"key_{level}:" for level in range(1000))
        deep += "\n  " * 1000 + "  leaf: value"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep_manifest.yml"
            path.write_text("version: 1\nsource_of_truth: docs/build-plan.md\n"
                            + deep, encoding="utf-8")
            try:
                parse_manifest_text(path.read_text(encoding="utf-8"))
            except ManifestError as exc:
                self.assertIn("nesting exceeds supported depth", str(exc))
            code, out = run_validator(path, PLAN)
            self.assertEqual(code, 1, out)
            self.assertIn("parse error", out)
            self.assertIn("nesting exceeds supported depth", out)

    def test_non_string_source_of_truth_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [
                ("source_of_truth: docs/build-plan.md", "source_of_truth: []"),
            ])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("source_of_truth must be a string", out)

    def test_root_must_be_mapping_fails(self):
        """A top-level sequence manifest must exit 1, not crash on dict access."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "root_list.yml"
            path.write_text(
                "- version: '1'\n"
                "- source_of_truth: docs/build-plan.md\n",
                encoding="utf-8",
            )
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("parse error: manifest root must be a mapping", out)
        self.assertIn("got list", out)

    def test_absolute_source_of_truth_fails(self):
        """An absolute truth path must be rejected even if it names the plan."""
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [(
                "source_of_truth: docs/build-plan.md",
                f"source_of_truth: {PLAN.resolve()}",
            )])
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("must be a relative path", out)

    def test_nul_byte_source_of_truth_fails(self):
        """A NUL inside truth must yield a FINDING, never a ValueError traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nul_manifest.yml"
            path.write_bytes(
                MANIFEST.read_bytes().replace(
                    b"docs/build-plan.md", b"docs/build-plan.md\x00evil.md", 1)
            )
            code, out = run_validator(path, PLAN)
        self.assertEqual(code, 1, out)
        self.assertIn("parse error: source_of_truth", out)
        self.assertIn("control characters", out)

    def test_unknown_indentation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = mutated(tmp, [("  - id: SKW-01", "      - id: SKW-01")])
            try:
                parse_manifest_text(path.read_text(encoding="utf-8"))
            except ManifestError as exc:
                # The deeper dash line either becomes unexpected content or a
                # duplicate sub-key; both are visible parse failures.
                self.assertTrue(
                    "unexpected content" in str(exc) or "duplicate key" in str(exc),
                    str(exc),
                )
            else:
                self.fail("parser accepted unsupported indentation")
            code, out = run_validator(path, PLAN)
            self.assertEqual(code, 1, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
