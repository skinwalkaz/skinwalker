# ADR 0001: Controlled multi-agent workflow

- Status: Accepted for local harness configuration
- Date: 2026-11-04
- Task: WP-0.2

## Context

The project needs AI-assisted implementation without allowing one agent to write,
test, review, and approve its own work. Repository policy also reserves evidence
verification, commits, pushes, cloud changes, and deployments for explicit human
decisions.

## Decision

Use a non-editing primary `manager` agent, a single task-scoped `implementer`, an
independent read-only `ab-qa` agent, and three read-only reviewers for
correctness, security, and evidence. The manager may promote or reject work
between internal stages, but the workflow stops at `Needs Review` for a human
decision. Review iteration is capped at three cycles.

The A/B baseline is the base branch or last human-verified commit recorded in
the approved task packet. The candidate is the current working tree. Results
must use comparable fixtures and commands, retain failures and exclusions, and
avoid treating mock output as live evidence.

## Consequences

- Writing and approval responsibilities are separated.
- Review findings can be iterated without granting reviewers edit authority.
- Every task has a finite stopping condition.
- The workflow uses additional model calls and may consume more provider quota.
- Permission configuration reduces accidental actions but does not replace the
  repository instructions or human review.
