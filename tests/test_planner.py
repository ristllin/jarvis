"""Tests for the planner module — _ensure_list, parsing, loop detection.

These tests mock heavy deps (chromadb) that aren't available locally outside Docker.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# Stub chromadb before planner imports try to pull it in
if "chromadb" not in sys.modules:
    _mock_chroma = types.ModuleType("chromadb")
    _mock_chroma.PersistentClient = MagicMock
    sys.modules["chromadb"] = _mock_chroma

from jarvis.core.planner import Planner, _ensure_list


class TestEnsureList:
    def test_none(self):
        assert _ensure_list(None) == []

    def test_list(self):
        assert _ensure_list([1, 2, 3]) == [1, 2, 3]

    def test_empty_list(self):
        assert _ensure_list([]) == []

    def test_dict(self):
        result = _ensure_list({"a": 1, "b": 2})
        assert result == [1, 2]

    def test_empty_dict(self):
        assert _ensure_list({}) == []

    def test_string(self):
        assert _ensure_list("goal") == ["goal"]

    def test_int(self):
        assert _ensure_list(42) == [42]


class TestParsePlan:
    @pytest.fixture
    def planner(self):
        from jarvis.memory.working import WorkingMemory

        router = MagicMock()
        wm = WorkingMemory()
        vm = MagicMock()
        return Planner(router, wm, vm)

    def test_parse_valid_json(self, planner):
        content = '{"thinking": "test", "actions": [{"tool": "web_search", "parameters": {"query": "hello"}}]}'
        plan = planner._parse_plan(content)
        assert plan["thinking"] == "test"
        assert len(plan["actions"]) == 1

    def test_parse_markdown_fenced(self, planner):
        content = '```json\n{"thinking": "fenced", "actions": []}\n```'
        plan = planner._parse_plan(content)
        assert plan["thinking"] == "fenced"

    def test_parse_json_in_text(self, planner):
        content = 'Here is my plan: {"thinking": "embedded", "actions": []} some extra text'
        plan = planner._parse_plan(content)
        assert plan["thinking"] == "embedded"

    def test_parse_garbage_returns_fallback(self, planner):
        content = "This is not JSON at all"
        plan = planner._parse_plan(content)
        assert plan["actions"] == []
        assert "This is not JSON" in plan["thinking"]

    def test_parse_truncated_json(self, planner):
        content = '{"thinking": "truncated", "actions": []'
        plan = planner._parse_plan(content)
        assert plan["thinking"] == "truncated"

    def test_unwrap_nested_plan(self, planner):
        inner = '{"thinking": "inner", "actions": [{"tool": "file_read", "parameters": {"path": "/test"}}]}'
        outer = {"thinking": inner, "actions": []}
        plan = planner._unwrap_nested(outer)
        assert len(plan["actions"]) == 1


class TestLoopDetection:
    @pytest.fixture
    def planner(self):
        from jarvis.memory.working import WorkingMemory

        router = MagicMock()
        wm = WorkingMemory()
        vm = MagicMock()
        return Planner(router, wm, vm)

    def test_no_stuck_initially(self, planner):
        assert planner._check_stuck_loop() is None

    def test_detects_repeated_actions(self, planner):
        for _ in range(3):
            planner._track_action_sig({"actions": [{"tool": "file_write", "parameters": {"path": "/test"}}]})
        warning = planner._check_stuck_loop()
        assert warning is not None
        assert "stuck" in warning.lower()

    def test_no_false_positive_on_varied_actions(self, planner):
        planner._track_action_sig({"actions": [{"tool": "web_search", "parameters": {}}]})
        planner._track_action_sig({"actions": [{"tool": "file_read", "parameters": {}}]})
        planner._track_action_sig({"actions": [{"tool": "code_exec", "parameters": {}}]})
        assert planner._check_stuck_loop() is None

    def test_detects_idle_loop(self, planner):
        for _ in range(5):
            planner._track_action_sig({"actions": []})
        warning = planner._check_stuck_loop()
        assert warning is not None
        assert "no actions" in warning.lower()
