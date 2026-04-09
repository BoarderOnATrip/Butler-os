# aiButler

The AI butler who can manage your life.

`aiButler` is a phone-first AI companion for operators, founders, and small teams. It is being built as an approval-first executive butler with a CRM brain: it keeps relationship context close, helps triage inbound chaos, prepares follow-ups, and can hand work off to a trusted local desktop runtime when it is time to act.

The naming call for this fork is simple:

- public product name: `aiButler`
- domain: `aiButler.me`
- specialist sales / outreach agent: `Mira`

This should not be branded as `Butler Clone`. The clone/avatar concept is a feature layer inside aiButler, not the master brand.

## What makes Butler different

- `Phone-native companion`: the phone is the daily surface for briefings, relationship memory, outreach prompts, and approvals.
- `Trusted desktop operator`: the Mac runtime handles higher-trust capabilities like files, secrets, and supervised computer use.
- `Approval-first by default`: risky actions create approvals and receipts instead of silently doing work in the dark.
- `Local-first architecture`: secrets stay in system keychains, receipts stay on-device, and local runtime remains the control plane.
- `Open build`: the goal is a public repo that people can inspect, extend, and help shape.

## Product direction

The near-term product is not “another chatbot.” It is:

- a phone-based CRM AI companion
- a personal executive assistant
- a relationship-memory layer
- a trusted local operator that can act when you approve it

The first strong user stories are:

- “Who do I owe a reply to today?”
- “Give me my executive briefing.”
- “Draft my next follow-ups.”
- “Handle the desktop work after I approve it.”

## Current surfaces

- [aibutler-core](aibutler-core): Python runtime, approvals, tools, memory, agentic orchestration.
- [desktop](desktop): Tauri desktop shell for onboarding, secure config, and local control.
- [mobile](mobile): Expo / React Native companion surface for phone-first usage.
- [bridge](bridge): desktop bridge between phone and trusted local runtime.
- [landing](landing): public marketing shell.

## What works today

- desktop onboarding for ElevenLabs config, macOS permissions, and Keychain-backed secret storage
- approval-aware local runtime with sessions, tasks, memories, approvals, and receipts
- supervised computer-use tools on macOS
- secure bridge pairing token model for mobile-to-desktop access
- phone UI for pairing, briefings, and quick-action Butler workflows
- Butler-managed OpenClaw operator-stack checks, install flow, and gateway repair from the phone
- optional RTK/OpenClaw integration tooling for shell-output token reduction in agent flows

## What is still in progress

- full mobile voice transport
- richer CRM / relationship-memory flows
- hardened QR pairing and device management
- repeatable packaging and release automation for public installs

## Local development

```bash
# install dependencies
./scripts/setup.sh

# desktop shell
cd desktop && cargo tauri dev

# mobile companion
cd mobile && npx expo start

# local bridge
cd bridge && AIBUTLER_BRIDGE_ALLOW_LAN=1 python server.py
```

For first-run product setup, start the desktop app and use the onboarding flow instead of exporting secrets in the terminal.

## OpenClaw Operator Stack

Butler can now treat OpenClaw as a first-class operator layer instead of a hidden dependency.

The runtime can:

- inspect OpenClaw readiness via `openclaw_status`, either on the local Mac or through a configured VPN endpoint
- install OpenClaw from the official package path via `install_openclaw`
- set `gateway.mode=local` and restart via `openclaw_configure_local_gateway`
- point Butler at a shared private operator fabric via `configure_openclaw_remote_endpoint`
- clear the remote endpoint and fall back to local mode via `clear_openclaw_remote_endpoint`
- install the gateway service via `openclaw_gateway_install`
- restart the gateway via `openclaw_gateway_restart`
- run repair / diagnostics via `openclaw_doctor`

The Android `Act` surface exposes the operator status directly once your Mac is paired, so the phone can bootstrap the local stack or check the shared private stack without dropping back to a terminal.

If you want OpenClaw to live in a shared safe environment behind VPN instead of on each Mac, configure Butler with a VPN-reachable RPC URL:

```bash
cd aibutler-core
python3 -m runtime tool-run \
  --tool-name configure_openclaw_remote_endpoint \
  --args '{"rpc_url":"ws://10.0.0.15:18789/rpc","label":"Shared VPN operator","vpn_required":true}' \
  --approved
```

Butler will then treat that remote endpoint as the active operator plane and simply call out to it when needed.

## Optional RTK Integration

Butler now vendors the RTK rewrite plugin for OpenClaw under [integrations/openclaw/rtk-rewrite](integrations/openclaw/rtk-rewrite).

The runtime can:

- inspect RTK/OpenClaw readiness via `rtk_status`
- preview command rewrites via `rtk_rewrite_preview`
- show RTK gain stats via `rtk_gain_summary`
- install the vendored plugin via `install_rtk_openclaw_plugin`

RTK itself is still an external binary. Install it separately with:

```bash
brew install rtk
```

## Public repo principles

- keep the repo focused on Butler surfaces and runtime code
- keep personal media, keynote decks, and unrelated experiments out of the public tree
- prefer local-first and approval-first defaults over convenience that widens the attack surface
- document what is real, what is experimental, and what still needs work

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## Architecture

See [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Product profile

See [PRODUCT_PROFILE.md](docs/PRODUCT_PROFILE.md).

## GitHub launch copy

See [GITHUB_PROFILE_PACK.md](docs/GITHUB_PROFILE_PACK.md).
