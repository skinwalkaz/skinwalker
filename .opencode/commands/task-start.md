---
description: Start one controlled task through the manager workflow
agent: manager
---

Start task `$1` using the repository's controlled multi-agent workflow.

Read `AGENTS.md` and only the sections of `docs/build-plan.md` required for this
task, its requirement, dependencies, and definition of done. First produce the
complete pre-edit task packet required by `AGENTS.md`, including the A baseline
for later A/B QA. Do not implement or launch the implementer until I explicitly
approve that packet. If `$1` is empty or does not map to a plan task, stop and
ask me for a valid task ID.

Additional operator context: $ARGUMENTS
