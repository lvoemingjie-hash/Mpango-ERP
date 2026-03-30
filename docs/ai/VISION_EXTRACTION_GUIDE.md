# Vision Extraction Guide

Use this guide when converting historical ChatGPT or other AI conversations into repository memory that Codex can reliably use.

## Core Principle

Do not try to transfer the whole conversation. Transfer the durable intent behind it.

The goal is not identical wording. The goal is equivalent decision-making.

## What To Extract

Prioritize information that changes how CTO-level decisions should be made:

- Product mission
- Target customer and first real users
- Non-negotiable constraints
- Tradeoff preferences
- Launch criteria
- Features intentionally delayed or rejected
- Team operating preferences
- Architectural beliefs that keep recurring

## What Not To Extract

Usually omit:

- Brainstorming branches that were never chosen
- Motivational text
- Repeated explanations
- Tactical details that are already obvious in code
- Temporary ideas that no longer affect decisions

## Compression Method

For each old conversation, rewrite the result into one of these forms:

- Decision: "We chose X because Y"
- Constraint: "We must not do X because Y"
- Priority: "For the next phase, X outranks Y"
- Principle: "When forced to trade off, prefer X over Y"
- Rejection: "We explicitly decided not to pursue X yet"

## The Five Things That Create Shared Vision

If you want Codex to feel closer to your Web GPT's vision, make sure these five areas are explicit:

### 1. Who We Serve

- Who is the first real customer?
- What daily pain are we solving?
- What environment do they operate in?

### 2. What Winning Looks Like

- What must be true for you to call this release successful?
- What counts as "usable" versus merely "demoable"?

### 3. What We Refuse To Compromise

- Security
- Tenant isolation
- Simplicity of user workflows
- Financial correctness
- Delivery speed, if that truly matters

### 4. How We Choose Between Competing Work

Examples:

- Real business flow over admin polish
- Stability over feature count
- Operational clarity over abstraction
- Product traction over premature platform generalization

### 5. What We Are Not Building Yet

This is extremely important. Vision is shaped as much by exclusions as by ambitions.

## Good Extraction Example

Weak:

- "We talked a lot about retailers and UX."

Strong:

- "Retailer ordering is strategically important, but it must not delay wholesaler operational readiness. If capacity is limited, improve wholesaler workflows first."

## Repository Placement Rules

- Put enduring strategy into `docs/ai/PROJECT_MEMORY.md`
- Put operating posture into `docs/ai/CTO_CONTEXT.md`
- Put architecture and governance decisions into `decision-register/`
- Put feature-specific detail into the closest feature doc

## Quality Test

A good extracted note should help Codex make the same decision your Web GPT would have made even if the original chat is unavailable.

If the note cannot guide a real tradeoff, it is probably too vague.
