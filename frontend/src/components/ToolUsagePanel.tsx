import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { ToolSchema } from '../types'

export function ToolUsagePanel() {
  const [tools, setTools] = useState<ToolSchema[]>([])

  useEffect(() => {
    api.getTools().then((data) => setTools(data.tools || []))
  }, [])

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Tool System</h2>
      <p className="text-sm text-gray-400">{tools.length} tools registered</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {tools.map((tool) => (
          <div key={tool.name} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="font-medium text-jarvis-400">{tool.name}</h3>
            <p className="text-sm text-gray-400 mt-1">{tool.description}</p>
            {tool.parameters && (
              <div className="mt-3">
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Parameters</p>
                <div className="space-y-1">
                  {Object.entries(tool.parameters).map(([key, val]: [string, any]) => (
                    <div key={key} className="text-xs">
                      <span className="text-cyan-400 font-mono">{key}</span>
                      <span className="text-gray-600 ml-2">{val?.type || 'any'}</span>
                      {val?.description && <span className="text-gray-500 ml-2">— {val.description}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
