"""Dynamic model-discovery parser for the Gemini web app `otAQ7b` RPC.

The Gemini web UI no longer exposes a stable list of mode hex IDs: the May 2026
release (`boq_assistant-bard-web-server_20260511.16_p18`) ships three default
modes (`3.1 Flash-Lite`, `3.5 Flash`, `3.1 Pro`) and a per-mode
thinking-level policy. New mode hexes are introduced server-side without any
client deployment, and legacy hexes are silently aliased into the new canonical
IDs.

This module parses the raw `otAQ7b` response payload into a structured
``ParsedUserStatus`` so callers can build an `AvailableModel` registry without
any hard-coded knowledge of mode IDs.

The parser is intentionally:

* **Pure** — no I/O, no logging, deterministic.
* **Tolerant** — every slot is optional; missing/None values yield safe defaults
  rather than raising.
* **Free of pydantic** — plain dataclasses keep it cheap in hot paths.

Positional indices are documented inline and were verified against a HAR
captured on 2026-05-20 from `gemini.google.com`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "ParsedMode",
    "ParsedUserStatus",
    "ThinkingLevelSpec",
    "parse_otaq7b_response",
    "build_alias_map",
    "resolve_alias",
]

# ---------------------------------------------------------------------------
# Top-level response slot indices (see HAR 2026-05-20).
# ---------------------------------------------------------------------------
_TOP_MODES_INDEX = 16
_TOP_THINKING_POLICY_INDEX = 25

# ---------------------------------------------------------------------------
# Mode entry slot indices.
# ---------------------------------------------------------------------------
_MODE_HEX_ID = 0
_MODE_SHORT_NAME = 1
_MODE_TAGLINE = 2
_MODE_CAPABILITY_SUBSET = 3
_MODE_ALIASED_LEGACY_IDS = 6
_MODE_IS_SELECTED = 7
_MODE_KEY = 8
_MODE_TIER = 9
_MODE_FAMILY_LABEL = 10
_MODE_DISPLAY_NAME = 11
_MODE_DESCRIPTION = 12
_MODE_SUBKEY = 16
_MODE_SORT_ORDER = 17
_MODE_ICON_TUPLE = 18
_MODE_CANONICAL_DISPLAY_NAME = 19


@dataclass(frozen=True)
class ThinkingLevelSpec:
    """A single thinking-level entry from the per-mode policy block.

    Attributes correspond to the positional triple `[id, label, description]`
    that the policy emits for each level.
    """

    level_id: int
    label: str
    description: str


@dataclass(frozen=True)
class ParsedMode:
    """A single mode (model) entry parsed out of the `otAQ7b` response.

    `hex_id` is the canonical Gemini mode identifier (e.g. ``e6fa609c3fa255c0``).
    `aliased_legacy_ids` lists hex IDs that previously identified separate
    models but now silently resolve to this mode — keep them for
    backward-compatible user input.
    """

    hex_id: str
    short_name: str = ""
    display_name: str = ""
    canonical_display_name: str = ""
    description: str = ""
    family_label: str = ""
    tagline: str = ""
    tier: int = 0
    mode_key: str = ""
    mode_subkey: str = ""
    sort_order: int = 0
    is_selected: bool = False
    capability_subset: tuple[int, ...] = ()
    aliased_legacy_ids: tuple[str, ...] = ()
    icon_url: str | None = None
    thinking_levels: tuple[ThinkingLevelSpec, ...] = ()

    @property
    def all_known_ids(self) -> tuple[str, ...]:
        """Canonical hex plus every aliased legacy hex."""
        return (self.hex_id, *self.aliased_legacy_ids)


@dataclass(frozen=True)
class ParsedUserStatus:
    """The structured form of the `otAQ7b` RPC body."""

    modes: tuple[ParsedMode, ...] = ()
    thinking_policy_name: str = ""
    raw_thinking_policy: Any = None

    @property
    def selected_mode(self) -> ParsedMode | None:
        for mode in self.modes:
            if mode.is_selected:
                return mode
        return None

    @property
    def by_hex(self) -> dict[str, ParsedMode]:
        return {mode.hex_id: mode for mode in self.modes}

    def alias_map(self) -> dict[str, str]:
        """Map every known hex (canonical or aliased) to its canonical hex."""
        return build_alias_map(self.modes)


# ---------------------------------------------------------------------------
# Parser entry points.
# ---------------------------------------------------------------------------


def parse_otaq7b_response(payload: Any) -> ParsedUserStatus:
    """Parse the decoded `otAQ7b` response array.

    Args:
        payload: The decoded jspb response body. Expected to be a list whose
            top-level shape matches the documented schema. Other types yield
            an empty :class:`ParsedUserStatus` rather than raising.

    Returns:
        A :class:`ParsedUserStatus` describing every mode and the per-mode
        thinking-level policy. Unknown or malformed slots are skipped
        defensively; the result is always non-None.
    """
    if not isinstance(payload, list):
        return ParsedUserStatus()

    modes_raw = _safe_index(payload, _TOP_MODES_INDEX, default=[])
    thinking_raw = _safe_index(payload, _TOP_THINKING_POLICY_INDEX, default=None)

    thinking_levels_by_hex, thinking_policy_name = _parse_thinking_policy(thinking_raw)

    modes: list[ParsedMode] = []
    if isinstance(modes_raw, list):
        for entry in modes_raw:
            mode = _parse_mode_entry(entry, thinking_levels_by_hex)
            if mode is not None:
                modes.append(mode)

    return ParsedUserStatus(
        modes=tuple(modes),
        thinking_policy_name=thinking_policy_name,
        raw_thinking_policy=thinking_raw,
    )


def build_alias_map(modes: tuple[ParsedMode, ...] | list[ParsedMode]) -> dict[str, str]:
    """Return ``{any_hex: canonical_hex}`` for every parsed mode.

    Canonical hexes map to themselves so callers can do a single lookup
    without branching on whether the input is already canonical.
    """
    out: dict[str, str] = {}
    for mode in modes:
        out[mode.hex_id] = mode.hex_id
        for legacy in mode.aliased_legacy_ids:
            # First write wins so a legacy ID listed under multiple modes keeps
            # the earlier (typically newer, selected) canonical target.
            out.setdefault(legacy, mode.hex_id)
    return out


def resolve_alias(alias_map: dict[str, str], hex_id: str) -> str:
    """Return the canonical hex for ``hex_id`` or the input itself if unknown."""
    return alias_map.get(hex_id, hex_id)


# ---------------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------------


def _parse_mode_entry(
    entry: Any,
    thinking_levels_by_hex: dict[str, tuple[ThinkingLevelSpec, ...]],
) -> ParsedMode | None:
    if not isinstance(entry, list):
        return None
    hex_id = _safe_index(entry, _MODE_HEX_ID, default="")
    if not isinstance(hex_id, str) or not hex_id:
        return None

    aliased = _safe_index(entry, _MODE_ALIASED_LEGACY_IDS, default=[]) or []
    capability = _safe_index(entry, _MODE_CAPABILITY_SUBSET, default=[]) or []
    icon_tuple = _safe_index(entry, _MODE_ICON_TUPLE, default=None)
    icon_url = icon_tuple[0] if isinstance(icon_tuple, list) and icon_tuple else None

    return ParsedMode(
        hex_id=hex_id,
        short_name=_as_str(_safe_index(entry, _MODE_SHORT_NAME)),
        display_name=_as_str(_safe_index(entry, _MODE_DISPLAY_NAME)),
        canonical_display_name=_as_str(
            _safe_index(entry, _MODE_CANONICAL_DISPLAY_NAME)
        ),
        description=_as_str(_safe_index(entry, _MODE_DESCRIPTION)),
        family_label=_as_str(_safe_index(entry, _MODE_FAMILY_LABEL)),
        tagline=_as_str(_safe_index(entry, _MODE_TAGLINE)),
        tier=_as_int(_safe_index(entry, _MODE_TIER)),
        mode_key=_as_str(_safe_index(entry, _MODE_KEY)),
        mode_subkey=_as_str(_safe_index(entry, _MODE_SUBKEY)),
        sort_order=_as_int(_safe_index(entry, _MODE_SORT_ORDER)),
        is_selected=bool(_safe_index(entry, _MODE_IS_SELECTED, default=False)),
        capability_subset=tuple(int(x) for x in capability if isinstance(x, (int, float))),
        aliased_legacy_ids=tuple(str(x) for x in aliased if isinstance(x, str)),
        icon_url=icon_url if isinstance(icon_url, str) else None,
        thinking_levels=thinking_levels_by_hex.get(hex_id, ()),
    )


def _parse_thinking_policy(
    raw: Any,
) -> tuple[dict[str, tuple[ThinkingLevelSpec, ...]], str]:
    """Best-effort extraction of `(per_mode_levels, policy_name)`.

    The live policy is itself a jspb structure whose exact shape is still
    rolling out. We accept either:

    * a dict with keys ``policy_name`` and ``levels_by_mode``:
      ``{ mode_hex: [[level_id, label, desc], ...] }``
    * a list whose first element is the policy name and whose second element
      is a list of `[mode_hex, [level_entries]]` pairs.

    Unknown shapes yield ``({}, "")`` rather than raising.
    """
    if isinstance(raw, dict):
        policy_name = _as_str(raw.get("policy_name"))
        levels_by_mode = raw.get("levels_by_mode") or {}
        out: dict[str, tuple[ThinkingLevelSpec, ...]] = {}
        if isinstance(levels_by_mode, dict):
            for hex_id, entries in levels_by_mode.items():
                specs = _parse_level_entries(entries)
                if isinstance(hex_id, str) and specs:
                    out[hex_id] = specs
        return out, policy_name

    if isinstance(raw, list) and raw:
        policy_name = _as_str(raw[0]) if isinstance(raw[0], str) else ""
        per_mode_raw = raw[1] if len(raw) > 1 else None
        out2: dict[str, tuple[ThinkingLevelSpec, ...]] = {}
        if isinstance(per_mode_raw, list):
            for pair in per_mode_raw:
                if (
                    isinstance(pair, list)
                    and len(pair) >= 2
                    and isinstance(pair[0], str)
                ):
                    specs = _parse_level_entries(pair[1])
                    if specs:
                        out2[pair[0]] = specs
        return out2, policy_name

    return {}, ""


def _parse_level_entries(entries: Any) -> tuple[ThinkingLevelSpec, ...]:
    if not isinstance(entries, list):
        return ()
    out: list[ThinkingLevelSpec] = []
    for entry in entries:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        level_id = _as_int(entry[0])
        label = _as_str(entry[1])
        description = _as_str(entry[2]) if len(entry) >= 3 else ""
        if level_id and label:
            out.append(
                ThinkingLevelSpec(
                    level_id=level_id,
                    label=label,
                    description=description,
                )
            )
    return tuple(out)


def _safe_index(seq: Any, idx: int, default: Any = None) -> Any:
    if isinstance(seq, list) and 0 <= idx < len(seq):
        return seq[idx]
    return default


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_int(value: Any) -> int:
    if isinstance(value, bool):  # bool is a subclass of int; treat False as 0 cleanly.
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0
