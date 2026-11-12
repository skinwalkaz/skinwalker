"""Focused WP-0.3 ledger validator tests."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tools.validate_ledgers import main, validate

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = """# Evidence Ledger

| Evidence ID | Claim | Requirement | Evidence path or link | Verification command | Git commit | Date | Reviewer | Status |
|---|---|---|---|---|---|---|---|---|
| SAMPLE-SKW-000 | SAMPLE ONLY - structural test | PROG-00 | docs/evidence/example.txt | `python3 tools/validate_ledgers.py` | PENDING | 2026-11-09 | Unassigned | Open |
"""
COST = """# Azure Cost Ledger

| Date | Deployment profile | Resources started | Resources destroyed | Estimated retail cost | Credit consumed | Actual charge | Trial days remaining | Notes |
|---|---|---|---|---:|---:|---:|---:|---|
| 2026-11-09 | SAMPLE ONLY - no deployment | None (sample) | None (sample) | 0.00 | 0.00 | 0.00 | 0 | SAMPLE ONLY - structural test |
"""
REAL_OPEN_ROW = (
    "| E-SKW-001 | Real structural record | PROG-00 | docs/evidence/record.txt | "
    "`python3 tools/validate_ledgers.py` | PENDING | 2026-11-09 | Reviewer One | Open |"
)
REAL_VERIFIED_ROW = (
    "| E-SKW-001 | Real structural record | PROG-00 | docs/evidence/record.txt | "
    "`python3 tools/validate_ledgers.py` | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
    "| 2026-11-09 | Reviewer One | Verified |"
)


class LedgerValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "docs").mkdir()
        (self.root / "policy").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def configure(self, identity: object = "skinwalker") -> None:
        (self.root / "policy/repository-profile.json").write_text(
            json.dumps({"repository": identity}), encoding="utf-8"
        )
        (self.root / "docs/evidence-ledger.md").write_text(EVIDENCE, encoding="utf-8")
        if identity == "azure-soc-range":
            (self.root / "docs/cost-ledger.md").write_text(COST, encoding="utf-8")

    def findings(self) -> list[str]:
        return validate(self.root)[4]

    def write_evidence_row(self, row: str) -> None:
        header = "\n".join(EVIDENCE.splitlines()[:-1])
        (self.root / "docs/evidence-ledger.md").write_text(
            f"{header}\n{row}\n", encoding="utf-8"
        )

    def test_real_repository_sample_validates(self):
        evidence_sample, evidence_live, cost_sample, cost_live, findings = validate(
            REPO_ROOT
        )
        self.assertEqual(findings, [])
        self.assertGreaterEqual(evidence_sample, 0)
        self.assertGreaterEqual(evidence_live, 0)
        self.assertGreaterEqual(evidence_sample + evidence_live, 1)
        self.assertEqual((cost_sample, cost_live), (0, 0))

    def test_skinwalker_sample_validates_without_cost_ledger(self):
        self.configure()
        self.assertEqual(validate(self.root), (1, 0, 0, 0, []))

    def test_azure_sample_validates_with_cost_ledger(self):
        self.configure("azure-soc-range")
        self.assertEqual(validate(self.root), (1, 0, 1, 0, []))

    def test_real_only_ledger_validates_after_sample_removed(self):
        self.configure()
        self.write_evidence_row(REAL_OPEN_ROW)
        self.assertEqual(validate(self.root), (0, 1, 0, 0, []))

    def test_azure_missing_cost_ledger_fails(self):
        self.configure("azure-soc-range")
        (self.root / "docs/cost-ledger.md").unlink()
        self.assertTrue(any("cannot read" in item for item in self.findings()))

    def test_invalid_status_fails(self):
        self.configure()
        path = self.root / "docs/evidence-ledger.md"
        path.write_text(
            EVIDENCE.replace("| Open |", "| Approved |"), encoding="utf-8"
        )
        self.assertTrue(any("invalid Status" in item for item in self.findings()))

    def test_duplicate_evidence_id_fails(self):
        self.configure()
        path = self.root / "docs/evidence-ledger.md"
        row = EVIDENCE.splitlines()[-1]
        path.write_text(EVIDENCE + row + "\n", encoding="utf-8")
        self.assertTrue(any("duplicate Evidence ID" in item for item in self.findings()))

    def test_malformed_header_fails(self):
        self.configure()
        path = self.root / "docs/evidence-ledger.md"
        path.write_text(EVIDENCE.replace("| Claim |", "| Assertion |"), encoding="utf-8")
        self.assertTrue(any("missing exact required header" in item for item in self.findings()))

    def test_invalid_date_and_commit_fail(self):
        self.configure()
        path = self.root / "docs/evidence-ledger.md"
        text = EVIDENCE.replace("PENDING", "not-a-commit").replace(
            "2026-11-09", "2026-99-99"
        )
        path.write_text(text, encoding="utf-8")
        findings = self.findings()
        self.assertTrue(any("invalid Git commit" in item for item in findings))
        self.assertTrue(any("invalid ISO date" in item for item in findings))

    def test_negative_and_malformed_costs_fail(self):
        self.configure("azure-soc-range")
        path = self.root / "docs/cost-ledger.md"
        text = COST.replace(
            "| 0.00 | 0.00 | 0.00 | 0 |", "| -1.00 | nope | 0.00 | -2 |"
        )
        path.write_text(text, encoding="utf-8")
        findings = self.findings()
        self.assertTrue(any("nonnegative number" in item for item in findings))
        self.assertTrue(any("nonnegative integer" in item for item in findings))

    def test_sample_labels_are_mandatory(self):
        self.configure("azure-soc-range")
        evidence = self.root / "docs/evidence-ledger.md"
        evidence.write_text(
            EVIDENCE.replace("SAMPLE ONLY - structural test", "placeholder"),
            encoding="utf-8",
        )
        cost = self.root / "docs/cost-ledger.md"
        cost.write_text(
            COST.replace("SAMPLE ONLY - structural test", "placeholder"),
            encoding="utf-8",
        )
        findings = self.findings()
        self.assertTrue(any("sample claim must say SAMPLE ONLY" in item for item in findings))
        self.assertTrue(any("sample notes must say SAMPLE ONLY" in item for item in findings))

    def test_unsupported_repository_identity_fails(self):
        self.configure("wrong-repository")
        self.assertTrue(any("unsupported identity" in item for item in self.findings()))

    def test_non_string_repository_identity_values_fail_without_traceback(self):
        for value in ([], {}, 123, True, None):
            with self.subTest(value=value):
                self.configure(value)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = main(["--root", str(self.root)])
                output = stdout.getvalue() + stderr.getvalue()
                self.assertEqual(result, 1)
                self.assertIn(
                    "FINDING: repository profile has unsupported identity", output
                )
                self.assertNotIn("Traceback", output)

    def test_non_object_repository_profile_roots_fail_without_traceback(self):
        for value in ([], None, "skinwalker", 7):
            with self.subTest(value=value):
                self.configure()
                (self.root / "policy/repository-profile.json").write_text(
                    json.dumps(value), encoding="utf-8"
                )
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = main(["--root", str(self.root)])
                output = stdout.getvalue() + stderr.getvalue()
                self.assertEqual(result, 1)
                self.assertIn("FAIL:", output)
                self.assertIn(
                    "FINDING: repository profile JSON root must be an object", output
                )
                self.assertNotIn("Traceback", output)

    def test_interrupted_table_followed_by_row_fails(self):
        self.configure()
        path = self.root / "docs/evidence-ledger.md"
        path.write_text(
            EVIDENCE + "prose ends the table\n" + REAL_OPEN_ROW + "\n",
            encoding="utf-8",
        )
        self.assertTrue(
            any("after table interruption" in item for item in self.findings())
        )

    def test_trailing_row_after_blank_fails(self):
        self.configure()
        path = self.root / "docs/evidence-ledger.md"
        path.write_text(EVIDENCE + "\n" + REAL_OPEN_ROW + "\n", encoding="utf-8")
        self.assertTrue(
            any("after table interruption" in item for item in self.findings())
        )

    def test_sample_verified_fails(self):
        self.configure()
        path = self.root / "docs/evidence-ledger.md"
        text = (
            EVIDENCE.replace("PENDING", "a" * 40)
            .replace("Unassigned", "Reviewer One")
            .replace("Open", "Verified")
        )
        path.write_text(text, encoding="utf-8")
        self.assertTrue(
            any("sample evidence cannot be Verified" in item for item in self.findings())
        )

    def test_verified_pending_commit_fails(self):
        self.configure()
        self.write_evidence_row(REAL_VERIFIED_ROW.replace("a" * 40, "PENDING"))
        self.assertTrue(
            any("exactly 40 lowercase hex" in item for item in self.findings())
        )

    def test_verified_unassigned_reviewer_fails(self):
        self.configure()
        self.write_evidence_row(REAL_VERIFIED_ROW.replace("Reviewer One", "Unassigned"))
        self.assertTrue(
            any("reviewer cannot be a placeholder" in item for item in self.findings())
        )

    def test_verified_reviewer_placeholders_fail_exactly_after_normalization(self):
        self.configure()
        placeholders = (
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
        )
        for reviewer in placeholders:
            with self.subTest(reviewer=reviewer):
                normalized_variant = f"  {reviewer.upper()}  "
                self.write_evidence_row(
                    REAL_VERIFIED_ROW.replace("Reviewer One", normalized_variant)
                )
                self.assertTrue(
                    any(
                        "reviewer cannot be a placeholder" in item
                        for item in self.findings()
                    )
                )
        self.write_evidence_row(
            REAL_VERIFIED_ROW.replace("Reviewer One", "todo-reviewer")
        )
        self.assertEqual(self.findings(), [])

    def test_verified_placeholder_evidence_reference_fails(self):
        self.configure()
        for reference in ("TBD", "PENDING", "N/A", "docs/evidence/example.txt"):
            with self.subTest(reference=reference):
                self.write_evidence_row(
                    REAL_VERIFIED_ROW.replace("docs/evidence/record.txt", reference)
                )
                self.assertTrue(
                    any(
                        "reference cannot be a sample or placeholder" in item
                        for item in self.findings()
                    )
                )

    def test_verified_reference_placeholders_fail_exactly_after_normalization(self):
        self.configure()
        placeholders = (
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
            "docs/evidence/example.txt",
        )
        for reference in placeholders:
            with self.subTest(reference=reference):
                self.write_evidence_row(
                    REAL_VERIFIED_ROW.replace(
                        "docs/evidence/record.txt", f"  {reference.upper()}  "
                    )
                )
                self.assertTrue(
                    any(
                        "reference cannot be a sample or placeholder" in item
                        for item in self.findings()
                    )
                )
        self.write_evidence_row(
            REAL_VERIFIED_ROW.replace(
                "docs/evidence/record.txt", "docs/evidence/example.txt.backup"
            )
        )
        self.assertEqual(self.findings(), [])

    def test_live_form_id_with_casefolded_sample_marker_is_sample_and_fails(self):
        self.configure()
        row = REAL_VERIFIED_ROW.replace(
            "Real structural record", "sAmPlE oNlY - masquerading row"
        )
        self.write_evidence_row(row)
        sample_count, live_count, _, _, findings = validate(self.root)
        self.assertEqual((sample_count, live_count), (1, 0))
        self.assertTrue(any("must use a SAMPLE- Evidence ID" in item for item in findings))
        self.assertTrue(any("sample evidence cannot be Verified" in item for item in findings))

    def test_sample_marker_requires_explicit_words_not_substring(self):
        self.configure()
        self.write_evidence_row(
            REAL_OPEN_ROW.replace("Real structural record", "SAMPLE ONLYISH result")
        )
        self.assertEqual(validate(self.root), (0, 1, 0, 0, []))

    def test_structurally_valid_real_verified_row_passes(self):
        self.configure()
        self.write_evidence_row(REAL_VERIFIED_ROW)
        self.assertEqual(validate(self.root), (0, 1, 0, 0, []))

    def test_missing_evidence_ledger_fails(self):
        self.configure()
        (self.root / "docs/evidence-ledger.md").unlink()
        self.assertTrue(
            any("cannot read UTF-8 ledger" in item for item in self.findings())
        )

    def test_cli_returns_success_for_real_repository(self):
        self.assertEqual(main(["--root", str(REPO_ROOT)]), 0)


if __name__ == "__main__":
    unittest.main()
