# SanctuaryGG/.github — the org CI backbone

One reusable workflow, called by every code repository, pinned by full SHA (fleet rule 5,
ADR-PLT-0010 #3). Documentation of the whole pipeline lives in
`SanctuaryGG/platform` → `docs/ci-cd.md` (ADR-PLT-0009 as amended by ADR-PLT-0013).

## What is here

| Path | What |
|---|---|
| `.github/workflows/fleet-ci.yml` | The reusable workflow: the five gates (boundary selftest, boundary gate — service or kernel role, `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test`) on the pinned toolchain, with the `FLEET_TOKEN` kernel fetch wired through the git CLI credential helper. |
| `runner/` | The self-hosted runner for the owned cluster: manifest + bootstrap instructions. Not applied by agents; cluster changes are founder actions. |

## How a repository calls it

```yaml
# .github/workflows/ci.yml in any code repository
name: ci
on:
  push: { branches: [main] }
  pull_request:
permissions: { contents: read }
concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }
jobs:
  fleet:
    uses: SanctuaryGG/.github/.github/workflows/fleet-ci.yml@<full-commit-sha>
    secrets: inherit
```

The kernel repository adds `with: { kernel-role: true }`.
The SHA is bumped deliberately, in a PR, when the workflow changes — never a branch, never
a floating tag.

## Runner labels

Until the self-hosted pool exists, callers omit `runs-on` and jobs execute on GitHub-hosted
`ubuntu-latest` (metered minutes). When the cluster runner is live, the flip is one line per
caller: `with: { runs-on: "[self-hosted, sanctuary-ci]" }` — or a change of the default here.

## Rules that apply to this repository

- Only the reusable workflow and its runner manifest belong here; no product code ever lands
  in this repository.
- Third-party actions are pinned by full SHA; `permissions: contents: read` unless a job needs
  more.
- The FLEET_TOKEN secret never appears in a URL, a log, or this repository. A failed kernel
  fetch is an access problem to report, not to work around.
