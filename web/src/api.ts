/**
 * web/src/api.ts
 * Unified API Client for VESTA Web Console.
 */

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8899';

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, options);
  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errObj = await res.json();
      errorDetail = errObj.detail || errObj.error || errorDetail;
    } catch {}
    throw new Error(`API Error (${res.status}): ${errorDetail}`);
  }
  return res.json();
}

// 1. System & Lakehouse
export const getHealth = () => fetchJson<any>('/health');
export const getLakehouseStatus = () => fetchJson<{ status: string; timestamp: string; tables: any[] }>('/api/status');

// 2. Dashboard (CafeF & Vietstock)
export const getDashboardOverview = () => fetchJson<any>('/api/dashboard/overview');
export const getMarketHeatmap = (limit = 60) => fetchJson<any>(`/api/dashboard/heatmap?limit=${limit}`);
export const getForeignFlow = (limit = 20) => fetchJson<any>(`/api/dashboard/foreign_flow?limit=${limit}`);
export const getCorporateEvents = (limit = 30) => fetchJson<any>(`/api/dashboard/events?limit=${limit}`);
export const getMarketNews = (limit = 25) => fetchJson<any>(`/api/dashboard/news?limit=${limit}`);
export const getOhlcv = (symbol: string, limit = 300) => fetchJson<any>(`/api/ohlcv/${symbol}?limit=${limit}`);

// 3. Crawler Pipeline
export interface CrawlParams {
  mode: 'latest' | 'category' | 'all';
  category?: string;
  symbols?: string;
  buffer_first?: boolean;
  delay?: number;
  pages?: number;
}
export const startCrawl = (params: CrawlParams) => fetchJson<any>('/api/crawl/run', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(params),
});
export const stopCrawl = () => fetchJson<any>('/api/crawl/stop', { method: 'POST' });
export const triggerAtomicIngest = () => fetchJson<any>('/api/crawl/atomic_ingest', { method: 'POST' });

// SSE Log Subscriber
export function subscribeCrawlLogs(onMessage: (line: string) => void): () => void {
  const source = new EventSource(`${API_BASE}/events`);
  source.onmessage = (event) => {
    try {
      const line = JSON.parse(event.data);
      onMessage(line);
    } catch {
      onMessage(event.data);
    }
  };
  source.onerror = () => {
    console.warn('[SSE] EventSource disconnected, retrying...');
  };
  return () => source.close();
}

// 4. Preprocessing QA
export const getPreprocessingDAG = () => fetchJson<any>('/api/preprocessing/dag');
export const getF203RegimeMatrix = () => fetchJson<any>('/api/preprocessing/regime_matrix');

// 5. Model Serving & Feedback
export const scoreHeadline = (headline: string, symbol = 'VN30', source = 'cafef') => fetchJson<any>('/api/v1/score_headline', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ headline, symbol, source, skip_cache: true }),
});
export const getDriftStatus = () => fetchJson<any>('/api/v1/drift_status');

// 6. Bot Arena & AI Studio
export const getArenaReport = () => fetchJson<any>('/api/bot-arena/report');
export const getArenaBots = () => fetchJson<any>('/api/bot-arena/bots');
export const chatAIStrategy = (message: string, initialCash = 10000000.0, riskTolerance = 'medium') => fetchJson<any>('/api/bot-arena/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message, initial_cash: initialCash, risk_tolerance: riskTolerance }),
});
