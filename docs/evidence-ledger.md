# Evidence Ledger

Use one immutable row per evidence item. After a row becomes `Verified`, record
corrections under a new evidence ID and mark the old row `Superseded`. A human
reviewer is the only person who may assign `Verified`.

The sample row validates the template and may be removed when the first real
row is added. For a `Verified` row, the validator requires a real evidence
reference, an assigned reviewer, and an exact 40-character lowercase commit
hash. These are structural prerequisites only; validation does not prove that
the named reviewer is human, that review occurred, or repository identity.

| Evidence ID | Claim | Requirement | Evidence path or link | Verification command | Git commit | Date | Reviewer | Status |
|---|---|---|---|---|---|---|---|---|
| SAMPLE-SKW-000 | SAMPLE ONLY - replace with measured project evidence | PROG-00 | docs/evidence/example.txt | `python3 tools/validate_ledgers.py` | PENDING | 2026-11-09 | Unassigned | Open |
| E-SKW-001 | Sanitized deterministic local prerequisite and version report | PROG-00 | docs/evidence/2026-11-10-wp-0.4-prerequisites.txt | `python3 tools/check_prerequisites.py` | PENDING | 2026-11-10 | Unassigned | Collected |

Allowed statuses: `Open`, `Collected`, `Needs Review`, `Verified`, `Failed`, and
`Superseded`.
