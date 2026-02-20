import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api/client'
import type { ChatMessage, WSMessage } from '../types'
import { Send, Bot, User, Loader2 } from 'lucide-react'

interface ChatPanelProps {
  lastMessage: WSMessage | null
}

export function ChatPanel({ lastMessage }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const sendingRef = useRef(false)

  useEffect(() => {
    api.getChatHistory(50).then((data) => {
      setMessages(data.messages || [])
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  useEffect(() => {
    if (lastMessage?.type === 'chat_message' && !sendingRef.current) {
      api.getChatHistory(50).then((data) => {
        setMessages(data.messages || [])
      }).catch(() => {})
    }
  }, [lastMessage])

  const send = async () => {
    if (!input.trim() || sending) return
    const text = input.trim()
    setInput('')

    const tempMsg: ChatMessage = { role: 'creator', content: text, timestamp: new Date().toISOString() }
    setMessages((prev) => [...prev, tempMsg])

    setSending(true)
    sendingRef.current = true
    try {
      const response = await api.sendChat(text)
      if (response.reply) {
        const reply: ChatMessage = {
          role: 'jarvis',
          content: response.reply,
          timestamp: new Date().toISOString(),
          metadata: { model: response.model, provider: response.provider, tokens_used: response.tokens_used },
        }
        setMessages((prev) => [...prev, reply])
      } else {
        api.getChatHistory(50).then((data) => {
          setMessages(data.messages || [])
        }).catch(() => {})
      }
    } catch (err) {
      console.error('Chat send error:', err)
      setMessages((prev) => [
        ...prev,
        { role: 'jarvis', content: 'Error: Failed to get response. Please try again.', timestamp: new Date().toISOString() },
      ])
    } finally {
      setSending(false)
      sendingRef.current = false
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-white">Chat with JARVIS</h2>
        <p className="text-xs text-gray-500">Direct communication channel with your AI entity</p>
      </div>

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-auto space-y-3 pr-2 mb-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-gray-600">
            <div className="text-center">
              <Bot size={48} className="mx-auto mb-3 text-gray-700" />
              <p className="text-sm">No messages yet. Say hello to JARVIS.</p>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'creator' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'jarvis' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-jarvis-900 flex items-center justify-center mt-1">
                <Bot size={16} className="text-jarvis-400" />
              </div>
            )}
            <div
              className={`max-w-[75%] rounded-xl px-4 py-2.5 ${
                msg.role === 'creator'
                  ? 'bg-blue-600 text-white rounded-br-sm'
                  : 'bg-gray-800 text-gray-200 rounded-bl-sm border border-gray-700'
              }`}
            >
              {msg.role === 'jarvis' ? (
                <div className="markdown-body text-sm">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
              ) : (
                <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
              )}
              <div className="flex items-center gap-2 mt-1">
                {msg.timestamp && (
                  <span className="text-[10px] opacity-50">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </span>
                )}
                {msg.role === 'jarvis' && msg.metadata?.model != null && (
                  <span className="text-[10px] opacity-40">
                    {String(msg.metadata.model)}
                  </span>
                )}
              </div>
            </div>
            {msg.role === 'creator' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-800 flex items-center justify-center mt-1">
                <User size={16} className="text-blue-300" />
              </div>
            )}
          </div>
        ))}
        {sending && (
          <div className="flex gap-3 justify-start">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-jarvis-900 flex items-center justify-center">
              <Bot size={16} className="text-jarvis-400" />
            </div>
            <div className="bg-gray-800 border border-gray-700 rounded-xl rounded-bl-sm px-4 py-3">
              <Loader2 size={16} className="animate-spin text-jarvis-400" />
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-gray-800 pt-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message to JARVIS..."
            rows={2}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 resize-none focus:outline-none focus:ring-1 focus:ring-jarvis-400 focus:border-jarvis-400"
          />
          <button
            onClick={send}
            disabled={!input.trim() || sending}
            className="p-2.5 rounded-lg bg-jarvis-600 hover:bg-jarvis-500 disabled:opacity-40 disabled:hover:bg-jarvis-600 transition-colors"
          >
            <Send size={18} className="text-white" />
          </button>
        </div>
        <p className="text-[10px] text-gray-600 mt-1">Press Enter to send, Shift+Enter for new line</p>
      </div>
    </div>
  )
}

/* Custom components for react-markdown to style within the dark chat bubble */
const markdownComponents = {
  h1: ({ children, ...props }: any) => <h1 className="text-lg font-bold mt-3 mb-1 text-white" {...props}>{children}</h1>,
  h2: ({ children, ...props }: any) => <h2 className="text-base font-bold mt-3 mb-1 text-white" {...props}>{children}</h2>,
  h3: ({ children, ...props }: any) => <h3 className="text-sm font-bold mt-2 mb-1 text-white" {...props}>{children}</h3>,
  p: ({ children, ...props }: any) => <p className="mb-2 last:mb-0 leading-relaxed" {...props}>{children}</p>,
  ul: ({ children, ...props }: any) => <ul className="list-disc list-inside mb-2 space-y-0.5" {...props}>{children}</ul>,
  ol: ({ children, ...props }: any) => <ol className="list-decimal list-inside mb-2 space-y-0.5" {...props}>{children}</ol>,
  li: ({ children, ...props }: any) => <li className="leading-relaxed" {...props}>{children}</li>,
  strong: ({ children, ...props }: any) => <strong className="font-semibold text-white" {...props}>{children}</strong>,
  em: ({ children, ...props }: any) => <em className="italic text-gray-300" {...props}>{children}</em>,
  a: ({ children, href, ...props }: any) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-jarvis-400 underline hover:text-jarvis-300" {...props}>{children}</a>
  ),
  code: ({ children, className, ...props }: any) => {
    const isBlock = className?.includes('language-')
    if (isBlock) {
      return (
        <div className="my-2 rounded-lg overflow-hidden">
          <div className="bg-gray-950 px-3 py-1 text-[10px] text-gray-500 border-b border-gray-800">
            {className?.replace('language-', '') || 'code'}
          </div>
          <pre className="bg-gray-950 p-3 overflow-x-auto">
            <code className="text-xs text-gray-300 font-mono" {...props}>{children}</code>
          </pre>
        </div>
      )
    }
    return <code className="bg-gray-900 text-jarvis-400 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>{children}</code>
  },
  pre: ({ children, ...props }: any) => <>{children}</>,
  blockquote: ({ children, ...props }: any) => (
    <blockquote className="border-l-2 border-jarvis-600 pl-3 my-2 text-gray-400 italic" {...props}>{children}</blockquote>
  ),
  hr: (props: any) => <hr className="border-gray-700 my-3" {...props} />,
  table: ({ children, ...props }: any) => (
    <div className="overflow-x-auto my-2">
      <table className="min-w-full text-xs border border-gray-700 rounded" {...props}>{children}</table>
    </div>
  ),
  thead: ({ children, ...props }: any) => <thead className="bg-gray-900" {...props}>{children}</thead>,
  th: ({ children, ...props }: any) => <th className="px-2 py-1 text-left text-gray-400 font-medium border-b border-gray-700" {...props}>{children}</th>,
  td: ({ children, ...props }: any) => <td className="px-2 py-1 border-b border-gray-800" {...props}>{children}</td>,
}
