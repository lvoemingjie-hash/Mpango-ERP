# Project Memory

This file captures durable context that may originally have lived in chat history but should now become repository memory.

## Why This Exists

Long chat histories are useful, but they are not a reliable operating substrate for AI agents. This file converts high-value background into stable project memory.

## Confirmed Baseline

- Repository is the operational source of truth
- Product priority is a usable wholesaler ERP, not platform theater
- Product and platform work can proceed in parallel, but product continuity wins when tradeoffs appear
- Multi-tenant safety is a hard constraint

## Strategic Intent

- Mpango's current product core is a wholesaler-led B2B ERP that extends downstream to retailers
- The retailer side exists to strengthen wholesaler operations, order capture, and network stickiness rather than to become an independent consumer-style product at this stage
- The near-term mission is to make one wholesaler and one retailer complete a reliable end-to-end business loop under strict tenant isolation
- Longer term, the product may expand upward into supplier-facing workflows and downward into retailer-to-end-customer flows, but those expansions must be earned by real usage and market pull rather than assumed up front
- Market direction should be informed by adoption and operational value, not by prematurely building every layer of the ecosystem
- Sustainable user growth, ongoing system usage, and real market utility are strategic goals because they create the conditions for long-term product relevance
- The African internet growth window is a strategic timing factor, so delivery speed matters, but not at the expense of tenant safety, correctness, or architectural discipline

## Product Boundary

- Mpango is not currently an open marketplace product
- Mpango is not currently a retailer-first SaaS
- Mpango is not currently a platform-admin-first business
- The current operating posture is wholesaler core first, retailer enablement second, broader ecosystem expansion later

## Product Hierarchy

- Primary customer: wholesaler
- Secondary operational user: invited retailer under wholesaler control
- Future possible expansions: supplier workflows upstream, end-customer workflows downstream

## Growth Logic

- First prove wholesaler daily operational value
- Then strengthen retailer adoption where it increases wholesaler throughput and retention
- Then evaluate supplier and end-customer extensions based on actual market behavior
- Growth in users and data volume is desirable only when it reinforces product usefulness and defensibility

## Delivery Tradeoff Principle

- During the current phase, speed is important because of market timing, but speed does not override tenant isolation, payment correctness, contract integrity, or bootability
- When forced to choose, prefer a smaller working operational loop over a broader but fragile ecosystem play

## To Capture From Historical Chats

Add short, high-signal notes here when prior ChatGPT or other AI conversations contain information that still matters.

Recommended sections:

### 1. Strategic Intent

- What kind of company Mpango is becoming
- Who the first paying users are
- What must be true before launch

### 2. Product Philosophy

- What the product should feel like for wholesalers and retailers
- What complexity should stay hidden from users
- Which workflows are mission-critical

### 3. Rejected Paths

- Ideas that were considered and intentionally not pursued
- Architectural patterns that were ruled out
- Premature features that should not distract the team

### 4. Current Priorities

- Top 3 to 5 active outcomes
- Near-term blockers
- What should explicitly wait

### 5. Decision Carry-Overs

- Important decisions made in chat but not yet formalized in `decision-register/`
- Temporary policies that are still active

### 6. AI Collaboration Preferences

- How the owner wants AI agents to communicate
- Preferred implementation style
- Review expectations
- Branching, testing, and rollout preferences

## Compression Rule

Do not paste entire old conversations here. Rewrite them into concise decisions, constraints, and priorities. If a fact is too vague to guide implementation, omit it.

## Promotion Rule

- If a note changes architecture or governance, promote it into `decision-register/`
- If a note changes operating policy for all AI agents, also update `docs/ai/CTO_CONTEXT.md`
- If a note only matters to one feature, move it into the nearest feature doc instead
