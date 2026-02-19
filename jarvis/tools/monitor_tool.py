import asyncio
import time
from jarvis.tools.base import Tool
# from jarvis.tools.registry import ToolRegistry
from jarvis.observability.logger import get_logger

log = get_logger('monitor_tool')

class MonitorTool(Tool):
    registry: 'ToolRegistry'  # type: ToolRegistry
    def __init__(self, registry: 'ToolRegistry', check_interval: int = 60):
        self.registry = registry
        self.check_interval = check_interval

    async def check_tools(self):
        while True:
            for tool_name, tool in self.registry.tools.items():
                try:
                    # Attempt to execute a simple command to check if the tool is functional
                    result = await tool.execute(parameters={})
                    if not result.success:
                        log.error(f'Tool {tool_name} is non-functional: {result.error}')
                except Exception as e:
                    log.error(f'Tool {tool_name} encountered an error: {str(e)}')
            await asyncio.sleep(self.check_interval)
            log.info('Monitoring tools...')

    def start_monitoring(self):
        asyncio.create_task(self.check_tools())