# Local Prerequisites

WP-0.4 records a minimal, sanitized local capability baseline. Run:

```text
python3 tools/check_prerequisites.py
```

The command is offline, read-only, and standard-library-only. No
environment-variable values are emitted or stored. Executable discovery and
resolution use normal OS process search semantics (including `PATH`), but the
checker never prints resolved executable paths or environment values. It does
not inspect credentials, cloud state, authentication state, hostnames,
usernames, or home directories, and it does not check for updates or install
software.

## Fixed schema and collection methods

Fields are emitted once in the order below as `Field: Value`:

| Field | Collection command or method | Sanitized format |
|---|---|---|
| `Schema-Version` | Constant owned by the checker | Exact `1` |
| `OS-Family` | Python `platform.system()` | Exact `Darwin`, `Linux`, or `Windows` |
| `OS-Version` | Python `platform.mac_ver()[0]` on macOS; otherwise `platform.release()` | Two to four numeric dotted components with an optional alphanumeric `-` or `+` suffix |
| `CPU-Architecture` | Python `platform.machine()` | Allowlisted common architecture: `x86_64`, `AMD64`, `arm64`, `aarch64`, `i386` through `i686`, `ppc64le`, `s390x`, or `riscv64` |
| `Git-Version` | Safe local command `git --version` | Numeric dotted version only, or exact `Unavailable` |
| `Python-Version` | Safe local command `python3 --version` | Numeric dotted version only, or exact `Unavailable` |
| `Executable-git` | Python `shutil.which("git")`; path is discarded | Exact `Available` or `Unavailable` |
| `Executable-python3` | Python `shutil.which("python3")`; path is discarded | Exact `Available` or `Unavailable` |
| `Executable-terraform` | Python `shutil.which("terraform")`; path is discarded | Exact `Available` or `Unavailable` |
| `Executable-az` | Python `shutil.which("az")`; path is discarded | Exact `Available` or `Unavailable` |

Git and Python are the local source-control and runtime prerequisites.
Terraform and Azure CLI are recorded only as optional availability signals for
later, separately authorized work. The checker never invokes Terraform or
Azure CLI, including version, login, account, subscription, or trial commands.
A missing executable is reported as exact `Unavailable`; no version is inferred.

## Validation and exclusions

The same command validates its collected report before printing it. To validate
a report file without collecting new facts, use
`python3 tools/check_prerequisites.py --validate REPORT`. Validation rejects
missing, malformed, duplicate, unknown, empty, and out-of-order fields. It also
rejects selected common home-directory path patterns and Unix absolute paths
rooted at `/private`, `/var`, `/etc`, `/opt`, `/usr`, or `/tmp`; email
addresses; common authorization-token shapes; JWT-like strings; and values
outside each field's allowlist.

Cloud access, subscription identity, tenant identity, authentication state,
credit, licenses, and trial state are deliberately not checked. Those facts
require separate human-authorized Azure work and must not be inferred from
local executable availability. This local collection contacts no external
service, changes no resources, and has an incremental cost of `$0`.
