# ADR 0003: Human-mediated dual-repository policy sync

- Status: Accepted for WP-0.2 local implementation
- Date: 2026-11-04
- Task: WP-0.2
- Requirement: PROG-00

## Context

WP-0.2 requires consistent policies in two independently controlled repositories.
Agent authority is repository-local, so direct sibling inspection or copying
would violate the isolation boundary. The Skinwalker build plan is canonical,
while repository identity and cloud defaults are repository-specific.

The branch began at verified WP-0.1 commit
`63b39b809413ced3a0b3b58f3a24e96394f8f11a`. This commit identifies the verified
branch baseline; it does not claim that the uncommitted WP-0.2 candidate existed
at that commit. The operator narrowly approved
the following preexisting dirty inputs and no others (path, byte count, SHA-256):

```text
.opencode/agents/ab-qa.md 1996 d3eb4a58a7e4ac4daa804a3f16baae1fd0355e1d55e23e61213812bc54e13523
.opencode/agents/implementer.md 1500 de105635ce39063dec4b3c9d3ae39d6a4e02b82b70f075b476f3f1a74a2324af
.opencode/agents/manager.md 2306 dcfce9535e1f1689256affb06f864adfacf46682ae6859797a3c72d947a1e5a4
.opencode/agents/review/correctness.md 754 06b50f0efd12d681c8e42ccaecb7d2f09c4788863bd5dc05a76806ab05f34eb3
.opencode/agents/review/evidence.md 890 a954e33a9a2bbdb9aaef7a21d8ecbfe75c2124ea426913bcaabc16d3e25c555c
.opencode/agents/review/security.md 870 4135b2c99d6aa28e30e6ea6bafe58a4eef36b3a64a1fde900e452fd681d11554
.opencode/commands/task-start.md 633 8347bd1ae10c8d7550b479d29fef2f6a248aa488e732526b814dda2f3b8977d2
AGENTS.md 11253 f4f8c0432280da38dc992f7c255824319013deefcdacc8bc247f412fa9600e10
docs/agent-workflow.md 3682 af6256797c8a2c4a9f83523b3fc44afe936964c4ed1bddbb6651322a955bc6f5
docs/decisions/0001-controlled-agent-workflow.md 1451 c5b5d31bbb8a7e9e105e0b34531f955f5821776bae65625d9b4a39f1d68d136c
opencode.jsonc 1152 2f4bb389afdb52b5eb1b4ad05a0f783e39596b03437228eb4ae053e77d50c562
```

An earlier inventory command failed with exit 127 because the zsh special
`path` loop variable overwrote executable PATH; it made no repository changes.
The successful retry produced the authoritative inventory above. No malformed
hash from the failed attempt is authoritative or used in calculations.

## Decision

1. Skinwalker authors the canonical shared bundle listed in
   `policy/shared-files.sha256`; the manifest is sorted and excludes itself.
2. `policy/repository-profile.json` contains repository-specific identity,
   canonical plan role and hash, cloud-write default, and zero WP-0.2 cost.
3. Agents cannot access a sibling repository. The operator performs any copy and
   real peer comparison. Synthetic peer drift tests stay under the ignored
   repository-local `/.policy-test-tmp/` directory.
4. The validator is deterministic, standard-library-only, and returns 0 pass,
   1 findings, or 2 input error. Agent-local evidence remains `Collected`.
5. Before review, final changed paths must be compared with both the narrow
   dirty-input inventory above and the WP-0.2 allowlist. Unexpected paths stop
   the task. Final hashes are not represented as the pre-edit hashes.
6. The task was reopened after the operator reported that Azure mirror validation
   found a P1 schema conflict: the canonical profile omitted mandatory paid-
   service and cost controls. No Azure repository access was used to record this
   operator-supplied discovery. Both approved profiles now require paid services
   disabled by default, a 0 USD out-of-pocket target, an Azure-credit target
   below 25 USD, and a 40 USD absolute ceiling without explicit approval.
7. The manager retains a broad shell denial followed only by individually
   scanned read-only Git preflight and shared-manifest verification commands.
   Arbitrary shell, dangerous Git, deletion, external-directory, Azure, and
   Terraform operations remain unavailable.
8. Corrective review cycle 2 replaces permissive regex/set extraction with a
   constrained structural parser that preserves permission order and cardinality,
   supports key reordering, and rejects malformed entries, unknown/duplicate/
   missing keys, duplicate approved allows, and a broad shell deny placed after
   an allow. Ordered narrowing denies follow the six mandated wildcard allows.
   They cover recognized Git output/external-command flags and command
   composition forms, but remain defense in depth rather than cryptographic
   prevention; OpenCode individual-command scanning remains required.
9. Skinwalker corrective changes are limited to nine named paths. `.gitignore`
   and ten disallowed canonical shared files are immutable and hash-pinned even
   if the shared manifest is edited. The ten shared hashes derive from the prior
   operator-reviewed canonical manifest/controlled read observation; no pre-edit
   shell transcript is claimed for that observation.
10. Required inputs and peer shared files reject symlinks and root escapes before
    reads or hashing. Profile and root configuration JSON reject duplicate keys.
    Report output is restricted to the single WP-0.2 evidence path.
11. `source_commit` remains the verified branch baseline rather than candidate
    provenance. `REPOSITORY_POLICY_HUMAN_PEER_VALIDATION` records operator intent
    to request peer mode; it does not authenticate the operator or prove identity.
12. The immutable corrective set contains all eleven paths: `.gitignore` plus
    ten disallowed canonical shared files. The `.gitignore` hash
    `9a2d473bf7cba2e910d1f794b4a45fcc33500c0921efa7fe73319ad5e88a6d29`
    comes from the controlled pre-correction local observation. The other ten
    hashes come from the operator-reviewed prior canonical manifest/controlled
    read observation. No historical shell transcript is invented for either.
13. Final review distinguishes actual newline commands from literal `\\n` text,
    parses NUL-delimited Git status records while retaining both rename/copy
    paths, and validates exact ordered root and manager permission sequences.
    Additional denies cover known Git difftool, no-index, help, signature,
    external/textconv, and composition forms. Because six prefix wildcard allows
    are operator-mandated, this is defense in depth and cannot prove every Git or
    configuration helper path is inert. Implementer/A-B-QA lexical denials remain
    an explicit out-of-scope limitation for this nine-path pass.
14. Evidence report replacement uses a contained temporary regular file, target
    no-follow opening where supported, parent revalidation, and atomic replacement.
    Portable standard-library
    code cannot claim complete elimination of the final filesystem race window.
15. The human operator authorized one exceptional fourth and final corrective
    cycle after the normal workflow correctly stopped at three cycles. The
    exception is limited to exactly three unresolved P1 findings: immutable
    staged/index state, broad `git log*`, and porcelain-v1 XY grammar. It grants
    no fifth cycle and no broader path, repository, network, cloud, or Git
    authority.
16. Immutable validation always checks working-tree bytes. Index mode and blob
    SHA-256 are inspected only when `git diff --cached --quiet -- <path>` reports
    an actual staged change. This intentionally ignores an older baseline index
    blob for an unstaged approved candidate. Staged entries must be a single
    stage-0 regular non-executable `100644` blob; deletions, type/mode changes,
    conflicts, malformed output, and plumbing failures are findings.
17. The broad `git log*` allow is removed. A deny for `git log*` precedes the
    sole exact override `git log -1 --oneline`, preserving six preflight allows
    while denying help, signature, format, and arbitrary extra arguments.
18. NUL-delimited porcelain-v1 status parsing validates documented XY grammar,
    rejects `!!` and impossible/unknown states, and preserves both paths for
    rename/copy records without interpreting filename text.
19. The operator authorized a fifth and final micro-correction solely for a
    confirmed porcelain-v1 grammar defect that remained after the exceptional
    fourth cycle. This supersedes the earlier no-fifth statement only for this
    defect: worktree-only ` A`, ` R`, and ` C` are valid; undocumented `DM` is
    invalid; and a rename/copy marker in either XY position consumes its second
    NUL-delimited source path. No sixth cycle, broader refactor, additional path,
    or expanded operational authority is granted.
20. After commit `139e05801ab54a08bf1dcc4246532fcb1672188e`, the operator
    reported an Azure compatibility failure without granting Azure repository
    access: the canonical suite hard-coded `repository == "skinwalker"` in the
    then-current `test_real_skinwalker_profile_has_exact_cost_controls`, and
    Azure-local required/allowed files omitted `README.md`. The profile model now
    stores repository-specific `local_files`: Skinwalker keeps only its local
    ADR-0003, while Azure requires its local ADR-0002 plus `README.md`.
    `required_files()` adds every approved local file, and the non-Skinwalker
    changed-path allowlist derives from it. `README.md` is not added to
    `SHARED_FILES` or the shared manifest, and Skinwalker gains no README. The
    real-repository profile test is identity-generic for either approved
    identity and validates `area`, `plan_role`, and exact cost controls.
21. Review of the first compatibility candidate identified a concrete
    canonical-identity gap: an identity-generic real-profile test alone let a
    Skinwalker tree select the approved Azure profile, which skips the
    Skinwalker corrective-scope and immutable-hash branch. The validator now
    binds the real repository profile to the local Git origin repository name
    (falling back to the checkout directory name when no origin exists).
    Synthetic policy trees remain unbound so the same canonical suite can run
    in the approved Azure mirror. This is a local defense-in-depth identity
    proxy, not an absolute sandbox: an actor able to rewrite both the profile
    and the local Git origin could still mislabel a checkout. The generic test
    retains the operator-required `area`, `plan_role`, and cost-control checks.

## Consequences

- Shared drift is machine-visible without granting cross-repository access.
- The operator must perform and record the peer copy/validation separately;
  this task cannot claim that policies already appear in the peer repository.
- Local and synthetic results are reproducible but are not live-cloud, network,
  GitHub, or peer-repository evidence.
