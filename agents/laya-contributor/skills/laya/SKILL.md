---
name: laya
description: Use when working on the Laya codebase (github.com/aayushch/laya) — a local-first AI notification command centre (Tauri + Svelte + Python engine). Covers the pipeline and API architecture that matters when changing it, the repository's contribution conventions, and the verified defects and open issues so work starts from evidence rather than from the issue text.
---

# Laya

Local-first desktop app: **Tauri shell + SvelteKit UI + Python FastAPI engine**,
with n8n for event ingestion and outbound action execution. Apache-2.0. One
maintainer (`aayushch`); external contributions are welcome and the contributor
guide asks for fork → branch → PR.

```
Event sources → n8n (:45678) → Engine (:8420) → UI (Tauri + Svelte, :5173)
                                     ↓
                           SQLite + ChromaDB (~/.laya/data)
```

## Before you touch anything

1. **Read `CLAUDE.md` at the repo root.** It is the real architecture document.
2. **The engine venv is not committed and `ui/node_modules` may be empty.**
   `scripts/setup-dev.sh` creates them. Beware that `requirements.txt` contains
   **no test runner**: `pytest` is imported by 77 test files and `pytest-asyncio`
   by 7 (the async fixtures in `tests/conftest.py` need the latter), and neither
   is in that file — so a venv built from it cannot run the suite at all, and
   `CONTRIBUTING.md`'s documented `pytest` step fails with *command not found*.
   Install both by hand, or use the prepared `fix/dev-requirements` branch, which
   adds `engine/requirements-dev.txt`. They are absent from `requirements.txt`
   deliberately: `bundle-engine.sh` copies that file into the shipped app.
3. **Check before you run the test suite.** On a tree without the test-isolation
   fix, `pytest` rewrites the real `~/.laya/settings.json` and **deletes the MCP
   bearer token** from the OS keychain. Do not rely on remembering that — run the
   check, which exits non-zero when the tree is unsafe:

   ```
   python3 "${DSH_HOME:-$HOME/.dsh}/.agent-presets/laya-contributor/tools/check_laya_home.py" \
       --repo /path/to/laya
   ```

   It reports `SAFE`, `UNSAFE` (exit 1) or `UNKNOWN`, and refuses to guess. See
   the defect below for why this is a script rather than a sentence: the rule was
   written down first and ignored twice anyway.

4. **Do not trust this document's numbers from memory — re-derive them.** Every
   checkable claim below (the paths, the 25/21 counts, that every egress adapter
   module is actually in `_REGISTRY`, whether each "verified defect" is *still*
   unfixed, whether each prepared branch still exists and is still unpushed, and
   the issue states) is asserted by a script:

   ```
   python3 "${DSH_HOME:-$HOME/.dsh}/.agent-presets/laya-contributor/tools/verify_claims.py" \
       --repo /path/to/laya --work-dir /path/to/clones
   ```

   It exits 1 when this skill contradicts the repository, and reports `UNKNOWN`
   rather than guessing when it cannot check something. This is not ceremony: two
   claims in this file were already wrong when the script was written — it named
   engine/laya/api/main.py (deliberately unbackticked: every backticked
   repo-relative path in this file is treated as a claim, so quote a wrong path
   plainly rather than making it look like one), a path that has never existed in
   any commit, and it told the reader to push the chat branch from a clone that
   cannot reach GitHub. A defect claim passing means the defect is *still there*;
   when the maintainer fixes one, the script goes red on purpose so this file gets
   corrected.

   Its companion, `tools/audit_prepared_work.py`, checks the **other** document:
   `PREPARED-WORK-INDEX.md`. That one verifies the documented branches sit at the
   documented commits, that they are pairwise file-disjoint, that upstream `main`
   has not moved, and — the part that matters before you push — whether each
   clone's fork remote is actually wired. Run both; they audit different claims
   and neither is a substitute for the other.

## Architecture worth knowing

**Pipeline** (`engine/laya/pipeline/`) — `queue.py` orchestrates
`ingest → space_resolution → rules → router → workers → stager → emit`, with
post-emit steps triggered by `emit.py`: `entity_resolution`, `context_grouping`,
`trace` (ChromaDB), `tags`, `group_summary`, `omni`.

**API** — the app entrypoint is `engine/laya/main.py`, **not** under `api/`. It
holds **25** `include_router` calls, drawn from the 21 `*_api.py` modules in
`engine/laya/api/` (`CLAUDE.md` says "~27"; counted, it is 25). The large
card surface is split into `cards_common` (shared row→model helpers) plus route
modules, aggregated in place via `include_router` into one `cards_router`. **Route
order matters** — the split modules are included in place precisely so it holds:
`_feed_router`, which carries the flat list and `/cards/grouped`, is included
before `_lifecycle_router`, which carries `/cards/{card_id}` detail. Annotate the
ordering reason when you add a route module; a wrong order silently shadows the
literal path with the parameterised one.

**Egress** (`engine/laya/egress/`) — each platform owns its whole contract
(capabilities, draft schema, terminal events, normalize/validate) as a `Platform`
subclass in `platforms/<name>.py`, exposing a module-level `PLATFORM` singleton;
`registry.py` (~460 lines, mostly one-line delegations) is a facade over them.

**`CLAUDE.md` says adding a platform "is one file, not edits in many tables".
The adapter is genuinely self-contained, but the file is not the only touch
point** — the platform resolves to nothing until it is registered. The
authoritative instructions are in `platforms/__init__.py`'s own docstring:
implement the interface, expose `PLATFORM`, register it in `_REGISTRY` (and
`_DISPATCH` if it enriches) — which also means adding it to that module's import
list and `__all__` — then add a workflow-name keyword in `_PLATFORM_KEYWORDS`
(`registry.py`) so ingestion resolves to it. For its own mark and colour the UI
needs entries in `PlatformIcon.svelte` and `cardVisuals.ts`, though both support
aliasing a parent (as `bitbucket_server` does). Prefer the code's docstrings over
`CLAUDE.md`'s summaries when they disagree.

**Agents** (`engine/laya/agents/`) — CLI coding-agent adapters behind the
`CodingAgent` / `BaseCodingAgent` protocol in `base.py`. `claude_code.py` is the
richest template. Agent types are registered in **four** places: the `AgentType`
enum (`models/workspace.py`), `_AGENT_BINARIES` + `detect_agent_paths()` +
`get_agent_binary()` (`config.py`), `session_manager._create_agent`, and the
settings UI's `CODING_AGENTS` list (`ui/src/lib/config.ts`). Missing any one
leaves the feature half-wired.

**LLM** (`engine/laya/llm/`) — LiteLLM wrapper in `client.py`. Prompts live in
`prompts/`, one module per role. **Gate conditional content by platform/intent**;
token cost matters on small local windows.

**MCP** (`engine/laya/mcp/`) — HTTP/SSE MCP server exposing Laya's tools,
scope-filtered by user settings and space-aware via a context var.

## Conventions that will get a PR reviewed well or badly

- **Leave a comment on every workaround or defensive fix, saying why it exists
  and what breaks without it.** The repository is explicit about this and the
  existing code follows it.
- **Svelte 5 runes only** (`$state`, `$derived`, `$effect`, `$props`) — never `$:`.
- **Async everywhere in the engine.** One shared aiosqlite connection; for
  multi-statement invariants use `db/sqlite.transaction()`, not per-request
  isolation (it is deliberately *not* applied to the hot `_persist_card` path).
- **Migrations are numbered** files in `db/migrations/`; take the next number.
- Bump `meta.laya_version` in a bundled n8n workflow whenever you change one.

## Verified defects — reproduce before you rely on them

These were found by running the code, not by reading issues. Each is a real
finding with a reproduction.

### 1. The engine cannot start on a fresh install (`mcp` 2.x) — FIXED UPSTREAM

**Closed. Do not prepare work for this.** On 2026-09-24 the maintainer landed
`c39c79f` — *"#16: Pin mcp version to <2 - 2.x mcp version renamed McpError to
MCPError"* — so `engine/requirements.txt` now reads `mcp>=1.0.0,<2`. #16 is the
tracker entry; #15 was closed as its duplicate. The prepared branch for it
(`fix/pin-mcp-below-2`) is now both obsolete and in conflict with `main`; it is
retired rather than submittable.

It stays here because the *reasoning* generalises. mcp 2.0 removed
`Server.list_tools`, `call_tool`, `list_resources` and `read_resource` — the four
decorators `build_mcp_server()` is built from — and renamed `McpError` to
`MCPError`. Three users confirmed the cause on #16 across two platforms, and one
applied `,<2` by hand and reported it working.

The reusable part is the trap. The reported symptom is only the *first* failure:
`laya/api/mcp_api.py` imports `http_server.py`, so the `ImportError` takes the
engine down before it can log anything, and the UI reports "engine started but is
not responding". **Working the import around does not fix it** — the module then
loads and dies at `build_mcp_server()` with `AttributeError: 'Server' object has
no attribute 'list_tools'`. An import shim looks like a fix and is not one; only
the bound works. Verify a dependency fix by running the code, never by making the
import succeed.

### 2. The Cursor adapter (#12) — FIXED UPSTREAM

**Closed. Do not prepare work for this either.** On 2026-09-25 the maintainer landed
`e87abe4` — *"#12: Added phase 1 support for cursor agent"* — 27 files, +1057/−53, which
created `engine/laya/agents/cursor_cli.py` and `engine/tests/test_cursor_cli_adapter.py`:
the same two files the prepared branch `feat/cursor-cli-adapter` adds. Issue #12 is
CLOSED/COMPLETED. That branch is now **both a duplicate and in conflict** with upstream
(`merge-tree` reports 9 conflicting files), so it is retired, not submittable.

Two lessons, and the second is the one that cost time. The first is the same as #16's:
a first-time contributor offering work the maintainer merged hours earlier is worse than
offering nothing. The second is that this was *detectable in advance and was detected* —
`verify_claims.py` watches the issue states the skill depends on and went red the moment
#12 closed, and `submit_prepared_work.py` refuses the branch mechanically because it no
longer merges. The gap that remains is the one no tool closes: **a clean merge proves the
text combines, not that upstream has not already solved the problem. Re-read the tracker
before submitting, every time.** Note also that upstream's implementation is "phase 1":
the mode list and the UI wiring may still be incomplete, so a *different* PR here is not
impossible — but it would have to be written against `e87abe4`, not against the retired
branch.

### 3. Running `pytest` deletes the developer's MCP token

`engine/tests/test_mcp_http.py::restore_settings` restores only the `mcp` key and
then calls `delete_mcp_token()`. `config.py` resolves `LAYA_HOME` from
`Path.home()` at **import** time, so a plain `pytest` rewrites the real
`~/.laya/settings.json` and removes the bearer token from the keychain. Measured:
one test file moved `~/.laya/settings.json` from `12:01:13` to `12:36:05`.

The fix is to redirect `HOME`/`USERPROFILE` before the first `laya` import — it
must be before, because modules do `from laya.config import LAYA_CONFIG_FILE` and
bind the real path. **Use a fixed directory, never `tempfile.mkdtemp()`**: a fresh
directory per run relocates ChromaDB's model cache and re-downloads the embedding
model, taking the suite from 43 s to 241 s. Until this lands, run the engine tests
with `HOME` pointed at a scratch directory.

### 4. The REST API is unauthenticated, including the token endpoint

The engine binds `127.0.0.1:8420` and protects itself only with
`TrustedHostMiddleware` plus a CORS allowlist. Any local process can call
`/settings` (3,241 bytes returned), `/cards`, `/spaces`, `/events`, and — the
sharp part — **`/mcp/token/reveal`, which returns the live MCP bearer token with
no `Authorization` header.** So it is not merely an open read API; it hands over
the credential for the authenticated path.

`main.py` already recognises the DNS-rebinding half and closes it with
`TrustedHostMiddleware`; that does not close the local-process half, because a
process already on the machine sends `Host: 127.0.0.1` and is allowed through by
design.

**There is no route-local fix.** `ui/src/lib/api/engine.ts` calls
`revealMcpToken`, and no REST call in `ui/src` sets an `Authorization` header — so
requiring a credential there is a bootstrap problem. Any fix has the same shape:
the Tauri shell (which can read the keychain) injects a credential into the
webview, and the engine requires it. The engine half is the small part. Treat the
design as the maintainer's call rather than opening a patch.

The handler's own docstring records the position: *"Return the full current token.
Loopback-trusted; same boundary as the existing `/settings/api-key/*` endpoints."*
So loopback trust is a stated design choice, not an oversight.

**Update 2026-09-24:** the maintainer has since said a PR is welcome and offered to
fix it himself otherwise. A reply is prepared at
`/home/logic/Work/laya-issue-13-reply.md` and re-verified against the current base;
it takes the note he offered, because the fix is a cross-stack design decision rather
than a route-local patch. Do not open a PR uninvited — but do not treat this as
closed either: he is waiting on a reply.

## Working discipline this repository expects

The maintainer's own standards, visible in the code and in the sibling
`reputation` project, are strict about evidence. Match them:

- **Reproduce before you claim.** A traceback, a measured time, a compared
  checksum — not a reading of the source.
- **Prove a guard fires.** A check that cannot fail is worse than no check; wire
  a self-test or a mutation and show it going red.
- **Report the unflattering result next to the flattering one.**
- **Read the committed number before writing the sentence about it.**

## Work that is already prepared — do not redo it

**Eleven branches** are built, verified on their own trees, and **deliberately not
pushed** (confirmed `local-only` against the remote) — plus one issue comment that is not
a patch. Two more were retired because the maintainer landed the same work: `fix/pin-mcp-below-2`
(#16, 2026-09-24) and `feat/cursor-cli-adapter` (#12, 2026-09-25). Do not submit either;
both are kept on disk and both now conflict with `main`. Before starting anything, read
`/home/logic/Work/PREPARED-WORK-INDEX.md` — it carries the exact commits, the submission
commands, and a verification log.

| branch | where | what it fixes |
|---|---|---|
| `fix/tests-isolate-laya-home` | `laya-inspect` | `pytest` deletes the MCP token |
| `fix/dev-requirements` | `laya-inspect` | the venv `setup-dev.sh` builds has no `pytest` |
| `feat/full-page-coding-chat` | **`laya-chat`** | full-page coding chat + an opt-in `ChatRequest.focus` |
| `fix/setup-progress-labels` | `laya-inspect` | parallel setup downloads render as one unlabelled counter (#7) |
| `fix/omni-attention-wipe-guard` | `laya-inspect` | a resynthesis that empties "Needs Attention" keeps its items (#10) |
| `feat/omni-open-items-input` | `laya-inspect` | the resynthesis is not offered the live high-priority subjects (#10) |
| `fix/omni-unitemised-cards` | `laya-inspect` | cards a resynthesis does not itemise are lost later (#10) |
| `fix/github-pr-comment-entity-key` | `laya-inspect` | a PR comment's entity key depends on the Pulls window (#10) |
| `test/auto-resolve-terminal-siblings` | `laya-inspect` | terminal-event sibling resolution had no coverage (#10) |
| `feat/persist-tool-call-references` | `laya-inspect` | tool call references are not persisted with a message (#6) |
| `fix/engine-cross-site-origin-guard` | `laya-inspect` | any local page can drive the REST API and read the UI broadcast (#13) |

**PR ordering is not cosmetic**: land `fix/tests-isolate-laya-home` before any
branch whose tests get run, or running `pytest` deletes the maintainer's MCP
token. `fix/setup-progress-labels` is the loosest: it touches only `ui/src-tauri/**`
and runs no Python tests, so it can land at any point.

**The base has moved twice while this work sat ready** (`c39c79f`, then `e87abe4`), and
each move retired a branch. Before submitting, re-read the tracker: a clean merge proves
the text combines, not that upstream has not already solved the problem. The audit
announces when `main` has moved and `verify_claims.py` goes red when an issue we depend on
closes, but neither can tell you an issue was fixed a different way.

The mcp bound that used to be half of this story is now in `main` (see defect 1),
so `fix/dev-requirements` stands alone: a venv built from `requirements.txt` today
still has no `pytest`, and that is the only remaining reason a fresh clone cannot
run the suite.

Submitting is one command, `tools/submit_prepared_work.py`. It is a dry
run unless given `--execute`, wires the fork before pushing, and verifies by URL
afterwards that the branch did not land on the maintainer's repository. **Run it
without `--execute`** — see the boundary below.

Every tool in `tools/` accepts `--self-test`, which checks the tool itself without
touching the network or the repository, and `tools/mutation_sweep.py` disables one guard at
a time in each and requires the self-test to notice — it found ten guards that were not
covered at all. Run them before trusting any of them; each one exists because a check that
could not fail had already gone unnoticed once.

To see the state of everything at once, run `tools/handoff_status.py`. It reports
what is committed but unpushed (per repository, from git), which pull requests are
prepared but unsubmitted, what is waiting on the user (open+high and blocked,
read from the task ledger), and whether the other four tools pass. Start there
after a gap rather than reconstructing the situation from conversation history:
everything it prints is derived, so a pushed commit simply stops appearing.

The chat branch lives in a **separate clone**, `/home/logic/Work/laya-chat` — but
**that clone cannot currently reach GitHub**: its `origin` is the local path
`/home/logic/Work/laya-inspect`, so `git push origin` there writes into the other
working tree. Wire the fork first (`gh repo fork aayushch/laya --clone=false
--remote`, run from `laya-chat`) and confirm with `git remote -v` before pushing.
The same trap applies to `laya-inspect`, whose `origin` is `aayushch/laya`
itself — a plain `gh repo fork … --clone=false` adds no remote, so pushing
without `--remote` targets the maintainer's repository. Full commands are in the
prepared-work index.

Issue #13 has a reproduction in `/home/logic/Work/laya-issue-13-repro.md` and is
**a comment, not a patch** — there is no route-local fix, so do not open a PR for
it without the maintainer's direction.

## Never

- **Push, comment, or open a PR under the user's name.** Prepare the branch and
  the PR text; the user submits. This extends to
  `tools/submit_prepared_work.py`: run it as a dry run only. `--execute` forks,
  pushes and opens pull requests under the user's GitHub account, which is the
  user's action to take, not yours — even when they have asked for the work to
  be finished. Hand them the command instead.
- **Commit anything to `job-kit`** or another deliberately unpublished directory.
- **Widen a dependency bound to make a test pass** without establishing that the
  new version actually works.
