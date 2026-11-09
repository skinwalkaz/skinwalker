# Repository Policy

This policy implements WP-0.2 / PROG-00 for the Skinwalker repository. The
canonical build plan remains `docs/build-plan.md`.

## Repository isolation and shared policy

Agents operate only inside the assigned repository. They must not list, read,
hash, validate, or modify a sibling repository. The human operator alone copies
the canonical shared bundle to a peer repository and runs real peer validation.
Agent tests may compare only synthetic trees under `/.policy-test-tmp/`.

`policy/shared-files.sha256` is the sorted SHA-256 manifest of the canonical
shared bundle and does not include itself. `policy/repository-profile.json`
records repository-specific identity, plan role, plan hash, cloud-write and paid
service defaults, cost targets and ceiling, and task cost. A changed shared byte
is drift, not an automatic sync request.

## Branch, change, and review controls

- Use one `feat/`, `fix/`, or `docs/` branch per requirement or tightly coupled
  acceptance unit. Reference the task and requirement in review material.
- Preserve unrelated changes. A task-specific changed-path allowlist bounds the
  implementation. WP-0.2 does not add or alter `.github/workflows`.
- Agents may not commit, push, merge, destructively delete, change visibility,
  or approve their own work. These actions require separate human authorization.
- Implementation and tests change together. Independent QA and correctness,
  security, and evidence review precede `Needs Review`.
- Only a human may assign `Verified` to a task or evidence item. Agent-local
  validation and synthetic peer tests do not satisfy human verification.

## Secrets and sensitive data

Never read or store `.env` files, credentials, tokens, private keys, Terraform
state, browser credentials, or cloud authentication caches. Use environment
variable names and obvious placeholders. Report a suspected secret path without
opening it. Run the local obvious-shape check over its explicit file set before
review; a pass is not proof that no secret exists.

## Fixtures, data, and licensing

Fixtures must be synthetic, sanitized, or explicitly redistributable. Record
source, author/publisher, retrieval date, license or terms, redistribution
decision, and transformations before use. Customer, employer, university, and
other non-lab telemetry is forbidden. Fixtures and mocks are test inputs, never
evidence of live services or production effectiveness.

## Evidence and generated artifacts

Preserve original evidence and telemetry. Store generated output separately
from hand-authored source, record the exact production command and Git state,
and regenerate rather than hand-edit generated artifacts. Evidence must expose
failures, warnings, skips, exclusions, limitations, provenance, and calculation
methods. New evidence remains `Collected` or `Needs Review` until human review.

The validator creates a stable WP-0.2 evidence template and records its own
local result. The manager may assemble the complete evidence artifact from
actual command transcripts, inventories, and controlled observations by filling
the labeled append points. Missing material stays explicitly `NOT RECORDED BY
THIS COMMAND`; future operator-mediated copy and peer output remains `NOT RUN`
until the operator supplies it. Controlled assembly must not invent results.

## Cloud authorization and cost

Cloud write defaults to false. Task approval never authorizes `terraform apply`,
`terraform destroy`, Azure CLI/PowerShell/SDK/API/portal writes, paid-plan or
trial activation, role or billing changes, public deployment, or attack traffic.
An explicit human-approved packet must name the subscription, resource group,
plan, resource changes, trial/licensing impact, estimated incremental and maximum
cost, lifetime and `expires_at`, validation, teardown, and empty-resource checks.

The portfolio target is zero out-of-pocket cost, under 25 USD of Azure credit,
and an absolute 40 USD ceiling without further human approval. WP-0.2 permits no
network or cloud action and has estimated and actual incremental cost of 0 USD.
Both approved repository profiles must encode these controls exactly as
`paid_service_default: false`, `out_of_pocket_target_usd: 0`,
`azure_credit_target_less_than_usd: 25`, and
`absolute_cost_ceiling_without_explicit_approval_usd: 40`; unknown profile keys
are rejected.

The manager has no arbitrary shell permission. After its broad shell denial it
may run only individual read-only preflight commands matching `git status*`,
`git branch --show-current*`, `git rev-parse HEAD`, `git diff*`, exact
`git log -1 --oneline`, and
`shasum -a 256 -c policy/shared-files.sha256`. These narrow permissions do not
authorize commit, push, merge, deletion, external-directory access, Azure or
Terraform writes, cloud activity, or automated verification.

Ordered denies after those six allows reject recognized Git output, external
diff/text conversion, pager/external-command configuration, redirection,
composition, chaining, and substitution forms. These glob patterns are defense
in depth, not cryptographic command isolation: OpenCode must scan each submitted
command individually, and the manager must not combine commands. Actual newline
and literal escaped-newline patterns are distinct and both are denied. Known
helper bypasses including `git difftool`, `git diff --no-index`, Git help, and
signature helper forms are also denied. The constrained
frontmatter validator preserves entry order and cardinality and rejects malformed
entries, unknown/duplicate/missing keys, duplicate allows, or moved denies.

The six prefix wildcard allows are operator-mandated. Narrowing denies reduce
known risk but cannot prove the absence of every Git/config/helper execution
path. The implementer and A/B-QA agents retain earlier lexical denial policies;
review of those files is outside this nine-path corrective pass. This limitation
is explicit rather than silently widening scope.

During this corrective cycle, changed paths are limited to the operator-approved
nine-path set. The previously dirty `.gitignore` and ten disallowed canonical
shared files are immutable and pinned by SHA-256; an updated shared manifest
cannot conceal drift in those files. The ten shared values come from the prior
operator-reviewed canonical manifest/controlled read observation, not a newly
invented pre-edit shell transcript. This provenance limitation stays visible.

Every required local policy input and every peer shared file must be a regular,
contained, non-symlink file before it is read or hashed. Policy JSON rejects
duplicate keys. `--report` may overwrite only
`docs/evidence/2026-11-04-wp-0.2-policy-validation.txt`, never source or the hash
manifest. Report assembly writes a contained temporary regular file, rechecks
the parent and target with no-follow opening where the platform supports it, and
atomically replaces the target. Standard-library
checks narrow but cannot portably eliminate every filesystem race between final
validation and replacement.

Changed-path discovery uses NUL-delimited porcelain output. Rename and copy
records retain and validate both source and destination without interpreting
spaces, arrow text, or quote-looking path bytes. The validator accepts only
documented ordinary, unmerged, and `??` porcelain-v1 XY states; it rejects
ignored `!!`, unknown, impossible, malformed, or incomplete rename/copy records.

Immutable scope validation has two independent layers. Working-tree bytes must
always match the approved SHA-256. For an immutable path with an actual staged
change, local noninteractive Git plumbing additionally requires one stage-0
index entry, mode `100644`, and staged blob bytes matching the approved SHA-256.
An unstaged tracked file does not fail merely because its baseline index blob
predates the approved uncommitted candidate. Staged deletion, conflicts,
multiple stages, executable/type modes, malformed output, and plumbing failures
all fail visibly; blob contents are hashed in memory and never printed.

## Local validation

Run from the repository root:

```text
python3 tools/validate_repository_policy.py
python3 tools/validate_repository_policy.py --check-format
python3 tools/validate_repository_policy.py --check-secrets
python3 tools/validate_repository_policy.py --report docs/evidence/2026-11-04-wp-0.2-policy-validation.txt
```

Exit codes are 0 for pass, 1 for findings, and 2 for usage/input error. Findings
and checked paths use stable lexical ordering. Real peer mode is human-only:

```text
REPOSITORY_POLICY_HUMAN_PEER_VALIDATION=1 python3 tools/validate_repository_policy.py --peer-root <operator-selected-peer-root>
```

Agents must not run that command against a real peer. Without the explicit human
confirmation variable, an external peer root is refused. The environment marker
records operator intent only; it is not authentication or proof of identity.
