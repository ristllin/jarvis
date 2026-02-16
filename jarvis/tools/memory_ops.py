from jarvis.tools.base import Tool, ToolResult
from jarvis.memory.vector import VectorMemory
from jarvis.memory.models import MemoryEntry


class MemoryWriteTool(Tool):
    name = "memory_write"
    description = "Store a memory in long-term vector memory. Use for important information you want to remember."
    timeout_seconds = 10

    def __init__(self, vector_memory: VectorMemory):
        self.vector = vector_memory

    async def execute(self, content: str, importance: float = 0.5, permanent: bool = False, source: str = "self", **kwargs) -> ToolResult:
        try:
            entry = MemoryEntry(
                content=content,
                importance_score=importance,
                permanent_flag=permanent,
                source=source,
            )
            self.vector.add(entry)
            return ToolResult(success=True, output=f"Memory stored (id={entry.id}, importance={importance})")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "content": {"type": "string", "description": "The content to remember"},
                "importance": {"type": "number", "description": "Importance score 0-1 (default 0.5)"},
                "permanent": {"type": "boolean", "description": "Mark as permanent (never auto-delete)"},
                "source": {"type": "string", "description": "Source label (default: self)"},
            },
            "required": ["content"],
        }


class MemorySearchTool(Tool):
    name = "memory_search"
    description = "Search long-term memory for relevant information."
    timeout_seconds = 10

    def __init__(self, vector_memory: VectorMemory):
        self.vector = vector_memory

    async def execute(self, query: str, n_results: int = 5, **kwargs) -> ToolResult:
        try:
            results = self.vector.search(query, n_results=n_results)
            if not results:
                return ToolResult(success=True, output="No relevant memories found.")

            output_lines = [f"Found {len(results)} relevant memories:\n"]
            for r in results:
                output_lines.append(f"- [{r.get('metadata', {}).get('importance_score', '?')}] {r['content'][:200]}")
            return ToolResult(success=True, output="\n".join(output_lines))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "query": {"type": "string", "description": "Search query"},
                "n_results": {"type": "integer", "description": "Number of results (default 5)"},
            },
            "required": ["query"],
        }
