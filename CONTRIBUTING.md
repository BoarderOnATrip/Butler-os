# Contributing

aiButler is being opened in public, but the standard should stay high. The goal is not to pile up demos. The goal is to ship a trustworthy phone + desktop Butler runtime that can actually act on behalf of a user.

## Principles

- local-first before cloud-first
- approval-first before silent automation
- typed runtime contracts before prompt sprawl
- secure defaults before convenience defaults

## Workspace

- `aibutler-core/`: runtime, tools, approvals, memory
- `desktop/`: Tauri shell and onboarding
- `mobile/`: phone companion
- `bridge/`: token-gated phone-to-desktop bridge

## Setup

```bash
./scripts/setup.sh
```

## Before opening a PR

Run the relevant checks:

```bash
python3 -m py_compile aibutler-core/voice.py aibutler-core/runtime/__main__.py bridge/server.py
cd desktop && npm run build && cargo check
cd mobile && npm run typecheck
```

## PR expectations

- keep changes scoped
- explain user impact, not just file diffs
- call out security implications for bridge, secrets, auth, or computer-use work
- do not add remote full-access paths
- do not commit personal media, cloned voice assets, or private strategy docs
