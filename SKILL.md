---
name: bambu-status-pilot
description: Evaluate the inactive A1 mini status-only MCP package, its optional dependencies, cached telemetry and connection prerequisites. Not permission to operate a printer.
license: GPL-3.0-or-later
metadata:
  agent-skills-exchange-dependencies: dependencies.json
---

# Bambu status pilot (inactive)

This package is a development example, not an installed printer integration.
Read `dependencies.json` for the guidance and offline-status features.
Read `README.md` only for setup, tests or the unsupported connection boundary.
The package includes `scripts/status_service.py`, a narrow stdio service exposing
only `get_printer_status`, with no tool arguments, HTTP API or print commands.
Its optional Python dependencies are hash-pinned in `requirements.lock`.
The offline fixture is synthetic data, not hardware. There is no Briar runtime,
other skill, editor or model-provider dependency.

For real-printer status, require a separately reviewed, pinned implementation,
local credential handling, explicit connection authority and tested listener
containment first. Real-printer mode is outside this manifest's supported profile;
the experimental CLI is not an approved connection path.

The exposed tool reads a cache; it does not poll or request printer updates.
Report connection state, data age and stale fields alongside progress. A partial
update must not disguise older cached fields as current. Subscribe-only operation
and verified TLS have passed fake-peer tests; A1 mini compatibility is unproven.

Use an explicit status allowlist. Do not expose file,
print-control, raw-command or credential-management tools. Camera is a separate,
disabled feature because streams may create listeners and disclose images.

Loading a tool or reading this skill grants no permission. On unload, deny new
calls first, disconnect and stop owned resources, remove tool exposure and verify
the result. Removing tools cannot erase instructions or results from chat history.

Assisted-by: Briar
