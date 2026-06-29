# P21-D0 Goose Middleman Shadow Pilot Configuration

Date: 2026-06-29
Branch: codex/platform-p21d0-goose-middleman-config-2026-06-29
Base: platform-dev at fc9eb40

## Objective

Configure a project-local Goose middleman shadow pilot for the Mpango ERP SaaS
platform track. Goose is evaluated as a dispatcher/recorder between Codex CTO
and Claude Worker, not as a reviewer, developer, gatekeeper, or merger.

## Deliverables

- `.review/PROJECT_CONTEXT.md`
- `.review/templates/task.schema.json`
- `.review/templates/result.schema.json`
- `.review/tasks/P21-D0.task.json`
- `.review/recipes/p21d0-goose-middleman.yaml`
- `.review/inbox/.gitkeep`
- `.review/outbox/.gitkeep`
- `.review/audit/.gitkeep`
- `.review/state/.gitkeep`
- `scripts/run_goose_p21d0_middleman.ps1`

## Boundaries

- No Goose global config changes.
- No runtime code changes.
- No backend API, frontend, migration, model, service, auth/RBAC, package,
  lockfile, product-dev-recovered, or `.secrets.baseline` changes.
- Goose must not invoke Claude during P21-D0.
- Goose must not merge, push, or write final approval markers.

## Runner Design

The PowerShell runner intentionally does not let the model directly edit files.
It reads the project context and task packet deterministically, asks Goose to
return one JSON object, validates that object, and writes only the three
approved shadow outputs. This avoids model/tool-name drift observed with local
models while still evaluating Goose as the middleman reasoning layer.

## Validation Plan

1. Validate the Goose recipe with `goose recipe validate`.
2. Run the shadow pilot manually with `scripts/run_goose_p21d0_middleman.ps1`.
3. Confirm Goose writes only:
   - `.review/outbox/P21-D0.to-claude.md`
   - `.review/audit/P21-D0.audit.md`
   - `.review/state/goose-runner-state.json`
4. Confirm no runtime or platform product files are modified by Goose.
5. Run `git diff --check`, forbidden path audit, and GitNexus analyze before
   any merge consideration.

## Initial Run Result

Goose was configured to use the user's current model selection
(`ollama` / `gemma4:e2b`) without changing global Goose config.

Two direct-tool attempts were intentionally rejected by the wrapper:

- The first headless recipe run failed because Goose requires a prompt field.
- After the prompt was added, Gemma attempted to use the wrong context/file
  access path and did not create the required files.

The runner was then hardened into a deterministic wrapper:

- PowerShell reads the context and task packet.
- Goose receives the content and returns one JSON object.
- PowerShell validates required fields and quality gates.
- PowerShell writes only the three approved shadow outputs.

Final manual run result:

- `goose recipe validate .review/recipes/p21d0-goose-middleman.yaml`: PASS.
- `scripts/run_goose_p21d0_middleman.ps1`: PASS.
- Generated files:
  - `.review/outbox/P21-D0.to-claude.md`
  - `.review/audit/P21-D0.audit.md`
  - `.review/state/goose-runner-state.json`
- No Claude dispatch.
- No runtime code touch.
- No merge or push by Goose.
- No final approval marker.
- Output quality gates were enforced by the wrapper:
  required outbox headings, minimum outbox length, audit phrases, no incorrect
  `Gemini` worker label, and UTF-8 without BOM / ASCII-only generated files.

## Risk

LOW. This is project-local automation configuration only. It does not change
platform runtime behavior and does not grant Goose final authority.
