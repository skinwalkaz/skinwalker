# Controlled OpenCode Agent Workflow

## Authority model

The manager controls internal workflow gates. It may accept a candidate for QA,
reject a candidate back to implementation, and decide when the evidence package
is ready for human review. It cannot commit, push, merge, deploy, change cloud
resources, mark evidence `Verified`, or replace the human reviewer.

The human operator approves the task packet, authorizes any action outside the
standing permissions in `AGENTS.md`, and makes the final verification decision.
Only the human operator may copy policy to a sibling repository or perform a
real peer-repository comparison. Agents remain isolated to this repository.

## Roles

| Role | Writes files | Runs commands | Decision authority |
| --- | --- | --- | --- |
| `manager` | No | No | Internal stage promotion only |
| `implementer` | Approved task only | Approval-controlled | None |
| `ab-qa` | No | Approval-controlled | PASS, FAIL, or BLOCKED recommendation |
| `review/correctness` | No | No | Severity-ranked findings |
| `review/security` | No | No | Severity-ranked findings |
| `review/evidence` | No | No | Severity-ranked findings |
| Human operator | As chosen | As chosen | Final approval and `Verified` status |

## State flow

1. Human selects one task ID.
2. Manager creates the pre-edit task packet and waits for approval.
3. Implementer makes the smallest approved change and runs targeted checks.
4. A/B QA compares the approved baseline (A) with the candidate (B).
5. The three reviewers independently inspect correctness, security, and evidence.
6. Manager consolidates all results without hiding disagreements.
7. Implementer addresses P0/P1 findings; QA and review repeat.
8. After at most three cycles, manager either issues a blocker report or produces
   the completion report and sets the task to `Needs Review`.
9. Human accepts, requests changes, or rejects. Only the human may mark the task
   or evidence `Verified` and separately authorize commit or push.

P2 findings remain visible but do not automatically block `Needs Review` unless
the approved acceptance tests or safety boundaries make them release-blocking.

## A/B QA contract

- A is the base branch or last human-verified commit recorded in the task packet.
- B is the current candidate working tree.
- The comparison uses the same fixtures, commands, environment, and calculation
  method wherever practical.
- Results include raw counts, failures, skips, exclusions, warnings, and timing
  when timing is relevant.
- A test that is not meaningful for both sides is labeled `not applicable` rather
  than forced into a misleading comparison.
- Mocks and fixtures are never represented as live-cloud evidence.

## Starting a task

From OpenCode in the repository root, run:

```text
/task-start WP-X.Y <optional operator context>
```

Example:

```text
/task-start WP-1.1 Build only the package skeleton and clean-environment install gate. Keep hosted AI providers out of scope.
```

After reviewing the manager's task packet, use this approval only if it is
accurate:

```text
I approve this task packet for the stated task ID, scope, files, tests, and local permissions. Begin implementation. Do not commit, push, deploy, use live cloud services, or begin another task. Run the full A/B QA and three-reviewer cycle, then stop at Needs Review.
```

## Operating limits

- Maximum three implementation-review cycles per task.
- A repeated blocker produces a blocker report rather than an endless retry.
- Review agents are read-only and do not fix their own findings.
- The implementer cannot launch other agents.
- Git commit and push, destructive file removal, Terraform apply/destroy, and
  Azure CLI commands are denied by the project configuration.
- Git merge is denied. Repository visibility changes and all cloud writes also
  require explicit human authorization.
- Permission settings are defense in depth; `AGENTS.md` remains binding.
