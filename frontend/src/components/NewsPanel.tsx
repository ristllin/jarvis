import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { RefreshCw, Newspaper } from 'lucide-react'

interface NewsArticle {
  title: string
  content: string
  source: string
  url: string
  published_at: string
}

interface NewsPanelProps {
  limit?: number
}

export function NewsPanel({ limit = 5 }: NewsPanelProps) {
  const [news, setNews] = useState<NewsArticle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchNews = async () => {
    try {
      setLoading(true)
      const response = await api.getNews()
      setNews(response.news || [])
      setError(null)
    } catch (err) {
      setError('Failed to fetch news')
      console.error('News fetch error:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchNews()
  }, [])

  const refreshNews = () => {
    fetchNews()
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Newspaper size={16} className="text-blue-400" />
          <h3 className="text-sm font-medium text-gray-400">News Monitoring</h3>
        </div>
        <button
          onClick={refreshNews}
          className="text-gray-400 hover:text-gray-300 p-1 rounded"
          disabled={loading}
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>
      {loading && <p className="text-gray-500 text-sm">Loading news...</p>}
      {error && <p className="text-red-500 text-sm">Error: {error}</p>}
      {!loading && !error && news.length === 0 && (
        <p className="text-gray-500 text-sm">No news articles found</p>
      )}
      {!loading && !error && news.length > 0 && (
        <div className="space-y-4">
          {news.slice(0, limit).map((article, index) => (
            <div key={index} className="border-b border-gray-800 pb-3 last:border-b-0">
              <h4 className="text-sm font-medium text-gray-200 hover:text-blue-400 transition">
                <a href={article.url} target="_blank" rel="noopener noreferrer">
                  {article.title}
                </a>
              </h4>
              <p className="text-xs text-gray-400 mt-1">
                {article.source} - {new Date(article.published_at).toLocaleString()}
              </p>
              <p className="text-sm text-gray-300 mt-2 line-clamp-3">
                {article.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}