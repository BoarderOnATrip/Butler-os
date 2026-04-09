# Butler-os Roadmap

Date: 2026-04-08

## Why This Doc Exists

We need one current answer to three questions:

1. What are we actually building?
2. What is already real in `Butler-os`?
3. What gets built next, in what order?

This roadmap is the working product plan for the repo as it exists today.

## Product Definition

`aiButler` is not just a CRM, and it is not just a voice assistant.

It is a phone-first context engine with a CRM projection and a trusted desktop execution surface.

The product has four core jobs:

1. capture life and work context with low friction
2. preserve provenance and uncertainty
3. turn context into trustworthy follow-up and execution suggestions
4. execute actions safely through a local, approval-first runtime

## Product Shape

Two surfaces are non-negotiable:

- `phone`
  The everyday surface for capture, briefings, review, relationship context, and approvals.
- `desktop`
  The high-trust surface for local execution, secrets, supervised computer use, and future Raven presence.

One substrate is canonical:

- `context repository`
  Markdown sheets plus append-only events under `~/.aibutler/context`

## What Is Real Right Now

These things are implemented in this repo today.

### Runtime

- approval-aware local runtime
- typed tool registry
- context repository with markdown sheets and JSONL events
- pending queue as a first-class memory lane
- thin core agent for deterministic routing and recall
- relationship memory and follow-up derivation
- memory search via the Butler recall layer

### Desktop

- Tauri desktop shell
- onboarding and secure config persistence
- bridge launch path
- local voice bootstrap path
- desktop control surface for pairing and runtime status

### Bridge

- FastAPI local bridge
- pairing token model
- mobile-to-desktop tool execution
- core-agent `/assist` endpoint
- context capture endpoint
- LAN mode for paired phone access

### Mobile

- Android installable development build
- phone-to-desktop pairing flow
- quick actions
- manual relationship ingest
- pending capture from text, camera, and photo library
- LIFO activity journal
- context graph card
- review lane UI
- Android call-log and SMS-thread metadata reader
- one-tap metadata sync into relationship memory

### CRM / Relationship Layer

- canonical person sheets
- append-only interaction events
- derived follow-up queue
- relationship briefing
- desktop contact import for bootstrap
- automatic dedupe for repeated phone metadata sync

## What Is Partially Real

These exist, but are not finished enough to call trustable v1 features.

### Review And Correction

- review queue exists
- promote / defer / dismiss / restore exist
- Butler analysis exists

Still missing:

- merge duplicate people
- split one mistaken person into two
- "wrong person" repair
- "wrong place" repair
- "do not learn from this"
- correction feedback that materially improves future matching

### Voice

- mobile voice UI exists as a scaffold
- local voice loop exists in Python
- ElevenLabs-first setup path exists

Still missing:

- a production voice architecture
- low-latency live voice on phone
- interruption and resume
- tool calling from live voice in a robust way
- a final decision on OpenAI Realtime vs. a hybrid path

### Graph / Context Engine

- graph snapshot exists
- linked person/org/place/conversation edges exist

Still missing:

- place-first context packs
- richer spatial and temporal inference
- a genuinely navigable graph surface
- Raven as the persistent interface shell

## What Is Not Real Yet

These are still roadmap items, not product truth.

- release-grade Android build without Metro
- iOS parity
- QR pairing
- OCR and receipt/document extraction
- contract versioning workflows
- file annotation and signature flows
- screenshot/video-snippet capture workflow end to end
- cloud sync and VM-backed execution
- full Paperclip control-plane integration
- end-user Raven desktop shell

## UI Direction

We should stop treating the UI as one screen with many cards and start treating it as a coherent product.

### Phone UI Strategy

The phone app should become five primary modes:

1. `Brief`
   Today, top follow-ups, urgent pending items, current place/person context.
2. `Capture`
   Voice, note, photo, receipt, screenshot, share-sheet ingress.
3. `Review`
   Pending and uncertain items, with frictionless correction.
4. `Relationships`
   People, threads, follow-ups, and CRM context.
5. `Act`
   Quick actions, approvals, delegation, and later voice handoff.

The current card-heavy prototype is acceptable for testing, but not the final information architecture.

### Desktop UI Strategy

Desktop should move in three stages:

1. `setup and control`
   Onboarding, secrets, bridge, approvals, runtime status.
2. `execution console`
   Tasks, approvals, receipts, local tools, imported sessions, debug surfaces.
3. `Raven shell`
   Floating assistant, expandable scroll UI, interruption-aware command surface.

### Design Principles

- LIFO diary views should remain central
- graph and map views should be secondary but delightful
- review and correction should be faster than manual cleanup
- ambiguity should be visible, not buried
- the user should always know what the system knows, what it inferred, and what it is unsure about

### Skins, Modules, And Recipes

We should treat the "skin" idea as a real product layer, not just theming.

- `module`
  A reusable surface block such as Brief, Capture, Review, Relationships, Act, Approvals, Graph, or Journal.
- `recipe`
  A reusable high-level workflow such as Daily Brief, Pipeline Sweep, Bring Butler Online, or Inbox Triage.
- `skin`
  A bundle that chooses modules, quick actions, defaults, visual treatment, and tone for a use case.

This gives Butler a path to stay simple for users while remaining highly extensible for open source contributors.

## Technical Direction

### Canonical Truth

Keep:

- markdown sheets
- JSONL event ledger
- local-first execution
- bridge pairing as trust boundary

Do not replatform away from this now.

### Voice Direction

Recommended direction:

- keep Butler runtime as the execution plane
- move live voice toward OpenAI Realtime for the main voice shell
- keep Butler tool execution local through the bridge/runtime
- treat ChatGPT / Apps SDK / MCP as an external entry point later, not the primary shell

### Secret Recovery Direction

Recommended direction:

- use Maccy as a recovery surface, not as a hidden secret source of truth
- keep Keychain as the canonical local secret store
- let the phone ask what is offline and request recovery
- require explicit approval before Butler restores or reveals credentials
- never normalize blind secret pasting as the default runtime behavior

### Mini-Agent Direction

Recommended direction:

- keep the Butler core agent small, deterministic, and always available
- give it Paperclip-style powers through a separate power plane, not by bloating the core router
- treat the phone-side mini-agent as the front door and the delegated worker fabric as the muscle
- let the heavy operator fabric live either locally or in a shared VPN-backed OpenClaw environment, as long as Butler keeps approvals, provenance, and trust boundaries explicit on the user side

The mini-agent should gain these powers over time:

- tool discovery and capability introspection
- approval queue awareness
- routines / recipes / saved workflows
- MCP client access to external tools
- MCP server exposure for Butler's own safe tool surface
- background jobs and scheduled runs
- worker delegation with receipts and checkpoints

The mini-agent should not become:

- a fully autonomous always-on operator by default

### Continuity And Collaboration Direction

Recommended direction:

- treat phone and desktop handoff as a first-class continuity layer, not a side feature
- start with append-only continuity packets plus explicit `claim` and `ack` semantics
- let one device actively claim a draft or task while the other waits, forks, or comments
- keep publish artifacts immutable; publishing should create a new version instead of overwriting in place
- use optimistic concurrency for team publishing with `version` and `parent_version`
- keep room layout and camera/view state lightweight, but version actual room objects and content patches

This is the safest path toward simultaneous edits and multi-publishing:

- `handoff packets` for transport
- `leases` for active editing
- `versions` for publishing
- `append-only events` for provenance
- a hidden automation layer that mutates state without user visibility
- a replacement for Butler's canonical context model

### Agent Stack Direction

The right stack is layered:

1. `phone context model`
   Tiny, fast, local-first. Handles intent classification, context compression, entity extraction, and offline triage.
2. `Butler core agent`
   Thin routing layer for recall, review, follow-up context, and safe execution requests.
3. `power plane`
   Paperclip-style powers: routines, approvals, MCP, delegation, and receipts.
4. `worker fabric`
   Heavier delegated agents, isolated workspaces, external integrations, and longer-running tasks.

This lets Butler feel simple on the phone while still growing into a serious operator system.

### CRM Direction

Recommended direction:

- Butler owns canonical people, interactions, follow-ups, and provenance
- CRM is a projection of context, not the other way around
- phone metadata, messages, places, and files should enrich the same canonical person records

## Roadmap

## Phase 0: Stabilize The Current Prototype

Goal:

- make the existing Android and bridge loop dependable enough for daily testing

Work:

- verify phone metadata sync on real device repeatedly
- harden bridge pairing UX
- remove Metro-only dependency for installable Android testing
- improve error reporting on mobile
- clean up demo and smoke data workflows
- add a dependable “bring Butler back online” secret recovery path for local integrations

Done when:

- a fresh tester can install, pair, sync, and review without terminal babysitting

## Phase 1: Trustable CRM

Goal:

- make the relationship layer accurate enough to trust

Work:

- call log and SMS ingest hardening
- merge / split / wrong-contact repair
- person matching improvements
- correction memory
- contact detail enrichment
- easier follow-up editing

Done when:

- the system can ingest real phone metadata and stay clean after user correction

## Phase 2: Real Voice Butler

Goal:

- ship a voice layer that is useful, fast, and tied to Butler execution

Work:

- choose the main live voice architecture
- wire tool calling through Butler runtime
- interruption and resume
- voice-to-review and voice-to-follow-up flows
- short, natural speaking style with explicit action confirmations
- teach the thin phone agent to invoke the power plane instead of trying to do everything itself

Recommended implementation:

- OpenAI Realtime for conversation
- Butler bridge/runtime for tools and execution

Done when:

- a user can talk naturally, ask for context, and safely trigger real work

## Phase 2.5: Mini-Agent Power Plane

Goal:

- give Butler's thin agent Paperclip-style powers without sacrificing simplicity

Work:

- expose safe Butler capabilities as an MCP-friendly surface
- add capability discovery and tool manifests to the phone and desktop shells
- add routines / recipes as reusable high-level workflows
- add background jobs with receipts
- add worker delegation for heavier tasks
- add secret-health and recovery loops so the agent can tell the user what is offline and how to restore it

Done when:

- the mini-agent can stay simple while still orchestrating real work through routines, tools, and workers

## Phase 3: Proper Review And Context Engine

Goal:

- turn Butler from “CRM with capture” into a real context engine

Work:

- working vs general vs pending memory promotion
- place nodes and place context packs
- artifact extraction and linking
- user-visible provenance and confidence
- better graph / timeline navigation

Done when:

- Butler can answer “what matters here, now, and why?” from real linked context

## Phase 4: Delightful Operations Layer

Goal:

- add the tools that make Butler feel like a real operator

Work:

- screenshot and snippet capture
- document transformation
- annotation
- signature workflows
- file and contract version visibility
- OpenScreen import and clip workflows

Done when:

- Butler is useful for daily executive/admin work, not just follow-up memory

## Phase 5: Raven And External Surfaces

Goal:

- make the product memorable and extensible

Work:

- Raven desktop shell
- floating assistant UI
- richer graph and map presentation
- Paperclip operator plane integration
- external MCP / ChatGPT entry points
- cloud sync and remote execution where appropriate
- skins, modules, and recipes that let the same runtime feel different by use case

Done when:

- Butler feels like a unique product surface, not just a collection of tools

## Build Order

This is the recommended execution order from today:

1. stabilize Android prototype loop
2. harden CRM correction and person matching
3. ship real voice architecture
4. add the mini-agent power plane
5. add OCR and artifact extraction
6. deepen place/time/context inference
7. build Raven shell
8. add cloud and external control-plane integrations

## What We Should Explicitly Not Do Right Now

- no major replatform
- no rewriting the runtime around a new storage model
- no dashboard-first detour
- no “smart” silent automation without correction hooks
- no polishing Paperclip before Butler’s own core loop is trustworthy
- no making the phone mini-agent responsible for every heavy task when a delegated worker is the right shape

## Current Repo Assessment

`Butler-os` is now past the architecture-only stage.

It is a real prototype with:

- installable Android development build
- paired phone-to-desktop flow
- canonical context persistence
- manual and automatic relationship ingest
- review lane
- memory search
- graph and journal surfaces

It is not yet a launchable product because:

- voice is not finalized
- correction is not complete
- release packaging is not complete
- trust-critical CRM cleanup workflows are still missing

## Next Concrete Sprint

The next sprint should be:

1. make Android install and pairing repeatable without Metro confusion
2. add merge / split / wrong-person correction
3. replace voice scaffolding with the chosen real voice stack
4. add OCR for receipts and documents

If we do those four things, Butler stops feeling like a promising prototype and starts feeling like a real product.
