# Upgrade report — `feat/auto-detect-models-v3`

This branch begins a multi-PR effort to keep `gemini-webapi` compatible with
the May-2026 Gemini web UI rollout (`boq_assistant-bard-web-server_20260511.16_p18`).
The new web UI ships three default modes — **3.1 Flash-Lite**, **3.5 Flash**,
**3.1 Pro** — and a per-mode thinking-level policy (Standard / Extended).

This PR lands the pure, dependency-free pieces. Wiring the new parser into
`client.py` and rebuilding the model-header jspb shape are deferred to a
follow-up PR (see **Deferred** below) so we can land the parser, its tests,
and the tooling baseline first — keeping each step independently reviewable.

## What shipped in this PR

| Area | Change |
| --- | --- |
| `pyproject.toml` | Added Python 3.13 classifier, `[dev]` extras (pytest, pytest-asyncio, ruff, black, pyright), and full ruff/black/pyright/pytest configuration. Pointed `Repository`/`Issues` URLs at this fork; kept upstream under `Upstream`. |
| `src/gemini_webapi/utils/model_discovery.py` | New pure parser for the BardFrontend `otAQ7b` RPC response, returning a `ParsedUserStatus` with every mode, alias mapping, and the per-mode thinking-level policy. Plain dataclasses — no pydantic dep. |
| `src/gemini_webapi/utils/__init__.py` | Re-exported `parse_otaq7b_response`, `ParsedMode`, `ParsedUserStatus`, `ThinkingLevelSpec`, `build_alias_map`, `resolve_alias`. |
| `tests/conftest.py`, `tests/fixtures/otaq7b_response.json` | Golden three-mode fixture captured from the live HAR plus the session-scoped loader. |
| `tests/unit/test_model_discovery.py` | 18 unit tests: canonical hex extraction, display-name parsing, alias-map ordering, tolerance against `None`/dict/short-list payloads, both dict- and list-shaped thinking-policy variants. |
| `CHANGELOG.md` | Keep-a-Changelog file documenting the above. |

## What is deferred (and why)

### `.github/workflows/*.yml` — blocked on a permission scope

The `.github/workflows/pypi-publish.yml` had marketplace-tag drift
(`actions/checkout@v6`, `upload-artifact@v7.0.1`, `download-artifact@v8.0.1`,
`pypa/gh-action-pypi-publish@v2` — none of those tags exist on the marketplace,
so any tag push would have failed before producing a wheel). The release
workflow body contained a corrupted Notion-compressed placeholder rather
than a valid GHA expression. A new `ci.yml` (ruff + black --check + pyright +
pytest matrix on 3.11/3.12/3.13) is drafted and ready to push.

**All three workflow file writes returned `403 Resource not accessible by integration`**
from the Notion MCP GitHub App. GitHub treats `.github/workflows/*` under a
separate `Workflows: read and write` permission scope; `Contents: write`
alone (the scope currently granted to this app) is not enough.

**To unblock**: GitHub → Settings → GitHub Apps → Notion MCP → Configure →
grant **Repository permissions → Workflows: Read and write** on this repo.
A follow-up PR will then pin all three workflows in one commit.

### `src/gemini_webapi/constants.py` v3 header builder

The live request payload now uses a 17-element jspb header
(`x-goog-ext-525001261-jspb`) with capability flags `[4,5,6,8]` at index 8
and a per-session `client_uuid` at index 16. The old 12-element header is
rejected by the server. Sibling headers also changed:
`x-goog-ext-73010989-jspb` went from `"[0]"` to `"[]"`, and
`x-goog-ext-73010990-jspb` is no longer sent at all.

This change must land together with:

- A `ThinkingLevel(IntEnum)` enum (values `1` = Standard, `2` = Extended) and
  wiring at `inner_req_list[24]` in `client._generate`.
- A `LEGACY_MODEL_ID_ALIASES` map (e.g. `9d8ca3786ebdfbea` →
  `e6fa609c3fa255c0`, `fbb127bbb056c959` → `56fdd199312815e2`,
  `5bf011840784117a` / `e051ce1aa80aa576` → `8c46e95b1a07cecc`).
- A fix for the `Model.from_dict` `UNSPECIFIED` mutation: today the
  fallthrough path mutates `cls.UNSPECIFIED.model_ids` on miss, which means
  any subsequent `from_dict` call sees the previously-missed ID.
- Renaming `GRPC.DEEP_RESEARCH_CAPS` → `GRPC.GET_MODE_CAPS` (with a
  deprecated alias) since the `aPya6c` RPC is now used for every mode, not
  just deep research.

These are intentionally not in this PR because they all depend on the
parser's contract (which this PR ships and pins with tests). Once merged,
the follow-up PR can be written against the verified parser shape.

### `src/gemini_webapi/client.py` integration

`_fetch_user_status` already reads `part_body[15]` for modes positionally and
still works — the indices have not moved — but it does not yet:

- Build an alias map from `model_data[6]`.
- Persist a per-session `client_uuid` and feed it into the new header
  builder.
- Surface `thinking_levels` on `AvailableModel`.
- Apply alias resolution in `_resolve_model_by_name` so user input like
  `"9d8ca3786ebdfbea"` continues to work post-cutover.

`client.py` is ~83 KB and rewriting it whole in a single PR is risky.
Treating this as its own PR keeps the diff reviewable.

### `src/gemini_webapi/exceptions.py`

`class TimeoutError(GeminiError)` shadows the builtin `TimeoutError`, which
bites callers that `except TimeoutError` expecting the stdlib semantics. The
planned rename is `class GeminiTimeoutError(GeminiError)` with
`TimeoutError = GeminiTimeoutError` retained as a deprecated alias for one
minor release. Trivial change but pulled into the same follow-up as the
constants refactor so the `CHANGELOG` documents one breaking-rename window.

### CLI `--thinking-level`

Depends on the constants `ThinkingLevel` enum, so it ships with the
constants refactor.

## Verification

- All new tests are deterministic, offline, and run under the `not live`
  marker selector that CI uses by default.
- `pytest tests/unit -q -m 'not live'` should pass on 3.11 / 3.12 / 3.13
  once `pyproject.toml` is installed via `pip install -e '.[dev]'`.
- The parser is purely positional and tolerant: every test for a malformed
  payload asserts a non-raising, sensible-default outcome.

## Compatibility

No existing public symbols are removed or renamed in this PR. The new
symbols are additive (`gemini_webapi.utils.parse_otaq7b_response` and
friends). Existing callers continue to work unchanged.
