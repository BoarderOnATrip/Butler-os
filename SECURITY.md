# Security Policy

aiButler can hold secrets and perform supervised actions on a user's machine. Security is part of the product, not a cleanup task.

## Reporting

Until a dedicated disclosure inbox exists, report security issues privately to `tyler@aibutler.me`. Do not open public GitHub issues for vulnerabilities involving auth bypass, bridge exposure, secret leakage, or silent privilege escalation.

## Core rules

- remote surfaces must never enable `full-access`
- bridge access must be authenticated when exposed beyond loopback
- secrets should live in OS credential stores where possible
- risky actions must respect approvals and leave receipts

## Current boundaries

- the bridge is intended for trusted local-network pairing, not internet exposure
- desktop onboarding is ahead of the mobile UX
- this local workspace contains experimental material that should not be included in the public repo export
