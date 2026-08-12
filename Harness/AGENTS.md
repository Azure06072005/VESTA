# Agent Instructions — VESTA
(Vietnamese Equity Sentiment-Triggered Agent)

This file is the routing manual. Keep it under 200 lines (Principle 4).
Detailed rules live in `docs/*.md` — read those only when the task needs them.

## Agent roles on this project (read this before anything else)

- **Gemini (chat)** — primary AI research (data sourcing, statistical
  design, interpreting results). Not the primary code-writer.
- **Gemini Antigravity** — primary AI coding agent. Implements
  `feature_list.json` features, writes tests, follows the workflow below.
  Logs sessions in `gemini-progress.md`.
- **Claude** — harness/documentation upkeep, code review, cross-checks
  against `conventions.md` / `DECISIONS.md`. Logs sessions in
  `claude-progress.md`.
- Whichever agent is running: read **both** progress files, not just the
  one matching your identity — they describe the same repo.

## Before Starting Any Work (Session Lifecycle — Principle 6)

1. Run `./init.sh` — install deps, run tests, confirm environment is healthy.
   Do NOT write feature code until init.sh passes clean.
2. Read `claude-progress.md` AND `gemini-progress.md` — what happened last
   session (by any agent), what's blocked, what's next.
3. Read `feature_list.json` — what's done, active, blocked, not started.
4. Read `DECISIONS.md` — don't reverse a deliberate prior choice without a
   new, stated reason (e.g. PhoBERT-base vs -large, execution-layer block).
5. Read `architecture.md`'s folder tree before creating any new file, so it
   lands in the right module.
6. Run `git log --oneline -10` — see recent changes.

If you cannot answer "what is this system / how do I run it / how do I
verify it / what's the current progress" after steps 1-6, STOP and say so.
Don't guess (Principle 3).

## Hard Constraints (non-negotiable)

- Work on exactly ONE feature at a time (WIP=1, Principle 7). Do not "also
  fix" or "also refactor" anything outside the current feature's scope.
- Never mark a feature `passing` without a passing verification command.
  "Looks correct" is not evidence (Principle 9).
- Only full-pipeline verification counts: tests + lint + type-check + build
  + smoke run (see `verification.md`). A single passing unit test is not
  "done" (Principle 10).
- `passing` state is irreversible — once verified, don't silently downgrade
  it; if it breaks later, that's a regression, log it as one.
- The `F9xx` execution tier stays `blocked` until `F901` (broker compliance
  confirmation) is `passing`. No agent may start implementing `execution/`
  code before then — see DECISIONS.md.
- Every session must end in a clean, resumable state (Principle 12) — see
  checklist below.
- If something is ambiguous or you're inventing scope that wasn't asked
  for, stop and say so in your progress file rather than guessing.

## Session Workflow

```
SELECT   → pick exactly one feature from feature_list.json (state: not_started or active),
           respecting the F0xx → F1xx → F2xx → F3xx → F4xx dependency order
EXECUTE  → implement → run full verification → fix → re-run until it passes
RECORD   → update feature_list.json state + evidence
WRAP UP  → update your progress file, run Session Exit Checklist, commit, stop
```

## Session Exit Checklist (must pass before ending a session)

- [ ] Build passes
- [ ] All tests pass
- [ ] Lint + type-check clean
- [ ] `feature_list.json` and your progress file updated
- [ ] No debug code left behind (console.log/print/debugger/TODO markers
      you added)
- [ ] Standard startup command still works
- [ ] Working tree is committed or explicitly left dirty with a note why

## Where to look for more detail

- `architecture.md` — system structure, full folder tree with per-file
  descriptions, agent-role notes (read once per session)
- `verification.md` — exact install/test/lint/type-check/build/smoke
  commands for this repo, plus GPU VRAM budget checks
- `conventions.md` — code style, naming, patterns specific to this project,
  each with a source/applicability/expiry
- `PROJECT_INSTRUCTIONS.md` — the coding-discipline + finance-domain
  guardrails behind this harness (compliance gate, signal-before-
  infrastructure, sourced-numbers rule)
- Add topic docs here as the project grows. Don't grow this file past
  ~200 lines — split into `docs/` instead.

## When You're Stuck

Attribute the failure to one of five layers before asking the human for
help: task specification, context provision, execution environment,
verification feedback, or state management. Say which layer, then ask your
question.
