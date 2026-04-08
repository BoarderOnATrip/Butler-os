# Real Prototype Execution Track

Date: 2026-04-07

## What "Real Prototype" Means

The real prototype is not:

- another architecture draft
- a generic chat app
- a CRM mockup

The real prototype is:

1. capture something from the phone
2. persist it into the canonical context repository
3. place it into the right memory lane
4. let the user review and correct it easily
5. project relevant subsets into business flows later

## Prototype Contract

### Canonical Truth

- markdown sheets
- pending markdown captures
- append-only event/provenance logs

### User Surfaces

- `phone`: capture, pending review, quick context
- `desktop`: trusted execution, approvals, local tooling
- `paperclip`: operator plane, routines, coding agents

### Memory Lanes

- `working`
- `general`
- `pending`

## Immediate Build Program

### Track 1: Phone Capture

Goal:

- capture note, receipt, or artifact from the phone
- send it to the paired desktop runtime
- show it in the pending queue

Done when:

- the phone can save a receipt/photo into pending
- the user sees the new item immediately

Status:

- complete for v0 text and image capture
- mobile now supports manual note capture, camera capture, and photo-library capture
- paired phones can write straight into the canonical pending queue through the desktop bridge

### Track 2: Runtime Ingest

Goal:

- accept phone capture payloads
- persist files under the canonical context repo
- create pending items and provenance events

Done when:

- each capture has file path, source metadata, and an event trail

Status:

- complete for v0 artifact ingest
- uploads are persisted under `~/.aibutler/context/inbox/uploads/<YYYY-MM>/<capture_id>/`
- pending items and provenance events are written in the same flow
- source app, device, surface, file hash, and saved path are preserved

### Track 3: Runtime Hardening

Goal:

- eliminate trivial JSON store clobbering under concurrent access

Done when:

- bridge calls and CLI calls no longer lose session or task writes

Status:

- first hardening pass complete
- runtime JSON writes now use lock files, atomic temp-file writes, and merge-on-save semantics
- this is enough for prototype traffic; a database-backed state layer can wait until later

### Track 4: Pending Review

Goal:

- review newest unresolved captures first
- correct, confirm, or defer without friction

Done when:

- the user can batch through pending items on phone or desktop

Status:

- in progress
- the phone can list the newest pending items
- correction, confirm, merge, and promote flows still need to be built

### Track 5: Relationship Ingest

Goal:

- log a real interaction from the phone
- update or create a canonical person sheet
- derive a trustworthy follow-up queue from live context, not demo data

Done when:

- phone interaction logging writes durable person state
- follow-ups are ranked from canonical sheets
- briefings and pipeline sweeps can use the live queue

Status:

- complete for v0 manual relationship ingest
- the phone can log calls, texts, meetings, and outreach notes into person sheets
- the runtime creates append-only relationship events and a derived follow-up queue
- agentic pipeline/follow-up objectives now route to the live relationship queue

### Track 6: Journal + Android Packaging

Goal:

- give the phone a diary-style LIFO surface instead of only forms
- bootstrap CRM trust from desktop contacts
- generate a native Android project that can be installed once the SDK is present

Done when:

- pinned people and recent activity are visible on the phone
- trusted desktop contacts can backfill canonical person sheets
- Expo packaging is clean and the Android native directory exists

Status:

- complete for v0 journal and packaging prep
- the phone now has a LIFO activity journal with pin and unpin actions
- desktop Contacts.app can import directly into canonical person sheets for CRM bootstrap
- Raven-themed mobile icon, adaptive icon, and splash assets now exist
- Expo doctor passes in managed mode and the Android native project has been prebuilt
- local APK assembly is still blocked on missing Android SDK configuration on this machine

## Status After Today's Build

What is real now:

- phone pairing to the trusted desktop bridge
- manual capture to pending
- photo capture from camera
- photo selection from library
- canonical file persistence with provenance
- pending queue refresh on phone
- bridge-safe runtime writes under concurrent access
- phone-side relationship ingest
- canonical person sheets with CRM metadata
- derived relationship follow-up queue
- relationship briefing and pipeline routing against live context
- phone-side LIFO journal with pinned records
- trusted desktop contact import into the canonical people graph
- generated Android native project under `mobile/android`

What is not real yet:

- OCR extraction from receipts and documents
- correction-first pending review actions
- working-memory versus general-memory promotion
- automatic call and message metadata ingest
- place graph and context packs
- Raven desktop shell
- a locally assembled Android APK on this machine because the Android SDK is not installed here

## What More We Need To Get Serious

Not more abstract architecture. We need three focused build tracks:

1. `ingest intelligence`
   - OCR for receipts, screenshots, and documents
   - auto-suggest title, merchant, amount, person, and date fields
   - uncertainty stays visible and lands in `pending`

2. `review and correction`
   - promote pending item to canonical sheet
   - merge into an existing person/place/org
   - one-tap "wrong", "later", "link this", and "never do this again" controls

3. `relationship context`
   - automatic call log and message metadata capture
   - person matching and follow-up suggestion generation
   - correction hooks for merge, split, and false-link cases
   - place/time linkage so the system starts inferring why something matters

4. `android execution`
   - install Android SDK and `adb` on the build machine
   - create `mobile/android/local.properties` or set `ANDROID_HOME`
   - run Gradle assembly and install to a physical device

## Next Three Slices After Current Work

### Slice A: Receipt Artifact Flow

- phone photo capture
- saved original image
- pending receipt item
- quick merchant/category clarification

### Slice B: Person + Call Metadata Flow

- ingest call metadata automatically
- match or create person candidate
- link to place and time
- create follow-up suggestion
- let the user correct the match in one tap

### Slice C: Place Context Pack

- current place node
- linked people
- linked pending items
- "what matters here?" briefing

## Guardrails

- no new dashboard-first work
- no replatforming away from markdown truth
- no burying ambiguity instead of surfacing it
- no silent automation without correction hooks
- no treating Paperclip as the end-user product

## Current Assumptions

- Android-first speed matters more than full iOS parity
- bridge pairing remains the trust boundary
- the desktop stays the high-trust execution surface
- the context repository stays under `~/.aibutler/context`
