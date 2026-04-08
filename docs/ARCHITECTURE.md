# aiButler.me Architecture

Detailed next-phase product architecture:

- `docs/CONTEXT_ENGINE_AND_RAVEN_ARCHITECTURE_2026-04-07.md`
- `docs/BUTLER_OS_ROADMAP_2026-04-08.md`

## Product shape

aiButler is being built as a two-surface system:

- `phone`: the companion surface for relationship context, briefings, approvals, and quick actions
- `desktop`: the trusted execution surface for secrets, files, supervised computer use, and local receipts

That split is the core product decision. The phone should feel immediate. The desktop should feel powerful and careful.

## Runtime stack

```text
phone app (Expo / React Native)
        |
        | pairing token + local network
        v
desktop bridge (FastAPI)
        |
        v
ButlerRuntime (Python)
        |
        +-- typed tool registry
        +-- approvals
        +-- tasks
        +-- memories / RAG
        +-- receipts
        +-- plugin hooks
        +-- agentic orchestration
```

## Core packages

### `aibutler-core/`

The local runtime and policy engine.

- sessions with permission modes
- approval requests and resolution
- memories and receipts
- tool registry for files, secrets, life data, and computer use
- agentic orchestration and plugin hooks

### `desktop/`

The Tauri shell that makes Butler usable by normal people.

- first-run onboarding
- config persistence in `~/.aibutler/config.json`
- secure launch path into the local runtime
- system settings deep-links for macOS permissions

### `mobile/`

The phone companion.

- pairing to the desktop bridge
- quick actions for briefings and outreach planning
- future voice transport surface
- live visibility into delegated tool activity

### `bridge/`

The boundary between phone and trusted desktop runtime.

- localhost by default
- optional LAN mode for phone pairing
- pairing token required for privileged routes
- remote full-access elevation blocked

## Security posture

- secrets live in the OS keychain, not plaintext config
- bridge pairing is explicit, not open by default
- remote clients can execute through standard approvals only
- full-access stays a trusted local desktop capability
- runtime writes receipts and security events for later inspection

## Near-term build priorities

1. finish mobile voice transport
2. improve QR/device pairing UX
3. deepen CRM / relationship-memory flows
4. tighten release packaging and public contributor onboarding

## Public-launch constraints

Before public GitHub launch, keep the repo scoped to Butler code and docs. Personal audio, keynote files, unrelated research dumps, and abandoned experiments should stay out of the exported tree even if they remain in the local workspace.
