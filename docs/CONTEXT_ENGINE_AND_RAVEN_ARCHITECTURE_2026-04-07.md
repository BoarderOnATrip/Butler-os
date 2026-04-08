# Context Engine And Raven Architecture

Date: 2026-04-07

## Product Thesis

`aiButler` should be built as a thin context engine with a memorable interface, not as a conventional CRM.

CRM, tasking, search, maps, and retrieval are all projections of the same core substrate:

- markdown entity sheets
- append-only event and provenance records
- layered memory
- place, person, time, and artifact links

The product should feel frictionless on capture, conservative on ambiguity, and unusually easy to correct.

The interface personality is a floating Raven assistant:

- always available
- small and movable
- expandable into a scroll-shaped interaction surface
- able to speak, listen, point, and stay out of the way

## Non-Negotiable UX Rules

### 1. Capture First

The system should accept as much context as the user gives it:

- voice
- photos
- receipts
- screenshots
- files
- notes
- calls
- messages
- calendar data
- location and place signals

It should ingest first and classify second.

### 2. Ask When Unsure

When the system is not confident enough to safely structure or act, it should ask immediately if the question is cheap, or send the item to a pending space if the user is busy.

The system should bias toward clarification over silent corruption.

### 3. Pending Is A First-Class Memory Layer

There must be a third state between "working on this now" and "stored forever":

- `working memory`
- `general memory`
- `pending / unresolved`

Pending exists so humans can batch triage low-importance ambiguity later.

### 4. Correction Must Be Easier Than Re-Doing

Every classification, link, summary, and task needs lightweight correction:

- quick undo
- relink entity
- split one thing into two things
- merge duplicates
- "not this person"
- "wrong place"
- "wrong receipt category"
- "do not learn from this"

Corrections should write provenance and improve future routing.

### 5. Interruption Must Not Derail The Current Job

The user must be able to interrupt the assistant mid-run without destroying task continuity.

We need:

- soft interrupt: ask a side question while preserving the current task
- hard interrupt: stop current action immediately
- point correction: click a specific on-screen item and redirect the model to that target
- resume: return to the suspended thread with working memory intact

### 6. Provenance Everywhere

Every memory should record:

- source app
- input type
- device
- hardware
- timestamp
- place
- confidence
- permissions used
- whether the user confirmed or corrected it

This is how the system gets better over time without becoming opaque.

## Product Shape

The core product is a context engine with four visible modes:

1. `Capture`
2. `Clarify`
3. `Act`
4. `Review`

`Capture` is frictionless.

`Clarify` is selective and confidence-aware.

`Act` uses working memory, tools, and approvals.

`Review` lets the user batch-process pending items and fix mistakes.

## Memory Model

### Working Memory

Short-lived state for the active task or conversation:

- current objective
- active people, places, files, and apps
- temporary assumptions
- selected UI anchors
- interruption stack

This should be resumable but ephemeral.

### General Memory

Durable, user-legible context:

- people
- organizations
- places
- projects
- files
- preferences
- routines
- commitments
- relationship history

This is the long-term context layer.

### Pending Memory

Unresolved or low-confidence captures:

- unlabeled receipts
- unknown callers
- ambiguous photos
- weak entity links
- partial notes
- "might matter later" fragments

Pending should be easy to batch in a dedicated review surface.

### Event Ledger

Append-only records of what happened:

- captures
- observations
- user corrections
- assistant actions
- call metadata
- message metadata
- file imports
- tool executions

The ledger is the system of provenance, not the primary user-facing memory surface.

## Canonical Data Model

### Canonical Truth

Human-facing canonical truth should live in markdown sheets.

Machine-facing raw history should live in append-only structured logs.

That means:

- `.md` for durable sheets and summaries
- `.jsonl` or database event tables for raw events and receipts

### Canonical Entity Types

- `Person`
- `Organization`
- `Place`
- `Conversation`
- `Task`
- `Project`
- `Artifact`
- `Secret`
- `Event`
- `Link`

### Canonical Repository Layout

```text
context/
  people/
    <slug>.md
  organizations/
    <slug>.md
  places/
    <slug>.md
  conversations/
    <slug>.md
  projects/
    <slug>.md
  tasks/
    <slug>.md
  artifacts/
    <slug>.md
  pending/
    <yyyy-mm>/
      <id>.md
  maps/
    places.geojson
  events/
    <yyyy-mm-dd>.jsonl
  receipts/
    <yyyy-mm-dd>.jsonl
  indexes/
    links.jsonl
    embeddings.jsonl
```

### Sheet Shape

Each entity sheet should include frontmatter for structured state and markdown body for human-readable context.

Minimum frontmatter:

```yaml
id: person_01
kind: person
name: Jane Doe
aliases: []
links:
  - org/acme
  - place/toronto-office
source_refs:
  - event_2026_04_07_001
last_confirmed_at: 2026-04-07T00:00:00Z
confidence: 0.94
status: active
```

### Why Markdown Stays Canonical

- portable
- inspectable
- diffable
- survivable across model vendors
- easy to project into other tools
- easy to repair by hand

## Place-Based Context

Place is first-class, not an optional tag.

A place can be:

- GPS-based
- semantic
- virtual

Examples:

- Home
- Toronto Office
- Client Site
- Airport
- Car
- Phone Call
- Zoom Room
- Inbox

Places should accumulate:

- linked people
- linked artifacts
- recurring tasks
- relevant files
- recent conversations
- current routines

This gives us a "virtual environment" that can feel spatial without requiring full 3D on day one.

## Capture And Resolution Pipeline

### Flow

```text
capture -> observe -> classify -> confidence score -> route
```

Possible routes:

- auto-commit to general memory
- ask now
- place in pending
- create task
- create CRM projection
- request approval before action

### Example: Receipt Photo

1. user takes a photo
2. OCR and layout extraction run
3. candidate merchant, amount, date, and category are inferred
4. if confidence is high, create artifact sheet + expense event
5. if confidence is medium, ask one clarifying question
6. if confidence is low or the user is busy, put it in `pending`

### Example: Unknown Phone Call

1. call metadata arrives
2. match against known people and orgs
3. create event with phone, time, duration, and device source
4. if matched, append to the relationship history
5. if unmatched, create pending person candidate
6. ask later: "Was this Sarah from Acme?"

## Correction And Interruption Model

### Soft Interrupt

Keep the current task live, open a side thread, then resume.

Use for:

- short clarifications
- quick lookup
- redirecting one field

### Hard Interrupt

Stop tool execution or narration immediately.

Use for:

- wrong recipient
- wrong click target
- privacy concern
- spending or sending mistake

### Point Correction

The user points to a specific visual anchor and says what is wrong.

The system must preserve:

- screenshot anchor
- window or app identity
- selected element bounds
- current task id

This lets the user correct one exact thing without derailing the full job.

### Correction Logging

Every correction should write:

- what was changed
- which model output it corrected
- source item
- user confidence
- whether the correction is local-only or reusable

## Raven Interface

### UI Thesis

The UI should feel characterful and useful, not like another empty chat box.

The Raven should be:

- draggable
- resizable
- minimizable
- always callable
- expressive without being noisy

### Base Form

The Raven lives as a floating desktop and mobile companion with three persistent controls:

1. resize
2. minimize
3. talk / listen

Primary interaction expands a compact scroll panel.

### Scroll Panel

The scroll is the efficient interaction canvas.

It should support:

- current reply
- live actions
- clarification prompts
- quick fixes
- pending item controls
- relationship cards
- task and follow-up chips

### UI Modes

- `Perch`: compact floating Raven
- `Scroll`: expanded interaction panel
- `Map`: place and graph context view
- `Review`: pending and correction batch mode

### Old-School Inspiration, Modern Behavior

The Raven can borrow the friendliness of classic assistants without inheriting their intrusiveness.

Rules:

- never steal focus without clear cause
- never autoplay long speeches
- prefer concise visual cues
- let the user dismiss or pin interaction states instantly

## System Boundaries

### aiButler

Owns:

- phone and desktop user experience
- capture surfaces
- context engine runtime
- markdown sheets
- pending review
- approvals
- direct user-facing intelligence

### Mira

Owns:

- structured CRM projection
- outreach state
- campaigns
- business reporting

Mira should not become the canonical memory store.

### Paperclip

Owns:

- operator control plane
- routines
- agent supervision
- coding and ops orchestration

Paperclip should not become the phone UX or canonical memory store.

## Recommended Open-Source Stack

Build from scratch, but use strong open-source primitives instead of inventing infrastructure we do not need.

### Core Storage

- `PostgreSQL` for structured projections and durability
- `PostGIS` for place and geospatial queries
- `pgvector` for semantic retrieval inside the same database

Use the database as an index and projection layer. Markdown sheets remain canonical.

### Sync

- `ElectricSQL` for local-first sync between phone, desktop, and backend projections

### Realtime Voice And Presence

- `LiveKit` for realtime transport

### Document And Receipt Ingestion

- `Docling` for document parsing, OCR, and structure extraction

### Graph And Place Visualization

- `React Flow` for point-cloud and linked-node editing
- `MapLibre` for place-based views

### Control Plane

- `Paperclip` for agent operations, routines, and board UI

### Existing Internal Repos To Reuse

- `aiButler.me` as the user-facing product shell
- `Mira Platform` as the CRM projection
- `paperclip` as the operator plane

## V0 Delivery Order

### Slice 1: Canonical Context Repository

Build:

- markdown sheet format
- event ledger
- provenance model
- pending item model
- entity linker

### Slice 2: Frictionless Capture

Build:

- phone photo capture
- note capture
- file capture
- receipt pipeline
- pending review inbox

### Slice 3: Relationship Context

Build:

- person and organization sheets
- call metadata ingestion
- message metadata ingestion
- relationship briefings
- follow-up suggestions

### Slice 4: Place Layer

Build:

- place sheets
- map view
- place-to-person linking
- contextual "what matters here?" packs

### Slice 5: Raven Shell

Build:

- floating Raven shell
- scroll interaction panel
- talk/listen control
- soft and hard interrupt controls
- point correction flow

### Slice 6: CRM Projection

Build:

- projection jobs into Mira
- contacts, stages, and follow-ups
- operator dashboard in Paperclip

## MVP Demo

The first demo should prove this loop:

1. user takes a receipt photo and receives one follow-up question or a pending item
2. user receives or places a phone call and the person + place context updates
3. user opens the Raven and asks what matters right now
4. the system answers with place-aware and relationship-aware context
5. Mira reflects the business subset
6. Paperclip shows the routines and operator state

## Anti-Goals

Do not:

- make chat transcripts the only memory
- make Mira the canonical truth layer
- make Paperclip the user product
- require perfect structure before capture
- silently auto-file low-confidence items
- hide provenance or correction history

## References

- Paperclip: https://github.com/paperclipai/paperclip
- PostGIS: https://postgis.net/
- pgvector: https://github.com/pgvector/pgvector
- ElectricSQL: https://electric-sql.com/
- LiveKit: https://docs.livekit.io/
- Docling: https://docling-project.github.io/docling/
- React Flow: https://reactflow.dev/
- MapLibre: https://maplibre.org/
