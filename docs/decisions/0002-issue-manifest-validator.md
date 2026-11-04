# ADR 0002: Declarative issue manifest with stdlib-only validator

- Status: Accepted
- Date: 2026-11-04
- Task: WP-0.1
- Operator decision: offline manifest + validator (live GitHub issue creation
  explicitly deferred; not authorized in this task)

## Context

WP-0.1 requires labels, an issue for every SKW/AZ requirement, and auditable
links from every work-package task to exactly one requirement and one
acceptance test. Not every contributor or environment has `gh` credentials or
network access, and the operator's standing rules forbid commits, pushes, and
network writes from this task. The manifest therefore needs to be verifiable
entirely offline.

## Decision

1. `.github/project-bootstrap.yml` is the single source of truth for labels,
   boards, the 16 SKW/AZ requirement issues plus the PROG-00 program
   requirement (17 total), task-to-requirement assignments, and verbatim
   `plan_verification` strings copied from the Work Breakdown Structure's
   Verification column.
2. `tools/validate_issue_manifest.py` reconciles the manifest against
   `docs/build-plan.md`: requirement-heading coverage, WBS-task coverage,
   uniqueness of task assignment, acceptance-test linkage, WBS verification
   text drift, mandatory/common-label and board integrity, and the requirement
   that `excluded_from_requirements` remain empty.
3. The validator uses only the Python standard library (Python 3.11+). The
   manifest is a deliberately restricted YAML subset; unsupported syntax
   fails visibly. A mapping line's key portion must not contain ": " (the
   parser splits at the FIRST colon-space, so a value may itself contain
   ": " but a bare duplicate colon in the key portion would silently split
   the key instead of failing); nesting is capped at 64 levels; and the
   manifest root must be a mapping. Malformed, overly nested, non-UTF-8, or
   otherwise unparseable input exits 1 with a `parse error` finding rather
   than a traceback, keeping the 0/1/2 exit-code contract intact; the
   manifest root is additionally guarded against being a plain list.
   `source_of_truth` must be a non-empty relative path (no NUL or other
   control characters, no absolute-path override) that resolves to the
   supplied plan relative to the manifest's own location only (never the
   launch CWD), duplicate requirement ids are rejected, and every nonempty
   exclusion list fails the gate. Bounded inline comments (`value # note`) are not
   supported and are absorbed into the value, so comments should be placed
   on their own lines. Pinning and installing PyYAML is deferred to the
   WP-1.1 locked environment rather than done piecemeal here.
4. Tests are standard-library `unittest` (`python3 -m unittest discover -s
   tests`) so the WP-0 stage runs with zero installs; the same files remain
   pytest-compatible for the WP-1.4 CI suite.
5. The validator rejects invented task ids: every assigned task must exist in
   the plan WBS, and `plan_verification` text is compared to the WBS
   Verification column. `related_tasks` cross-references (such as AZ-08
   referencing WP-11.4, which is primarily assigned to AZ-01) are permitted
   and are checked after all assignments are collected, so the outcome does
   not depend on the order requirements appear in the file.
6. The board requirement is exactly one board per supported area, and every
   board must carry a Deferred (status:deferred) column, so deferred items
   land on a board lane rather than living outside board columns.
7. Every requirement issue uses the common labels `type:requirement` and
   `evidence:required`; both labels are mandatory manifest definitions.

## Corrections recorded

The reopen-cycle directives from the operator are mapped as follows:
1. ab-qa + review/correctness + review/security + review/evidence cycle:
   executed (results consolidated below; see cycle record in
   docs/evidence/2026-11-04-wp-0.1-validation.txt section 8).
2. Gate/exclusion conflict resolved non-silently: PROG-00 owns the four WP-0
   tasks, so zero exclusions exist and the gate holds literally for all 57
   plan tasks (bullet "WP-11.4"/owner correction and PROG-00 below).
3. WP-11.4 reassessed: **AZ-01 Cost and safety controls** is the primary
   owner (the teardown verification is a cost-and-safety control); AZ-08
   Delivery lists WP-11.4 as a `related_tasks` cross-reference. An earlier
   draft of this ADR recorded the AZ-08-as-primary orientation.
4. Exactly one board per supported area (`skinwalker`, `azure`, `program`
   -> three boards), enforced by the validator.
5. `source_of_truth` validated against the plan file supplied on the command
   line (required to be relative, resolvable from the manifest's own
   location, NUL-free; type-checked).
6. Duplicate requirement ids are rejected, and every nonempty exclusion list
   fails because all 57 WBS tasks must map to exactly one requirement.
7. Deferred board columns added to all three boards (validator-enforced),
   chosen over leaving deferred items outside board columns.
8. The evidence artifact preserves the complete unittest output (section 2)
   and the exact secret-scan command with its raw exit code (section 5);
   both sections are reproduced in full within the artifact.
9. Every corrected validator gap has a regression test (50 total:
   unassigned-plan-task branch, reverse ownership rule, title drift, plan
   anchor drift, missing plan_verification, duplicate board name,
   unsupported board area, depth cap, source_of_truth type/binding/
   absolute-path/NUL cases, non-list root, scalar related_tasks, real
   label-value output, duplicates, zero-exclusion enforcement, and both
   mandatory common labels).

Final human-review corrections additionally enforce the literal zero-exclusion
gate even for a well-formed WP-0 exclusion and require both common issue-label
definitions. Per operator direction these changes were locally verified and
returned directly to human review without a fourth automated review cycle.

Earlier corrections from the validator v1 review are retained below.

## Consequences

- The gate "every task links to one requirement and one acceptance test" is
  machine-checked, and future edits to the plan's WBS or headings produce
  immediate validator findings (drift alarm), including deleted requirements.
- Live GitHub label/issue/board creation must happen later under explicit
  human authorization; until then the validator output is the evidence of
  structure, not proof of GitHub state.
- The restricted YAML subset is a documented limitation: complex YAML is
  rejected rather than half-parsed.
