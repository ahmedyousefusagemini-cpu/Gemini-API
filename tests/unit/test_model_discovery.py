"""Unit tests for `gemini_webapi.utils.model_discovery`.

These tests exercise the parser against the golden `otAQ7b` fixture plus a
set of malformed and partial payloads to verify the tolerance contract.
"""

from __future__ import annotations

import pytest

from gemini_webapi.utils.model_discovery import (
    ParsedMode,
    ParsedUserStatus,
    ThinkingLevelSpec,
    build_alias_map,
    parse_otaq7b_response,
    resolve_alias,
)


class TestGoldenFixture:
    def test_returns_parsed_user_status(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        assert isinstance(result, ParsedUserStatus)
        assert len(result.modes) == 3

    def test_extracts_canonical_hex_ids(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        hexes = [m.hex_id for m in result.modes]
        assert hexes == [
            "8c46e95b1a07cecc",
            "56fdd199312815e2",
            "e6fa609c3fa255c0",
        ]

    def test_extracts_display_names(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        names = {m.hex_id: m.display_name for m in result.modes}
        assert names["8c46e95b1a07cecc"] == "3.1 Flash-Lite"
        assert names["56fdd199312815e2"] == "3.5 Flash"
        assert names["e6fa609c3fa255c0"] == "3.1 Pro"

    def test_captures_aliased_legacy_ids(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        by_hex = result.by_hex
        assert "fbb127bbb056c959" in by_hex["8c46e95b1a07cecc"].aliased_legacy_ids
        assert "9d8ca3786ebdfbea" in by_hex["e6fa609c3fa255c0"].aliased_legacy_ids

    def test_capability_subset_is_int_tuple(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        pro = result.by_hex["e6fa609c3fa255c0"]
        assert pro.capability_subset == (4, 5, 6, 8)
        assert all(isinstance(x, int) for x in pro.capability_subset)

    def test_selected_mode_picks_first_selected(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        assert result.selected_mode is not None
        assert result.selected_mode.hex_id == "8c46e95b1a07cecc"

    def test_thinking_levels_attached_to_pro(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        pro = result.by_hex["e6fa609c3fa255c0"]
        assert len(pro.thinking_levels) == 2
        assert pro.thinking_levels[0] == ThinkingLevelSpec(
            level_id=1, label="Standard", description="Best for most questions"
        )
        assert pro.thinking_levels[1].level_id == 2
        assert pro.thinking_levels[1].label == "Extended"

    def test_modes_without_policy_have_empty_thinking_levels(
        self, otaq7b_sample
    ) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        flash_lite = result.by_hex["8c46e95b1a07cecc"]
        assert flash_lite.thinking_levels == ()

    def test_thinking_policy_name_preserved(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        assert result.thinking_policy_name == "v3p2_pro_policy"

    def test_icon_url_extracted(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        assert all(m.icon_url and m.icon_url.startswith("https://") for m in result.modes)


class TestAliasMap:
    def test_canonical_hexes_map_to_themselves(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        alias_map = result.alias_map()
        for mode in result.modes:
            assert alias_map[mode.hex_id] == mode.hex_id

    def test_legacy_hex_resolves_to_canonical(self, otaq7b_sample) -> None:
        result = parse_otaq7b_response(otaq7b_sample)
        alias_map = result.alias_map()
        # `fbb127bbb056c959` is listed under BOTH Flash-Lite and Flash. The
        # first-write-wins rule means it resolves to Flash-Lite (parsed first).
        assert alias_map["fbb127bbb056c959"] == "8c46e95b1a07cecc"
        assert alias_map["9d8ca3786ebdfbea"] == "e6fa609c3fa255c0"

    def test_unknown_hex_returns_input(self) -> None:
        assert resolve_alias({"a": "b"}, "zzz") == "zzz"

    def test_build_alias_map_from_list_input(self) -> None:
        modes = [
            ParsedMode(
                hex_id="canon",
                aliased_legacy_ids=("old1", "old2"),
            ),
        ]
        m = build_alias_map(modes)
        assert m == {"canon": "canon", "old1": "canon", "old2": "canon"}


class TestTolerance:
    def test_non_list_payload_returns_empty(self) -> None:
        assert parse_otaq7b_response(None) == ParsedUserStatus()
        assert parse_otaq7b_response({"unexpected": "dict"}) == ParsedUserStatus()
        assert parse_otaq7b_response("string") == ParsedUserStatus()
        assert parse_otaq7b_response(42) == ParsedUserStatus()

    def test_empty_list_returns_empty(self) -> None:
        result = parse_otaq7b_response([])
        assert result.modes == ()
        assert result.thinking_policy_name == ""

    def test_missing_modes_slot_is_safe(self) -> None:
        result = parse_otaq7b_response([1, 2, 3])
        assert result.modes == ()

    def test_mode_entry_without_hex_is_skipped(self) -> None:
        payload = [None] * 17
        payload[16] = [
            [],
            [None, "name"],
            ["abc123", "Good"],
        ]
        result = parse_otaq7b_response(payload)
        assert [m.hex_id for m in result.modes] == ["abc123"]
        assert result.modes[0].short_name == "Good"

    def test_list_shaped_thinking_policy(self) -> None:
        payload = [None] * 26
        payload[16] = [
            [
                "deadbeef",
                "X",
                "",
                [],
                None,
                None,
                [],
                False,
                "",
                0,
                "",
                "X",
                "",
                None,
                None,
                None,
                "",
                0,
                None,
                "",
            ]
        ]
        payload[25] = [
            "list_shape_policy",
            [["deadbeef", [[1, "S", "std"], [2, "E", "ext"]]]],
        ]
        result = parse_otaq7b_response(payload)
        assert result.thinking_policy_name == "list_shape_policy"
        assert result.by_hex["deadbeef"].thinking_levels == (
            ThinkingLevelSpec(1, "S", "std"),
            ThinkingLevelSpec(2, "E", "ext"),
        )

    @pytest.mark.parametrize("bad_policy", [None, 42, "abc", [], {}])
    def test_unknown_thinking_policy_shapes(self, bad_policy) -> None:
        payload = [None] * 26
        payload[16] = []
        payload[25] = bad_policy
        result = parse_otaq7b_response(payload)
        assert result.modes == ()
        assert isinstance(result.thinking_policy_name, str)
