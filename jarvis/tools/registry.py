import asyncio
import time
from jarvis.tools.base import Tool, ToolResult
from jarvis.tools.web_search import WebSearchTool
from jarvis.tools.web_browse import WebBrowseTool
from jarvis.tools.code_exec import CodeExecTool
from jarvis.tools.file_ops import FileReadTool, FileWriteTool, FileListTool
from jarvis.tools.git_ops import GitTool
from jarvis.tools.memory_ops import MemoryWriteTool, MemorySearchTool
from jarvis.tools.budget_query import BudgetQueryTool
from jarvis.tools.llm_config import LLMConfigTool
from jarvis.tools.self_modify import SelfModifyTool
from jarvis.tools.coding_agent import CodingAgentTool
from jarvis.tools.resource_manager import ResourceManagerTool
from jarvis.tools.send_email import SendEmailTool
from jarvis.tools.skills import SkillsTool
from jarvis.tools.http_request import HttpRequestTool
from jarvis.tools.env_manager import EnvManagerTool
from jarvis.tools.memory_config import MemoryConfigTool
from jarvis.tools.news_monitor import NewsMonitorTool
from jarvis.tools.credit_monitor import CreditMonitorTool
from jarvis.tools.coingecko import CoinGeckoTool
from jarvis.tools.self_analysis import SelfAnalysisTool
from jarvis.memory.vector import VectorMemory
from jarvis.memory.working import WorkingMemory
from jarvis.safety.validator import SafetyValidator
from jarvis.observability.logger import get_logger

# Delayed import to avoid circular dependency
from jarvis.tools.monitor_tool import MonitorTool

log = get_logger("tools")

class ToolRegistry:
    """Discovers, registers, and executes tools with logging and safety checks."""

    def __init__(self, vector_memory: VectorMemory, validator: SafetyValidator,
                budget_tracker=None, llm_router=None, blob_storage=None, working: WorkingMemory = None):
        self.tools: dict[str, Tool] = {}
        self.validator = validator
        self.blob = blob_storage
        self._register_defaults(vector_memory, budget_tracker, llm_router, blob_storage, working)
        self.monitor_tool = MonitorTool(self)
        self.monitor_tool.start_monitoring()

    def _register_defaults(self, vector_memory: VectorMemory,
                           budget_tracker=None, llm_router=None, blob_storage=None, working: WorkingMemory = None):
        default_tools = [
            WebSearchTool(),
            WebBrowseTool(),
            CodeExecTool(),
            FileReadTool(),
            FileWriteTool(),
            FileListTool(),
            GitTool(),
            MemoryWriteTool(vector_memory),
            MemorySearchTool(vector_memory),
            SelfModifyTool(blob_storage=blob_storage),
            SendEmailTool(),
            SkillsTool(),
            HttpRequestTool(),
            EnvManagerTool(),
            NewsMonitorTool(),
            CoinGeckoTool(),
        ]
        if working:
            default_tools.append(MemoryConfigTool(working))
        if budget_tracker:
            default_tools.append(BudgetQueryTool(budget_tracker))
            default_tools.append(ResourceManagerTool(budget_tracker))
            default_tools.append(CreditMonitorTool(budget_tracker=budget_tracker))
        if llm_router:
            default_tools.append(LLMConfigTool(llm_router))
            default_tools.append(CodingAgentTool(llm_router, blob_storage=blob_storage))
            default_tools.append(SelfAnalysisTool(llm_router=llm_router, budget_tracker=budget_tracker))
        for tool in default_tools:
            self.tools[tool.name] = tool
            log.info("tool_registered", tool=tool.name)

    def register(self, tool: Tool):
        self.tools[tool.name] = tool
        log.info("tool_registered", tool=tool.name)

    async def execute(self, tool_name: str, parameters: dict) -> ToolResult:
        if tool_name not in self.tools:
            return ToolResult(success=False, output="", error=f"Unknown tool: {tool_name}")

        # Safety check
        is_safe, reason = self.validator.validate_action({
            "tool": tool_name,
            "parameters": parameters,
        })
        if not is_safe:
            log.warning("tool_blocked", tool=tool_name, reason=reason)
            return ToolResult(success=False, output="", error=f"Blocked by safety: {reason}")

        tool = self.tools[tool_name]
        start = time.time()

        try:
            result = await asyncio.wait_for(
                tool.execute(**parameters),
                timeout=tool.timeout_seconds,
            )
            duration_ms = int((time.time() - start) * 1000)

            # Sanitize output
            result.output = self.validator.sanitize_output(result.output)

            # Record in blob storage
            if self.blob:
                self.blob.store(
                    event_type="tool_execution",
                    content=f"Tool: {tool_name}\nParams: {str(parameters)[:500]}\nSuccess: {result.success}\nOutput: {result.output[:1000]}",
                    metadata={
                        "tool": tool_name,
                        "success": result.success,
                        "duration_ms": duration_ms,
                        "error": result.error,
                    },
                )

            log.info("tool_executed",
                     tool=tool_name, success=result.success,
                     duration_ms=duration_ms)
            return result

        except asyncio.TimeoutError:
            log.error("tool_timeout", tool=tool_name, timeout=tool.timeout_seconds)
            return ToolResult(success=False, output="", error=f"Tool timed out after {tool.timeout_seconds}s")
        except Exception as e:
            log.error("tool_error", tool=tool_name, error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    def get_tool_schemas(self) -> list[dict]:
        return [tool.get_schema() for tool in self.tools.values()]

    def get_tool_names(self) -> list[str]:
        return list(self.tools.keys())