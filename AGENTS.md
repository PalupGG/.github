<!-- fleet:begin source=PalupGG/platform@main sha256=de71c1e52e358594 · edit in PalupGG/platform, never here · local rules go below fleet:end -->
# AGENTS.md — PalupGG fleet

PalupGG is a marketplace where adults book paid one-to-one gaming sessions with verified
providers. Fourteen repositories: the five services (identity, marketplace, ledger, chat,
web), the kernel crate, the console, rooms, gitops, the platform and headquarters
documentation repositories, the `.github` workflow repository, agent-skills and the
analysis archive. Everything above `fleet:end` is one block, distributed to the other
repositories as sync PRs (ADR-PLT-0011); the section below it is local to this repository.

Read, in order: this block → the local section → `FEATURES.md` (code repositories) → your issue.

State, measured 2026-11-19 — one claim per line, each checkable by a command (workflow runs:
`gh run list -R PalupGG/<repo> --branch main`; releases: `gitops/releases/<env>.yaml`; PRs:
`gh pr view`; hostnames: `curl -sI`):

- CI gates PRs and main pushes in every code repository; green on `main` today in kernel,
  identity, marketplace and ledger (kernel 44356588769; identity 44417401280 plus its auth
  `flow` 44417401009; marketplace 44392729122; ledger 44386134361, its `e2e` 44386134738 and
  the D1 money-gate `proofs` 44386133775).
- Red on `main` today, named: chat `ci` failing at the image push since 2026-11-17
  (44213674681; `e2e` last green 2026-11-16, 43936677621); rooms `ci` failing (44378270734);
  web `ci` green but `site` failing on the newest pushes (44420111548); `.github` selftest
  failing on 2026-11-17 (44140370536, later runs cancelled); console has no `main` run yet.
- web, chat and identity run as proto Workers (ADR-PLT-0029 rev 2): web serves the three
  hostnames; chat and identity have no hostname of their own (ADR-PLT-0027) and ride web's
  `CHAT` and `IDENTITY` service bindings (`site/wrangler.jsonc`); identity went live
  2026-11-18 (first green deploy 44417680588); chat has served through its binding since the
  2026-11-17 measurement in the master plan.
- `proto.palup.gg`, `test.palup.gg` and the IP-gated apex `palup.gg` answer `/healthz` with
  200 and the pages carry `noindex` (checked 2026-11-19); prod's one trigger is an annotated
  `vYYYY.MM.DD` tag in gitops (ADR-PLT-0028 §7) — no gitops tag exists yet; the prod record
  row came from the open #52 drill (b63037ff, 2026-11-18).
- The four stateful services hold real state: identity on D1 (ADR-PLT-0031), chat on D1 +
  Durable Objects (ADR-PLT-0030), marketplace on Postgres with its settlement steps on D1
  (ADR-PLT-0032; marketplace #24, #25 closed), ledger on Postgres, parked off the live path
  by the settlement plan (ledger #20).
- `gitops/releases/<env>.yaml` carries `desired` and `observed` per component
  (ADR-PLT-0028 §4; `baseline-order.yaml` fixes the promotion order, §6); the nightly drift
  job skips its live compare until the `CLOUDFLARE_DRIFT_TOKEN`/`CLOUDFLARE_ACCOUNT_ID`
  secrets exist (founder gate), so rows lag live — identity's row still reads "never
  deployed" against the 2026-11-18 deploy.
- Every service still pins kernel `v0.2.0` (`tag =` in each `Cargo.toml`); `v0.2.0` is the
  newest kernel tag (checked 2026-11-19).
- Work dispatches through the `headquarters` DEC-0013 issue queue
  (`DEC-0013-issue-queue-master-plan.md`): issues open just-in-time, at most one
  `agent-ready` issue per repository, promoted when the repository's lane frees
  (`gh issue list --label agent-ready` per repository).

## 0. Reading rules

- **Merged** = on `main` today. **Planned** = an issue or a decision, not code. Never describe
  planned work as built, in code, comments, docs, PRs or reports.
- Access is per repository by design (ADR-PLT-0004); you may not see the others. Don't seek
  access or copy their content in. If a task needs them, stop and tell the founder what and why.
- When documents disagree: a DEC beats an ADR on what the DEC owns; a newer ADR beats the one
  it supersedes or amends; ADRs beat `architecture.md`, READMEs, plans and this file; this
  block beats the local section, which may add rules but never relax them. Code that
  contradicts a recorded decision is a bug to report, not a precedent.

## 1. Hard rules — every repository

1. **Issue first.** Implementation starts from an issue in the repository where the code
   lands. No issue: open one (goal, acceptance criteria, the ADR/DEC/spec it serves) or ask.
   Documentation-only changes are exempt, but still go through a PR.
2. **Decisions are files.** Company and cross-repository decisions: `headquarters` DEC-NNNN.
   Technical decisions: `platform` ADR-PLT-NNNN. A new framework, database driver, queue,
   broker, gateway or service is an ADR before it is code. If your change contradicts a
   recorded decision, stop and say so on the issue. Never code around one.
3. **Money.** Every amount is `kernel::money::MinorUnits`: signed i64 minor units, checked
   arithmetic. No floats (clippy `float_arithmetic = "deny"` everywhere), no `unsafe`. The
   ledger is append-only and double-entry, balances are derived, and every money write
   carries an idempotency key. No wallet, stored balance, transferable credit or balance
   gift: the platform never holds buyer money (DEC-0002 #2; DEC-0003 #4, #6). Gifts and tips
   are charge-tied only.
4. **Service boundaries.** One database and one role per stateful service; no service reads
   another's database. Services call each other over HTTP with an idempotency key and a
   timeout; no request chains more than two services. Side effects of a write (email, events)
   go through the transactional outbox in the same transaction, never inline. No broker, no
   gateway at launch. No in-process state a replica switch would lose; the per-replica rate
   limiter is the recorded exception (ADR-PLT-0005).
5. **In-org references.** The only in-org git dependency is `PalupGG/kernel`, pinned by
   tag. The only other allowed in-org reference is the planned reusable CI workflow in the
   org `.github` repository, pinned by SHA (ADR-PLT-0010 #3). No path dependencies. In a
   service tree never write a `github.com/PalupGG/<repo>` URL for any repository but
   kernel, because the boundary gate fails on it. Write `PalupGG/<name>`.
6. **Names and provenance.** Never write the name of a competitor, of a category service we
   studied, or of an analysed artefact: not in files, paths, branch names, commits, code
   comments, issues or PRs. Cite that work as "the dated analysis note outside git". Analysis
   material never enters git and nothing is copied from it; ideas are restated in our own
   words. Vendors and libraries we use are named normally. No script checks this, on purpose:
   you are the check.
7. **Licences.** No AGPL-family code, from anywhere (DEC-0006). Reference projects are ideas
   only; adopting third-party code needs a licence-review DEC first. An unknown or
   incompatible licence is a blocked build. Every dependency enters `THIRD-PARTY.md` in the
   PR that adds it.
8. **No secrets, no personal data** in trees, fixtures, logs, issues, PRs or screenshots.
   Ordinary configuration comes from `<SERVICE>_*` environment variables. Key material is a
   mounted file (`*_FILE`), never an environment variable (ADR-PLT-0010 #2). Test data is
   synthetic.
9. **Documentation repositories hold no code** (`platform`, `headquarters`; DEC-0005): no
   scripts, no CI workflows, nothing that compiles or runs. Markdown, mermaid and JSON-Schema
   goldens only.
10. **Founder-only.** Prepare these but never perform them without an explicit go: merging to
    `main` in any repository, creating or deleting tags, secrets, tokens, accounts, DNS.
    Never fill in, default or invent equity, legal names, contracts or signatures.
11. **History.** Never force-push `main`, rewrite pushed history, or move a tag. Work lands
    through PRs; the server-side record is part of our provenance.

## 2. Workflow: issue → branch → PR → gates → proof → review → merge

1. **Issue.** Read it whole. If acceptance criteria are missing or contradict a decision,
   comment and stop.
2. **Branch** from a fresh `main`: `<type>/<topic>`, type one of `feat fix test docs chore ci
   style` (e.g. `feat/opaque-sessions`). One issue, one branch, one repository.
3. **Commits** say what they do: `type(scope): what it does (closes #N)`. A message that is
   only accurate if it leaves out where an idea came from means the change is wrong.
4. **PR body:** `Closes #N` (or `Refs #N` plus the slice it covers); the gate output (§3)
   and the PR's green CI checks; new `FEATURES.md` and `THIRD-PARTY.md` rows; the ADR, DEC
   or spec it implements.
5. **Gates** green on the exact commit you pushed (§3).
6. **Proof.** A change to what a service answers or what a page shows is run before it is
   reviewed: use what you built the way the person it is for meets it, and post the proof on
   the PR (§3, "Proof of a feature").
7. **Review.** Money (ledger), auth (identity) and security changes get a review pass before
   merge. Land the fixes in the same PR (`fix: review pass — …`).
8. **Merge** with a merge commit (no squash, no rebase), by the founder or with their go. Then
   pull `main` and check that the issue closed.
9. **Cross-repository change.** The contract or decision comes first, as a spec or ADR PR in
   `platform`. Then one issue and PR per repository in dependency order: kernel before
   services, provider before consumer. Nothing lands atomically across repositories, so each
   step must be safe alone.

**Stop and ask** if you would need another repository's code or database; a secret, token or
account; a new dependency class or stack component; a weaker gate or test; or a change to a
recorded decision. Also stop when the issue and a decision disagree.

## 3. Verification

Code repositories (kernel, identity, marketplace, ledger, chat, web): run each gate as its own
command and read its exit status.

```sh
sh scripts/check-boundaries.sh --selftest
sh scripts/check-boundaries.sh            # kernel: --role kernel
cargo fmt --all --check
cargo clippy --all-targets -- -D warnings
cargo test
```

CI is live (measured 2026-11-16): the org reusable workflow gates PRs with `fleet / gates`,
`fleet / gates-postgres`, `image` and `release`, and runs `ci` on main pushes in all six code
repositories (+ `e2e` in ledger and chat, `site` in web, `baseline` in gitops). You still run
the five gates locally as above and paste their output into the PR, and the PR's CI must be
green on the exact commit you push. Documentation repositories and `gitops` have no cargo
gates; there, review is the check (links, numbering, the name rule).

- Never report green from a chained command (`&&`, `;`, a pipe into `tail` or `grep`), from
  memory, or from an earlier commit. Before "done": `git status` is clean, and
  `git rev-parse HEAD` equals the pushed branch (`git ls-remote origin <branch>`).
- A red gate is never "known failing". Never skip, `#[ignore]` or weaken a test, a lint, a
  coverage threshold (it only goes up) or the gate itself. A gate change is its own PR with a
  new selftest case.
- **Tests (ADR-PLT-0007):** one `tests/<feature>.rs` per feature, helpers in
  `tests/common/mod.rs`, table-driven cases named for what they pin. `cargo test` runs
  everything: no hidden runners, no ignored database tests (CI will provide Postgres).
- **`FEATURES.md` is the contract.** A feature without a row is unfinished; a row without a
  test is a lie. Add the row in the same PR.
- **Determinism.** Domain functions take `now` as an argument; only the HTTP edge reads the
  clock. Every wire uses unix seconds; chat's `at_ms` is the one named exception.
- **Bug fixes** start with a failing test, in the same PR.
- **Contracts.** Responses are specified in `platform/docs/specs/` with JSON-Schema goldens. A
  test validating a service against its golden is a feature row (platform #2).
- **Proof of a feature.** Green gates show the code is sound, not that the feature works. After
  the gates, run what you built from your branch and post one PR comment headed
  `## Proof @<head sha>` before you ask for review:
  - one row per acceptance criterion of the issue: what you did (the request, the page, the
    click), what came back (status, the fields that matter, the row it wrote, a screenshot), and
    the file holding the raw output;
  - the raw output, verbatim — in the comment, or in a sealed pack beside it
    (`analysis/proofs/<repo>-<pr>-<head>/`, `SHA256SUMS` written last);
  - a last row, **Not proven yet**, naming each open half and the issue that carries it: a
    deploy, a binding, another repository's slice. An open half with an issue is honest; a silent
    gap is a false claim.

  Synthetic accounts only. A FAIL row stays. The reviewer repeats one row on the reviewed
  commit. A PR that changes what a service answers or what a page shows is not ready for review
  without this comment; docs-only, sync and test-only PRs are exempt. The feature is done when
  the same rows pass on proto (L5, `platform/docs/testing.md`). The gate that merges a lane's PR
  refuses a behaviour-changing PR with no proof comment at its head.

## 4. Kernel and tags

- The kernel holds `kernel::money` and `kernel::telemetry`, nothing else until an ADR adds to
  it. Its dependencies must be on the gate allowlist (`tracing`, `tracing-subscriber`;
  `serde` since v0.2 per ADR-PLT-0012). Extending the allowlist is an ADR plus a gate change
  in the same PR.
- Consumers pin a tag, never a branch or rev:
  `kernel = { git = "https://github.com/PalupGG/kernel", tag = "v0.2.0" }`.
  All five services pin `v0.2.0` (bumped 2026-11-13; check each `Cargo.toml`).
- Tags are immutable; a fix is a new tag. A moved tag desynchronises every `Cargo.lock`.
- Before 1.0, a breaking change takes the next minor (`v0.2.0`) and is announced in `platform`
  (ADR or spec note) before it merges.
- Release: kernel issue → PR → merge → tag (founder) → in each consumer that needs it, an
  issue and PR changing the `tag =` line and `Cargo.lock` together, citing the release.
- CI fetches the kernel with the `FLEET_TOKEN` secret (scoped to reading kernel) through the
  git CLI (`.cargo/config.toml`: `net.git-fetch-with-cli = true`). Never put a token in a URL,
  `Cargo.toml`, git config or a log. A failed fetch is an access problem: report it. Never
  vendor the kernel or swap in a path dependency.
- One toolchain pin (`rust-toolchain.toml`: 1.98.1, edition 2024) in all six code
  repositories. Bump all six together.

## 5. Deployment (`gitops`)

- `PalupGG/gitops` is the only deployment truth (ADR-PLT-0009). Service repositories hold
  no deployment manifests; personal infrastructure repositories hold nothing for this product.
- Layout: `apps/<service>/{base,staging,prod}`, `clusters/` (one ArgoCD app-of-apps root per
  cluster), `secrets/` (SOPS + age).
- Images: `ghcr.io/palupgg/<service>`, tagged `main-<short-sha>` on every merge and
  `vX.Y.Z` on version tags. The `fleet-image` job builds them on main pushes (measured
  2026-11-16; identity #24, marketplace #22, ledger #23, chat #23, web #18).
- Staging (our own cluster, behind a tunnel) follows `main-<sha>` automatically. **Prod (a
  rented EU node behind the edge) moves only through a reviewed `gitops` PR that bumps the
  prod overlay to a `vX.Y.Z` tag.** Never `latest`; never a `main-<sha>` in prod. (Phase 1,
  ADR-PLT-0024: the cluster path is dormant — the only deployed component is web, a Worker;
  proto deploys on merge, test and prod are gated hostnames.)
- ArgoCD pulls. Never `kubectl apply`, `helm install` or push-deploy from CI or an agent.
- Secrets only as SOPS-encrypted files. Never commit decrypted values, `*.dec` files or age
  keys; the founders hold the keys. Key material reaches pods as mounted files.
- Before the first secret enters a cluster: cluster secret encryption on. Before the first
  real signup: backups proven by a restore test. Before the first prod deploy: domain on the
  edge, CI building images, node architecture decided (platform #4).

## 6. Security musts

- Every router wears the baseline from `src/security.rs`: rate limiting (429) and
  `security_layer()` (64 KiB body limit, 413), each mechanism as substituted per runtime
  below. Web adds `security_headers_middleware` (nosniff, referrer policy, strict CSP).
- The shared `src/security.rs` rule is the **recorded per-runtime substitution**: every
  service carries the ADR-PLT-0006 baseline, superseded item by item as its runtime moves,
  each supersession recorded in that file's header and cited to its ADR (identity's rate
  limiter is the Workers Rate Limiting binding — ADR-PLT-0031 #8; the other Worker moves —
  ADR-PLT-0029 rev 2 §3). Byte-identical copies are not required. The fleet check is the
  semantic doc-truth claim C1 (`platform/docs/standards/VERIFY.md`), never a hash comparison.
- **Rate limiting keys on the real client IP** (ADR-PLT-0010 #5): `CF-Connecting-IP` only
  from trusted peers, IPv6 grouped by /64, a bounded bucket map, no User-Agent fallback,
  per-account login backoff. Merged in all five services (identity #9, marketplace #7,
  ledger #7, chat #8; web issue #6 closed).
- Tokens (merged, identity #16/#18): access = EdDSA JWT with `kid` (RFC 7638 thumbprint),
  `typ: at+jwt`, per-environment `iss` and `aud`. Refresh = opaque 256-bit session stored only
  as SHA-256, with family revocation and an absolute cap. The HS256 domain code is replaced:
  don't resurrect it.
- Never log or `Debug`-print passwords, hashes, tokens, emails or keys. Structs holding them
  get a redacted `Debug` (pattern: identity's `Account`, `TokenService`).
- Validate at the edge: bounded lengths, control characters rejected, unknown cursors and ids
  are errors, never defaults.
- Processor webhooks (ledger, M3): verify the signature before any write; idempotent by event id.
- No real signups until the email processor has a signed DPA, a privacy-notice entry, a
  scoped send-only key and send quotas (ADR-PLT-0010 #4).
- CI: third-party actions pinned by full SHA; `permissions: contents: read` unless a job needs
  more (`packages: write` only for the image push).
- A new surface (webhooks, websockets, uploads) updates `platform/docs/security-threat-model.md`
  in the same change set.

## 7. Where decisions and records live

| What | Where |
|---|---|
| Company, money model, payment route, entity, licence and repository policy: anything crossing company and product | `headquarters` `docs/decisions/DEC-NNNN-*.md` |
| Stack, boundaries, security baseline, hosting, CI/CD, test convention | `platform` `docs/adr/ADR-PLT-NNNN-*.md`: supersede or amend, never rewrite an accepted ADR |
| Wire contracts: ids, time, error envelope, endpoint shapes | `platform` `docs/specs/` + `*.schema.json` goldens, before the code |
| Which service owns which data | `platform` `docs/service-architecture-2026-11-06.md` |
| Milestone definitions of done (M0–M6) | `platform` `docs/plans/2026-11-03-build.md` |
| Order of work and timeline (R0–R7) | `platform` `docs/roadmap.md` |
| Architecture map | `platform` `docs/architecture.md` |
| Security posture, known limitations | `platform` `docs/security-threat-model.md` |
| Repository layout: docs folders, code folders, root files | `platform` ADR-PLT-0013; every repository's `docs/README.md` is its own index |
| One unit of work, its acceptance criteria | an issue in the repository where the code lands |
| What runs where, which version is in prod | `PalupGG/gitops` |
| What a repository's tests cover | its `FEATURES.md` |
| Dependencies and licences | its `THIRD-PARTY.md` |
| Provenance; name clearance | `headquarters` `PROVENANCE.md`; `brand/name-clearance.md` |
| Reviews, reverse-engineering notes, plans that embed code | outside git, never committed |
| Equity, legal names, contracts, signatures | the founders, never an agent |

Cited most:

- DEC-0002: never hold buyer money. Formally still *proposed*; treat it as binding.
- DEC-0003: one account, two capabilities; the self-dealing guard; charge-tied gifts.
- DEC-0005: documentation repositories hold no code.
- DEC-0006: reference projects are ideas only; voice messages in DMs only.
- ADR-PLT-0002: Rust, five services, one database each. ADR-PLT-0004: repository per service,
  kernel by tag. ADR-PLT-0006, 0010: security. ADR-PLT-0007: tests. ADR-PLT-0009: CI/CD, gitops.

Known stale text (2026-11-08; fix it, don't follow it):

- `architecture.md` §6 and ADR-PLT-0005 #2 put manifests in the infrastructure repository;
  ADR-PLT-0009 superseded that.
- "Secrets via environment only" (ADR-PLT-0006 #5, ADR-PLT-0008 #6) is amended for key
  material by ADR-PLT-0010 #2.
- ADR-PLT-0008 names an ARM node; the node architecture is still open (platform #4).

## 8. The repositories

Services bind `127.0.0.1` unless `<SERVICE>_BIND` says otherwise, and listen on
`<SERVICE>_PORT`. Ingress routes `/api/<service>` to each service and `/` to web. Every service
answers `GET /healthz` with `ok`; the four stateful services own their Postgres databases
(measured 2026-11-16). Issue numbers are anchors as of 2026-11-16; the issue list is the live
truth.

### kernel — the shared crate
- **Merged:** `MinorUnits` (signed i64; checked add, sub and mul; two-decimal display; no
  currency field; no split or percent helpers). `telemetry::init` (idempotent; JSON since
  v0.2.0). The error envelope (ADR-PLT-0012). Tags `v0.1.0`, `v0.2.0` (2026-11-12).
- **Open:** none.
- **Must:** gate with `--role kernel`; keep dependencies on the allowlist (`tracing`,
  `tracing-subscriber`, `serde`); release by tag (§4).
- **Never:** product logic, HTTP, storage, I/O beyond telemetry; git or path dependencies;
  split or rounding helpers before the M3 rounding spec.

### identity — accounts and access · port 8081 · db `identity`
- **Owns:** accounts, 18+ attestation, email verification, sessions and access tokens, bans,
  the provider capability on the single account (DEC-0003 #2).
- **Merged** (M1 complete, ADR-PLT-0010 order; Postgres since #18):
  - Signup validation: attestation required, password at least 8 characters, email
    normalisation shared with login.
  - Argon2 hashing (pinned parameters); the account record with `attested_at`, `banned`,
    `provider_capability`.
  - Opaque sessions, EdDSA access tokens, a clock module (#16); the auth HTTP routes per the
    web contract, signup as one transaction (#18); one execution per Idempotency-Key on
    state-changing routes (#22); `/metrics` and the container image (#24).
- **Open:** none.
- **Must:** treat the access-token TTL (15 minutes) as every verifier's ban latency and record
  changes in the platform spec; mint account ids as opaque strings (`acc_<8 hex>`).
- **Never:** store or log plaintext passwords, tokens or emails; issue an access token before
  the email is verified; let a duplicate signup replace a pending account's password; make
  refresh tokens JWTs.

### marketplace — catalogue and bookings · port 8082 · db `marketplace`
- **Owns:** catalogue; provider profiles and applications (verified through a state machine,
  never approved instantly); services and pricing; slot calendars; orders; reviews; search;
  follows.
- **Merged** (M2 complete; Postgres since #16):
  - Offer validation: price above 0, bundle of at least 2.
  - `quote()`, the single pricing truth: quantity 1–8, first-session-free and bundle
    promotions with every applied one reported, checked arithmetic.
  - The `Order` aggregate: distinct parties, seven legal transitions derived from the actor,
    an exhaustive matrix test. Owned, idempotent slot holds.
  - Dev database and migrations (#16); catalogue read side — browse, categories, games,
    profile, search (#18); quote and orders per the booking web contract (#20); container
    image (#22).
- **Open:** none.
- **Must:** price only through `quote()`; derive roles from the order's own parties; at M2,
  mirror the self-dealing and slot guards as database constraints; confirm an order only
  against a non-null ledger reference (M3). Account ids are strings on the wire (booking
  contract, #20); the internal `AccountId(u64)` stays domain-side, off the wire.
- **Never:** money math outside `kernel::money`; a transition outside the matrix; buyer equal
  to provider; charges or refunds (ledger owns them).

### ledger — the money · port 8083 · db `ledger`
- **Owns:** the append-only double-entry ledger, Stripe Connect destination charges, verified
  webhooks, refunds, payout lanes and their per-provider configuration, nightly
  reconciliation, the outbox. The critical path (roadmap R4).
- **Merged** (M3 in progress; Postgres since #16, append-only enforced by grants):
  - Balanced postings: at least 2 distinct accounts, no zero legs, sums in i128.
  - Idempotency by key plus payload digest: a replay returns the original id, a divergence is
    a conflict. Rejections commit nothing; ids are ledger-assigned.
  - Facts always post; commands are floor-checked on the account's natural side.
  - Derived balances and a trial balance; one currency (CHF).
  - A processor-side chart (clearing asset, provider payable, fee revenue, expense) with no
    buyer balance.
  - HTTP money routes per the ledger-web spec (E0.2, #24); verified webhooks and nightly
    reconciliation first cut (E0.4, #25); container image (#23).
- **Open:** #20 E0.3 — Stripe Connect destination charges (test mode) behind the
  payout-channel interface.
- **Must:** key, digest and reference (order or processor event id) every posting; reverse
  with a new posting; prove sum-zero, the trial balance, replay and divergence in tests for
  every change.
- **Never:** update or delete an entry; accept an unbalanced posting; floor-reject a processor
  fact; hold buyer money in any form.

### chat — DM threads · port 8084 · db `chat`
- **Owns:** buyer–provider DM threads, history, unread counts, websocket delivery,
  notifications, moderation hooks, voice messages in DMs.
- **Merged** (HTTP live since #21; Postgres since #17):
  - Two distinct participants per thread.
  - Messages trimmed, non-empty, at most 400 characters, no control characters.
  - Reads guarded exactly like writes.
  - History oldest-first with message-id cursors (an unknown cursor is an error); pages of
    1–100 with `has_more`.
  - Unread counts skip your own messages; `at_ms` is in milliseconds.
  - Thread persistence (#17); HTTP routes per the web contract with v1 polling (#21);
    container image (#23). web proxies `/api/chat` to the chat Worker via a service binding
    (web #92).
- **Open:** #25 W3 — chat Worker: Durable Object per thread, D1 index, WebSocket, demo
  guard · #6 voice messages in DMs: presigned uploads to object storage (R2), references
  only, duration and size caps, the moderation queue (M4, DEC-0006).
- **Must:** guard every read path (websocket included) like writes; page, never truncate
  silently. Ids are opaque strings on the wire (`acc_/thr_/msg_`, `src/ids.rs`).
- **Never:** voice in community rooms; audio bytes in the service; code from AGPL-family chat
  projects; live voice or an SFU (that needs its own decision).

### web — the front end · port 8080 · stateless
- **Owns:** server-rendered pages: askama templates plus htmx 4 (ADR-PLT-0016); in phase 1
  the same router is exported to static pages served by a Cloudflare Worker (ADR-PLT-0024).
  No data.
- **Merged:** the static export of the real router (#30, #54); preview surfaces on the demo
  dataset (#54–#88); chat UI and the `/api/chat` proxy via a service binding (#92);
  workers_dev and preview URLs off — gated hostnames only (#90); `noindex` and route map
  audit (#89); `/healthz`, the baseline plus security headers. Deployed: `proto.palup.gg`,
  `test.palup.gg` and the IP-gated prod apex `palup.gg` (each answered 200 on 2026-11-16).
- **Open:** #93 visual parity with the reference design. Name clearance is a founder gate
  before any public, indexable page.
- **Must:** keep the working-name marker and `noindex` until clearance; take every datum from
  a service over HTTP; keep the CSP strict.
- **Never:** a database or `*_DATABASE_URL`; pricing, authorisation or money logic; a client
  framework at launch; inline scripts or htmx's eval features (`hx-on:`, `js:` values, trigger
  filters); a CSP exception without an ADR; candidate brand names anywhere.

### gitops — the deployment truth
- **Is:** ArgoCD applications, overlays and encrypted secrets for staging and prod (§5).
- **State** (measured 2026-11-16): edge Terraform — zone deny-by-default IP allowlist (#30),
  tunnel ingress and the API hostname (E1.6, #38), R2 attachment buckets (#39), prod apex
  `palup.gg` as an IP-gated Worker custom domain (#26); the environment record and the
  `baseline` workflow (#41, green run 43943569135); chat row and D1 names (#43). The cluster
  path is dormant in phase 1 (ADR-PLT-0024); web deploys as a Worker.
- **Must:** change prod only by a reviewed tag bump; keep every secret encrypted.
- **Never:** plaintext secrets or age keys; cluster infrastructure (it lives outside this
  org); push-deploy scripts.

### platform — the technical record
- **Is:** ADR-PLT-0001 to 0013, the architecture map, the roadmap, the build plan, the
  data-ownership note, contract specs and goldens, the threat model, diagrams. Documentation
  only.
- **Open:** #2 contract specs and goldens · #3 infrastructure runbook · #4 node architecture
  (x86 or ARM).
- **Must:** record a decision before the code that needs it; supersede or amend with a new
  ADR; keep `architecture.md` and `roadmap.md` current when a decision changes; cite DECs,
  never restate them.
- **Never:** code, scripts or CI of any kind.

### headquarters — the company record
- **Is:** DEC-NNNN decisions, strategy, finance, brand and name clearance, provenance.
  Isolated on purpose; most agents never see it.
- **Must:** hold every decision that crosses company and product, with the alternatives
  rejected.
- **Never:** code; executed contracts, invoices, identity or bank documents, personal data,
  credentials; technical implementation detail; competitor names.

## 9. What stays local

The section below `fleet:end` holds only what is true of this repository alone: commands or
prerequisites that differ from §3, file formats and templates, and temporary exceptions with
their issue number. It never repeats this block. Also local, never copied in here:

| Repository | Stays local |
|---|---|
| every repository | `docs/README.md`, its own document index (ADR-PLT-0013): local documents only, fleet-wide records stay in `platform` |
| every code repository | `FEATURES.md`, `THIRD-PARTY.md`, `README.md` (port, environment names), `scripts/check-boundaries.sh` (identical in all six; change together), `rust-toolchain.toml` |
| kernel | prerequisites (`rustup`, `jq`), the release checklist |
| identity, marketplace, ledger, chat, web | nothing beyond the files above |
| gitops | overlay and secrets conventions, the promotion-PR template |
| platform | ADR and spec templates (`docs/templates/`), numbering, supersession |
| headquarters | the DEC template, the folder map, what never lives there |

To change this block, open a PR in `PalupGG/platform`; it reaches the other repositories
as sync PRs. Never edit it here.
<!-- fleet:end -->

## Local to this repository

- Local rules: none recorded yet. This repository holds the reusable workflows and the runner setup (ADR-PLT-0009).
