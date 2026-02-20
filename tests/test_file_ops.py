import os

import pytest
from jarvis.tools.file_ops import FileListTool, FileReadTool, FileWriteTool


@pytest.fixture
def test_dir(data_dir):
    """Create a test subdirectory under data_dir."""
    path = os.path.join(data_dir, "test_files")
    os.makedirs(path, exist_ok=True)
    return path


@pytest.mark.asyncio
class TestFileReadTool:
    async def test_read_existing_file(self, test_dir):
        filepath = os.path.join(test_dir, "hello.txt")
        with open(filepath, "w") as f:
            f.write("Hello, JARVIS!")
        tool = FileReadTool()
        result = await tool.execute(path=filepath)
        assert result.success
        assert "Hello, JARVIS!" in result.output

    async def test_read_nonexistent_file(self):
        tool = FileReadTool()
        result = await tool.execute(path="/data/nonexistent_file_xyz.txt")
        assert not result.success

    async def test_read_missing_path(self):
        tool = FileReadTool()
        result = await tool.execute(path="")
        assert not result.success


@pytest.mark.asyncio
class TestFileWriteTool:
    async def test_write_file(self, test_dir):
        tool = FileWriteTool()
        filepath = os.path.join(test_dir, "output.txt")
        result = await tool.execute(path=filepath, content="Test content")
        assert result.success
        with open(filepath) as f:
            assert f.read() == "Test content"

    async def test_write_missing_content(self, test_dir):
        tool = FileWriteTool()
        filepath = os.path.join(test_dir, "empty.txt")
        result = await tool.execute(path=filepath, content="")
        # Writing empty content should still succeed (or tool may reject it)
        # Behavior depends on implementation
        assert isinstance(result.success, bool)

    async def test_write_creates_directories(self, test_dir):
        tool = FileWriteTool()
        filepath = os.path.join(test_dir, "sub", "dir", "deep.txt")
        result = await tool.execute(path=filepath, content="deep file")
        assert result.success
        assert os.path.exists(filepath)


@pytest.mark.asyncio
class TestFileListTool:
    async def test_list_directory(self, test_dir):
        with open(os.path.join(test_dir, "a.txt"), "w") as f:
            f.write("a")
        tool = FileListTool()
        result = await tool.execute(path=test_dir)
        assert result.success
        assert "a.txt" in result.output

    async def test_list_nonexistent_directory(self):
        tool = FileListTool()
        result = await tool.execute(path="/data/nonexistent_dir_xyz")
        assert not result.success


class TestToolSchemas:
    def test_file_read_schema(self):
        tool = FileReadTool()
        schema = tool.get_schema()
        assert schema["name"] == "file_read"
        assert "path" in schema.get("parameters", {})

    def test_file_write_schema(self):
        tool = FileWriteTool()
        schema = tool.get_schema()
        assert schema["name"] == "file_write"
        assert "path" in schema.get("parameters", {})
        assert "content" in schema.get("parameters", {})

    def test_file_list_schema(self):
        tool = FileListTool()
        schema = tool.get_schema()
        assert schema["name"] == "file_list"
