# Butler Boundary Spec

Date: 2026-04-09

This file is the canonical boundary contract. Any other boundary notes or copies in other repos or workspace roots are derivative and should be deleted or treated as mirrors once synced.

## Purpose

This document defines the working boundary between:

- `Butler-os`
- `DewDrops`
- `Lifegirdle`

The goal is simple:

- one canonical source of truth
- one continuity protocol
- one publish/version model
- no duplicate runtime or sync systems

## Core Rule

`Lifegirdle` is a shared context model, not a third runtime.

That means:

- `Butler-os` owns truth, continuity, approvals, sync policy, and publish/version state
- `DewDrops` owns the desktop spatial harness and multi-agent orchestration UX
- `Lifegirdle` defines durable context objects, layers, and schemas that both systems consume

## Single Source Of Truth

`Butler-os` is the canonical owner of:

- room IDs
- project IDs
- person IDs
- artifact IDs and URLs
- continuity packet IDs
- approval IDs
- draft and published version IDs
- lease state
- append-only provenance events

`DewDrops` may cache and render these objects, but it should not mint competing canonical IDs for them.

During prototype work, DewDrops may still carry local placeholder IDs or temporary React-state objects. Those are explicitly non-canonical until Butler issues real IDs and version handles.

## Ownership Split

| Topic | Canonical owner | Consumer / secondary owner |
|---|---|---|
| Continuity packets | Butler-os | DewDrops |
| Device pairing and bridge auth | Butler-os | DewDrops consumes |
| Clipboard and device handoff | Butler-os | DewDrops consumes |
| Rooms | Butler-os | DewDrops renders and edits through Butler contracts |
| Boards / spatial orchestration UI | DewDrops | Butler-os may embed later |
| Multi-agent orchestration UX | DewDrops | Butler-os may trigger or resume |
| Publish/version policy | Butler-os | DewDrops respects it |
| Lifegirdle schemas | Shared model | Both consume |
| Artifact blobs and canonical URLs | Butler-os | DewDrops references |

Rooms are canonical in Butler. Identity, lifecycle, membership, policy, and publish semantics live there even when DewDrops renders a richer desktop projection.

## Canonical Object Types

These IDs should be stable across phone, desktop, and future cloud surfaces.

### Room

A room is the canonical context container.

Examples:

- a person room
- a project room
- a company room
- a place room
- a task room
- a conversation room

Required fields:

- `room_id`
- `kind`
- `title`
- `status`
- `metadata`
- `current_draft_version`
- `current_published_version`

### Artifact

An artifact is a durable object stored in or linked from Butler.

Examples:

- note
- screenshot
- draft
- clip
- contract
- image
- transcript

Required fields:

- `artifact_id`
- `room_id`
- `artifact_kind`
- `artifact_url`
- `mime_type`
- `metadata`

### Continuity Packet

A continuity packet is a time-limited transport object between devices or surfaces.

Required fields:

- `packet_id`
- `kind`
- `title`
- `content`
- `source_device`
- `target_device`
- `source_surface`
- `status`
- `lease_owner`
- `lease_expires_at`
- `expires_at`
- `session_id`
- `created_at`
- `updated_at`

Packet status values:

- `pending`
- `claimed`
- `consumed`

## Continuity Protocol V1

Continuity is the first-class handoff layer between phone and desktop.

It is not:

- a hidden clipboard mirror
- a second sync database
- a generic message bus for arbitrary mutation

It is:

- append-only transport
- explicit claim / acknowledge workflow
- tied to Butler sessions and receipts

### Packet Actions

`create`

- producer creates a packet
- packet is visible in the target device inbox

`claim`

- one device claims the packet for active editing
- claim creates a lease with expiry
- another device may not silently overwrite a claimed packet

`ack`

- consumer marks the packet as consumed
- packet remains in provenance history

`expire`

- packets are time-limited
- expired packets remain in history but are not active inbox items

## Versioning And Publishing

Publishing must not overwrite state in place.

Every publish creates a new immutable version.

Required fields for versioned objects:

- `version_id`
- `parent_version_id`
- `room_id`
- `state_kind`
- `created_by`
- `created_at`
- `status`

Version status values:

- `draft`
- `published`
- `archived`

Rules:

- one object may have one active published version
- drafts may branch from published or draft parents
- publish promotes a draft to a new immutable published version
- old published versions remain addressable

## Simultaneous Edit Policy

Do not begin with fully live shared mutable documents.

Use this order:

1. append-only packets
2. explicit lease / claim
3. optimistic concurrency on drafts
4. immutable publish artifacts
5. later, selective real-time collaboration where justified

### Lease Rules

- only one active lease owner per draft object
- lease has explicit expiry
- another editor may fork, wait, or take over only after expiry or release
- claim conflicts return a real conflict, not silent last-write-wins

### Conflict Policy

Allowed last-write-wins:

- viewport
- camera position
- temporary UI layout state

Must not be last-write-wins:

- room content
- publish artifacts
- structured object edits
- task ownership
- approval state

## Artifact URLs

There should be one canonical artifact URL space.

Rules:

- DewDrops stores only references to canonical artifact URLs
- Butler may later move physical storage, but canonical URLs must stay stable
- no duplicate desktop-only and phone-only blob pipelines

## Boards Vs Rooms

- A Butler `room` is the canonical context container with stable identity, policy, and draft/publish lifecycle.
- A DewDrops `board` is a richer spatial projection that may reference one or more `room_id` values.
- Extra layout or view-state may live as Butler-approved artifacts or a future dedicated view-state record, but it must not fork canonical identity.
- DewDrops may render a room however it wants, but it should not create a second room model with separate lifecycle rules.

## DewDrops Contract

`DewDrops` may:

- render rooms spatially
- create orchestration boards
- spawn and manage desktop agent workflows
- package work into continuity packets
- edit Butler-owned objects through Butler contracts

`DewDrops` may not:

- create competing canonical room IDs
- publish directly without Butler version rules
- own a separate continuity protocol
- invent a second approval model

## Lifegirdle Contract

`Lifegirdle` is the persistent context schema layer.

It may define:

- north star / mission objects
- initiative charters
- decision logs
- layer-of-detail views
- specialist-facing schemas
- relationship between rooms, boards, and artifacts

It should not:

- become its own sync service
- become its own handoff layer
- become its own canonical identity authority

## Minimum Shared API Surface

These are the minimum contracts DewDrops should rely on:

- `get_room(room_id)`
- `list_room_artifacts(room_id)`
- `create_continuity_packet(...)`
- `claim_continuity_packet(packet_id, actor_device, lease_minutes)`
- `acknowledge_continuity_packet(packet_id, actor_device, note)`
- `get_current_draft_version(room_id)`
- `save_draft_version(room_id, parent_version_id, payload)`
- `publish_draft_version(version_id)`

The exact transport can evolve, but these semantics should remain stable.

## Mental Model

Use this sentence everywhere:

`Butler-os owns canonical context, continuity, approvals, sync policy, rooms, and publish/version state; DewDrops owns the desktop spatial harness and multi-agent orchestration UX; Lifegirdle is the shared context model both consume, not a third runtime.`

## Immediate Implementation Consequences

Near-term work should follow this order:

1. keep extending Butler continuity packets and leases
2. make rooms canonical in Butler
3. let DewDrops consume Butler room IDs and artifact URLs
4. add versioned draft/publish state before rich team editing
5. only then add deeper collaborative canvas behavior

## Open Decisions

These remain intentionally unresolved and should be tracked against this spec rather than solved independently in multiple repos:

- whether rich board layout lives as a standard Butler artifact or a dedicated Butler-managed view-state record
- whether fork semantics are personal drafts, named branches, or copy-on-write variants
- whether comments are modeled as append-only thread artifacts or a more structured activity stream
