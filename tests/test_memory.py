import os
import json
import pytest
from jarvis.memory.blob import BlobStorage
from jarvis.memory.vector import VectorMemory
from jarvis.memory.working import WorkingMemory
from jarvis.memory.models import MemoryEntry


class TestBlobStorage:
    def test_store_and_read(self, data_dir):
        blob = BlobStorage(data_dir)
        blob.store("test_event", "Hello world", {"key": "value"})
        blob.store("test_event", "Second entry")

        entries = blob.read_recent(limit=10)
        assert len(entries) >= 2
        assert entries[0]["content"] == "Second entry"
        assert entries[1]["content"] == "Hello world"

    def test_stats(self, data_dir):
        blob = BlobStorage(data_dir)
        blob.store("test", "content")
        stats = blob.get_stats()
        assert stats["total_files"] >= 1
        assert stats["total_size_bytes"] > 0


class TestVectorMemory:
    def test_add_and_search(self, data_dir):
        vector = VectorMemory(data_dir)
        vector.connect()

        entry = MemoryEntry(
            content="Python is a programming language",
            importance_score=0.8,
            source="test",
        )
        vector.add(entry)

        results = vector.search("programming language", n_results=1)
        assert len(results) >= 1
        assert "Python" in results[0]["content"]

    def test_mark_permanent(self, data_dir):
        vector = VectorMemory(data_dir)
        vector.connect()

        entry = MemoryEntry(content="Important memory", source="test")
        vector.add(entry)
        vector.mark_permanent(entry.id)

        all_data = vector.collection.get(ids=[entry.id], include=["metadatas"])
        meta = all_data["metadatas"][0]
        assert meta.get("permanent_flag") is True

    def test_get_stats(self, data_dir):
        vector = VectorMemory(data_dir)
        vector.connect()
        stats = vector.get_stats()
        assert "total_entries" in stats


class TestWorkingMemory:
    def test_add_and_get_messages(self):
        wm = WorkingMemory()
        wm.set_system_prompt("You are JARVIS.")
        wm.add_message("user", "Hello")
        wm.add_message("assistant", "Hi there")

        messages = wm.get_messages_for_llm()
        assert messages[0]["role"] == "system"
        assert "JARVIS" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"

    def test_inject_memories(self):
        wm = WorkingMemory()
        wm.set_system_prompt("System")
        wm.inject_memories(["Memory A", "Memory B"])

        messages = wm.get_messages_for_llm()
        assert "Memory A" in messages[0]["content"]
        assert "Memory B" in messages[0]["content"]

    def test_context_trimming(self):
        wm = WorkingMemory()
        wm.set_system_prompt("System")
        for i in range(1000):
            wm.add_message("user", f"Message {i} " * 100)

        context = wm.get_context()
        assert context.total_tokens_estimate <= 130_000

    def test_clear(self):
        wm = WorkingMemory()
        wm.add_message("user", "Hello")
        wm.clear()
        assert len(wm.messages) == 0
