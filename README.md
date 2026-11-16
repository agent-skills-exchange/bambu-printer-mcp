# Bambu printer MCP — status pilot, inactive candidate

Guidance can be read without installing anything. The optional `offline-status`
feature runs one stdio MCP tool, `get_printer_status`, against synthetic cached
data. It does not connect to a printer. No Briar service, other skill, editor,
provider, account or credentials are required. This repository contains a
development candidate, not an admitted skill or accepted release. Status is the
first feature; broader printer capabilities require separate work and authority.

## Setup and offline use

The declared executable profile is Ubuntu 26.04 x86_64, Python 3.14.4. Other
platforms and Python versions have not been qualified. The broader development
prototype was tested on that profile; portable-package acceptance is separate.
Python must already be provisioned. Do not install or alter system packages
just because a manifest names them.

If authorised to install dependencies, from an isolated copy of this package
use an already-installed uv 0.9.10:

```sh
uv --no-config venv --python /usr/bin/python3 .venv
uv --no-config pip sync requirements.lock --python .venv/bin/python --require-hashes --only-binary :all: --default-index https://pypi.org/simple
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/status_service.py --fixture
```

Use a fresh environment; do not overwrite an existing one. uv is installation
tooling, not a runtime dependency. The lock includes transitive dependencies;
installing only the two direct libraries is not an equivalent reproduction.
Downloads use PyPI and files.pythonhosted.org; an already-provisioned offline
environment needs no network or credentials. The last command speaks MCP over
stdin/stdout, not a human terminal UI. An authorised stdio MCP client may launch
that exact command; host configuration and reload steps are not supplied here.
Never treat its synthetic `IDLE` state as real printer status.

## Boundaries and loading

Select guidance for instruction-only work. Select offline-status only when a
synthetic tool is useful; read the manifest and lock then. Do not load unrelated
references or dependencies. Host-supported removal can end tool availability,
but cannot erase instructions/results already read. No automatic installer,
activation hook or runtime authorisation mechanism is included.

The service source also contains an experimental `--mqtt-config` path. It is
outside this manifest's declared features. Do not enable it through this
profile: trusted device TLS identity, credential custody, explicit target and
connection authority, passive A1 mini telemetry compatibility and independent
review remain unresolved. There is no supported camera, print, file, discovery
or raw-command feature. No real-printer destination or credential placeholder
is invented in the manifest.

`service-lock.json` binds the unchanged service and dependency lock; it is not
an admission receipt. Local schema/test success does not prove host integration
or activation. SkillSpector's aggregate completeness flag is false when LLM
analyzers are disabled. The exchange's current static-profile assessor checks
every required static analyzer and file explicitly instead; the local report
passes that compatibility check. This is not verified upstream provenance,
independent review or activation. Keep the original report and findings intact;
do not suppress findings or enable paid enrichment to obtain a pass. Activation
still requires the owning host's complete admission and authority checks.

## Contribution and licensing

Propose changes through development PRs in
https://github.com/agent-skills-exchange/bambu-printer-mcp . Alex retains merges.
Add focused positive/negative tests; retain exact-byte static inspection and
risk-appropriate independent review before activation. Publication is not review
acceptance or permission to operate a printer.
Do not place this package in the Briar core or copy private approval records.

Original package code and documentation are GPL-3.0-or-later; see LICENSE.md.
Third-party dependencies retain their own licences (MCP SDK: MIT;
Paho MQTT: EPL-2.0 OR BSD-3-Clause). Dependency redistribution and licence
obligations still need release review. No dependency wheels are bundled.

Assisted-by: Briar
