# Butler UI Doctrine

Date: 2026-04-08

## Core Goal

Butler should feel like it is barely there, while becoming impossible to replace.

That means:

- low-friction enough to live on the phone all day
- useful enough that life and work start routing through it by default
- honest enough that trust compounds instead of collapsing

## Product Thesis

Butler is not a dashboard.

It is a layer that sits on top of the user's real tools, people, files, and conversations.

The UI should therefore optimize for:

1. glanceability
2. capture speed
3. correction speed
4. execution clarity

## The Four Tests

Every phone surface should pass these tests:

1. `Five-second test`
   The user should understand what matters in under five seconds.
2. `One-thumb test`
   The main action should be reachable and obvious on a phone.
3. `Trust test`
   The user should see what Butler knows, what Butler inferred, and what Butler is unsure about.
4. `Replacement test`
   The surface should connect memory, follow-up, and execution in a way a normal notes app or CRM cannot.

## The Five Phone Modes

### Home

The living brief.

- what matters now
- who needs you
- what is waiting
- what Butler is unsure about
- the best next recipes

### Capture

The fastest ingress path in the product.

- voice
- note
- photo
- share sheet
- phone-native metadata

The user should not be asked to file first and think later.

### Review

The trust layer.

- pending items
- promoted / deferred / dismissed state
- visible ambiguity
- correction before learning

### People

The relationship memory surface.

- people
- follow-ups
- linked context
- graph and timeline views
- CRM projection without CRM feel

### Act

The execution surface.

- pairing
- approvals
- voice
- recipes
- delegation
- receipts

## Flow Transitions

Mode changes should be intentional.

- capture should flow into review
- review promotion should flow into people
- recipes and delegation should surface act
- successful pairing should return the user to the living brief

The user should feel guided, not trapped inside one long screen.

## Invisible But Irreplaceable

### Invisible

- one obvious next action per screen
- minimal chrome
- LIFO by default
- progressive disclosure instead of dense control panels
- useful without long setup

### Irreplaceable

- remembers what the user forgot
- connects people, places, messages, files, and actions
- preserves provenance
- improves when corrected
- can actually execute work

## Skins, Modules, Recipes

### Module

A reusable surface block.

Examples:

- brief
- capture
- review
- relationships
- graph
- journal
- approvals
- act

### Recipe

A reusable workflow.

Examples:

- Daily Brief
- Pipeline Sweep
- Inbox Triage
- Bring Butler Online

### Skin

A bundle that selects:

- visual treatment
- default mode
- featured modules
- visible modes
- recipe emphasis
- tone and posture

Skins should change emphasis, not truth.

## Initial Reference Skins

### Raven

- calm
- executive
- context-first
- balanced across memory and action

### Founder

- momentum-first
- pipeline heavy
- follow-up and inbox pressure surfaced earlier

### Butler Lite

- minimal
- capture, review, act
- fewer modules, same canonical runtime

## Design Rules

- no screen should feel like enterprise software by default
- no critical action should disappear into chat history
- no ambiguity should be silently resolved without review
- no skin should fork the data model
- no recipe should hide what it touched

## Implementation Rule

The runtime stays canonical.

Skins and modules only change:

- what is visible
- what is prioritized
- what is one tap away

They do not change:

- truth
- approvals
- provenance
- receipts
- canonical context storage

## Immediate Build Consequence

The mobile app should stop growing as one long prototype scroll.

Every new feature should land in exactly one of:

- Home
- Capture
- Review
- People
- Act

The visible navigation should derive from the active skin's enabled modules and the current runtime state, so a lighter skin feels lighter and unavailable surfaces disappear until pairing or platform capability makes them real.

If it does not belong cleanly to one of those, the feature is not ready yet.
