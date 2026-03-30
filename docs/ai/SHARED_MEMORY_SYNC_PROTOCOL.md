# Shared Memory Sync Protocol

This document explains how Codex on two machines can share project memory reliably.

## Core Answer

Codex instances do not share hidden memory automatically.

Shared memory happens only when important context is written into versioned repository files and synchronized between machines.

## What Counts As Shared Memory

The only durable shared memory is git-tracked project memory.

Use these files as the shared layer:

- `docs/ai/CTO_COCKPIT.md`
- `docs/ai/CTO_CONTEXT.md`
- `docs/ai/PROJECT_MEMORY.md`
- `docs/ai/AGENT_DELEGATION_PROTOCOL.md`
- `docs/ai/VISION_EXTRACTION_GUIDE.md`
- `docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md`
- `decision-register/`
- `ai-ledger/`

## Important Clarification

If a document is not committed and pushed, the other machine does not have it.

So yes:

- if you want shared memory, these documentation files should be committed like code
- they are not optional extras
- they are part of the operating system of the project

## Recommended Sync Model

Use a dedicated memory layer that both machines always pull.

Minimum process:

1. Update shared docs on the machine where the new decision was made
2. Commit those docs
3. Push to the active coordination branch
4. Pull on the other machine before starting major work
5. Read `docs/ai/README.md` before coding

Recommended branch policy:

- commit memory changes on the active track branch when tightly coupled to code
- otherwise use a doc-only branch such as `coordination/docs-sync`
- merge important memory updates early so both machines converge quickly

## What Should Be Committed

Commit these when they change:

- strategic priorities
- architecture decisions
- track coordination rules
- platform/product boundary decisions
- AI operating rules
- durable findings from Web discussions

Do not wait for a code feature to finish before syncing these.

## Suggested Habit

Treat memory updates like schema migrations:

- if the project model changed, the memory layer must change too
- stale memory is a production risk for AI-driven development

## Practical Workflow

Before a session on either machine:

1. `git pull`
2. read `docs/ai/README.md`
3. review changed memory docs
4. begin implementation

After a meaningful session:

1. update docs if a durable decision emerged
2. add ledger entry if needed
3. commit docs and code together when they belong together
4. if docs changed independently, commit docs alone

## Good Commit Strategy

Use separate commits when helpful:

- one commit for shared memory updates
- one commit for implementation

This makes cross-machine sync easier, not harder.

Preferred commit prefixes:

- `docs:` for memory, governance, and roadmap alignment
- `feat:` or `fix:` for implementation
- `chore:` for tooling and maintenance

## What If You Do Not Want To Push All Docs To `main`

That is fine.

You still need them in git, but they do not have to land in `main` immediately.

Recommended options:

- keep them on `product-dev` and `platform-dev` and merge regularly
- keep them on a shared coordination branch and merge from there
- merge doc-only commits earlier than feature commits when they carry important decisions

## Non-Git Alternatives

Non-git memory stores can help, but they should be secondary.

Examples:

- local notes
- task apps
- chat threads

These can support thinking, but they should not replace repo memory because the other machine and future agents cannot trust them by default.

## Bottom Line

Two Codex installations become one CTO system only when both read and write the same git-tracked memory layer.
