# Changelog

All notable changes to this fork are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Dynamic model discovery** (`gemini_webapi.utils.model_discovery`): pure,
  tolerant parser for the BardFrontend `otAQ7b` RPC response. Returns a
  `ParsedUserStatus` containing every mode (canonical hex, display names,
  tier, capability subset, aliased legacy hexes) plus the per-mode
  thinking-level policy. See `tests/unit/test_model_discovery.py` for the
  exhaustive contract.
- **Alias resolution helpers** (`build_alias_map`, `resolve_alias`) so callers
  can keep accepting legacy model IDs while routing them to whatever the
  server currently considers canonical (e.g. `9d8ca3786ebdfbea` →
  `e6fa609c3fa255c0`).
- **CI tooling configuration** in `pyproject.toml`: declared Python 3.13
  support, added a `[dev]` extras set (pytest, pytest-asyncio, ruff, black,
  pyright), and configured ruff/black/pyright/pytest. Repository/Issues URLs
  now point at this fork; the upstream URL is preserved under `Upstream`.
- **Golden fixture** at `tests/fixtures/otaq7b_response.json` captured from
  the 2026-05-20 web UI build
  `boq_assistant-bard-web-server_20260511.16_p18`. Tests run fully offline.

### Deferred (tracked in `REPORT.md`)

- `.github/workflows/*.yml` pins and the new `ci.yml` cannot land in this PR
  because the connected GitHub App lacks the `Workflows: read and write`
  permission scope. Grant that scope and a follow-up PR can pin the actions.
- `src/gemini_webapi/constants.py` v3 header builder (17-element jspb with
  capability flags `[4,5,6,8]` and `client_uuid`), `ThinkingLevel(IntEnum)`,
  and `LEGACY_MODEL_ID_ALIASES` map. This touches a wide surface and is
  blocked behind landing the parser first so it can be wired against the
  exact shapes the parser already validates.
- `src/gemini_webapi/client.py` integration: building a per-session model
  registry from the parsed status, propagating `client_uuid` into the
  header builder, surfacing `thinking_levels` on `AvailableModel`.
- `src/gemini_webapi/exceptions.py` rename `TimeoutError` →
  `GeminiTimeoutError` (with a backward-compatible alias).
- CLI `--thinking-level` flag.

### Notes for upstream rebase

The `Repository` and `Issues` URLs were repointed at this fork so PyPI
release metadata stops linking back to upstream. If you rebase this branch
onto a newer upstream release, drop the `[project.urls].Upstream` field if
it collides with upstream's own metadata.
