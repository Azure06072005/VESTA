import React, { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import type { IChartApi } from 'lightweight-charts';
import { BarChart3, Calendar, Newspaper, RefreshCw, TrendingUp } from 'lucide-react';
import { getCorporateEvents, getDashboardOverview, getForeignFlow, getMarketHeatmap, getMarketNews, getOhlcv } from '../api';

export const DashboardPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<any>(null);
  const [heatmapItems, setHeatmapItems] = useState<any[]>([]);
  const [foreignFlow, setForeignFlow] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('FPT');
  const [sizeBy, setSizeBy] = useState<'market_cap' | 'trading_val'>('trading_val');
  const [selectedSector, setSelectedSector] = useState<string>('ALL');

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);

  const loadAllData = async () => {
    setLoading(true);
    try {
      const [ov, hm, ff, ev, nw] = await Promise.all([
        getDashboardOverview().catch(() => null),
        getMarketHeatmap(80).catch(() => ({ data: [] })),
        getForeignFlow(20).catch(() => ({ data: [] })),
        getCorporateEvents(20).catch(() => ({ data: [] })),
        getMarketNews(20).catch(() => ({ data: [] })),
      ]);
      setOverview(ov);
      setHeatmapItems(hm.data || []);
      setForeignFlow(ff.data || []);
      setEvents(ev.data || []);
      setNews(nw.data || []);
    } catch (e) {
      console.error('Error loading dashboard data', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, []);

  // Lightweight charts candlestick series
  useEffect(() => {
    if (!chartContainerRef.current) return;

    if (chartInstanceRef.current) {
      chartInstanceRef.current.remove();
      chartInstanceRef.current = null;
    }

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 340,
      layout: {
        background: { color: '#0d0d1c' },
        textColor: '#c8c4bc',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
      },
      crosshair: {
        vertLine: { color: '#00e5c3', width: 1 },
        horzLine: { color: '#00e5c3', width: 1 },
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: true,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22A366',
      downColor: '#D6483F',
      borderVisible: false,
      wickUpColor: '#22A366',
      wickDownColor: '#D6483F',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: 'rgba(0, 229, 195, 0.3)',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    getOhlcv(selectedSymbol, 180)
      .then((res) => {
        if (res && res.bars && res.bars.length > 0) {
          candleSeries.setData(res.bars);
          volumeSeries.setData(
            res.bars.map((b: any) => ({
              time: b.time,
              value: b.volume,
              color: b.close >= b.open ? 'rgba(34, 163, 102, 0.4)' : 'rgba(214, 72, 63, 0.4)',
            }))
          );
        }
      })
      .catch((err) => console.warn('Could not load OHLCV for chart', err));

    chartInstanceRef.current = chart;

    const handleResize = () => {
      if (chartContainerRef.current && chartInstanceRef.current) {
        chartInstanceRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartInstanceRef.current) {
        chartInstanceRef.current.remove();
        chartInstanceRef.current = null;
      }
    };
  }, [selectedSymbol]);

  // Heatmap Filtering
  const sectors = ['ALL', ...Array.from(new Set(heatmapItems.map((item) => item.sector))).filter(Boolean)];
  const filteredHeatmap = selectedSector === 'ALL'
    ? heatmapItems
    : heatmapItems.filter((item) => item.sector === selectedSector);

  const getPriceBadgeClass = (state: string) => {
    switch (state) {
      case 'ceiling': return 'badge-ceiling';
      case 'floor': return 'badge-floor';
      case 'up': return 'badge-up';
      case 'down': return 'badge-down';
      default: return 'badge-ref';
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HEADER & ACTION BAR */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--cream)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TrendingUp size={20} color="var(--teal)" />
            Bảng Điều Khiển Toàn Cảnh Thị Trường (CafeF & Vietstock)
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
            Dữ liệu tổng hợp HOSE, HNX, UPCOM, HĐTL VN30F1M, Khối ngoại và Sự kiện doanh nghiệp
          </p>
        </div>
        <button className="btn-ghost" onClick={loadAllData} disabled={loading}>
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Đang cập nhật...' : 'Làm mới dữ liệu'}
        </button>
      </div>

      {/* MARKET BREADTH BAR */}
      {overview && overview.market_summary && (
        <div className="panel" style={{ padding: '14px 18px', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <span className="mono" style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--cream3)' }}>
              Độ rộng thị trường (Market Breadth) — Ngày: {overview.latest_trading_date || 'Mới nhất'}
            </span>
            <div style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
              <span style={{ color: 'var(--vn-up)', fontWeight: 700 }}>▲ {overview.market_summary.advancing} Tăng</span>
              <span style={{ color: 'var(--vn-ceiling)', fontWeight: 700 }}>★ {overview.market_summary.ceiling} Trần</span>
              <span style={{ color: 'var(--vn-ref)', fontWeight: 700 }}>■ {overview.market_summary.unchanged} TC</span>
              <span style={{ color: 'var(--vn-down)', fontWeight: 700 }}>▼ {overview.market_summary.declining} Giảm</span>
              <span style={{ color: 'var(--vn-floor)', fontWeight: 700 }}>◆ {overview.market_summary.floor} Sàn</span>
            </div>
          </div>
          {/* Progress bar visual */}
          <div style={{ display: 'flex', height: '8px', borderRadius: '2px', overflow: 'hidden', background: 'var(--bg3)' }}>
            <div style={{ flex: overview.market_summary.ceiling || 1, background: 'var(--vn-ceiling)' }} title="Trần" />
            <div style={{ flex: overview.market_summary.advancing || 10, background: 'var(--vn-up)' }} title="Tăng" />
            <div style={{ flex: overview.market_summary.unchanged || 5, background: 'var(--vn-ref)' }} title="Tham chiếu" />
            <div style={{ flex: overview.market_summary.declining || 10, background: 'var(--vn-down)' }} title="Giảm" />
            <div style={{ flex: overview.market_summary.floor || 1, background: 'var(--vn-floor)' }} title="Sàn" />
          </div>
        </div>
      )}

      {/* MAIN LAYOUT: HEATMAP + CANDLESTICK CHART */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '20px', marginBottom: '24px' }}>
        {/* Market Treemap Heatmap */}
        <div className="panel">
          <div className="panel-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span className="panel-title"><BarChart3 size={15} color="var(--teal)" /> Bản Đồ Nhiệt Thị Trường</span>
              <select value={selectedSector} onChange={(e) => setSelectedSector(e.target.value)} style={{ padding: '3px 8px', fontSize: '11px' }}>
                {sectors.map((sec) => (
                  <option key={sec} value={sec}>{sec === 'ALL' ? 'Tất cả các ngành' : sec}</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                className={`btn-ghost btn-sm ${sizeBy === 'trading_val' ? 'btn-main' : ''}`}
                onClick={() => setSizeBy('trading_val')}
              >
                Theo GTGD
              </button>
              <button
                className={`btn-ghost btn-sm ${sizeBy === 'market_cap' ? 'btn-main' : ''}`}
                onClick={() => setSizeBy('market_cap')}
              >
                Theo Vốn Hóa
              </button>
            </div>
          </div>

          <div style={{ padding: '16px', maxHeight: '420px', overflowY: 'auto' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))', gap: '6px' }}>
              {filteredHeatmap.slice(0, 54).map((stock) => {
                const isSelected = selectedSymbol === stock.symbol;
                return (
                  <div
                    key={stock.symbol}
                    onClick={() => setSelectedSymbol(stock.symbol)}
                    className={getPriceBadgeClass(stock.price_state)}
                    style={{
                      padding: '10px',
                      borderRadius: 'var(--rad)',
                      cursor: 'pointer',
                      textAlign: 'center',
                      border: isSelected ? '1.5px solid var(--teal)' : undefined,
                      boxShadow: isSelected ? '0 0 10px rgba(0, 229, 195, 0.4)' : undefined,
                      transition: 'var(--transition)',
                    }}
                  >
                    <div className="sans" style={{ fontSize: '13px', fontWeight: 800 }}>
                      {stock.symbol}
                    </div>
                    <div className="mono tabular" style={{ fontSize: '12px', fontWeight: 700, margin: '2px 0' }}>
                      {stock.last_price ? stock.last_price.toLocaleString('vi-VN') : '-'}
                    </div>
                    <div className="mono tabular" style={{ fontSize: '10px', fontWeight: 700 }}>
                      {stock.pct_change > 0 ? '+' : ''}{stock.pct_change.toFixed(1)}%
                    </div>
                    <div className="mono" style={{ fontSize: '9px', opacity: 0.75, marginTop: '2px' }}>
                      {stock.trading_value_billion ? `${stock.trading_value_billion.toFixed(0)} Tỷ` : ''}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Real-time Candlestick Chart */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">
              Biểu Đồ Nến: <span style={{ color: 'var(--teal)' }}>{selectedSymbol}</span>
            </span>
            <div style={{ display: 'flex', gap: '6px' }}>
              {['VN30', 'FPT', 'VCB', 'HPG', 'SSI', 'VNM'].map((sym) => (
                <button
                  key={sym}
                  className={`btn-ghost btn-sm ${selectedSymbol === sym ? 'btn-main' : ''}`}
                  onClick={() => setSelectedSymbol(sym)}
                  style={{ padding: '2px 8px', fontSize: '10px' }}
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>
          <div style={{ padding: '12px' }}>
            <div ref={chartContainerRef} style={{ width: '100%', height: '340px' }} />
          </div>
        </div>
      </div>

      {/* BOTTOM SECTION: 3 PANELS (FOREIGN FLOW, CORPORATE EVENTS, FINANCIAL NEWS) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
        {/* Panel 1: Foreign Net Flow */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title"><TrendingUp size={14} color="var(--gold)" /> Dòng Tiền Khối Ngoại (20 Phiên)</span>
          </div>
          <div style={{ padding: '12px', maxHeight: '280px', overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Ngày</th>
                  <th>Mua (Tỷ)</th>
                  <th>Bán (Tỷ)</th>
                  <th>Ròng (Tỷ)</th>
                </tr>
              </thead>
              <tbody>
                {foreignFlow.slice(0, 10).map((r, i) => (
                  <tr key={i}>
                    <td className="mono">{r.date}</td>
                    <td className="mono tabular">{r.buy_billion?.toFixed(1) || '-'}</td>
                    <td className="mono tabular">{r.sell_billion?.toFixed(1) || '-'}</td>
                    <td className="mono tabular" style={{ fontWeight: 700, color: (r.net_billion || 0) >= 0 ? 'var(--vn-up)' : 'var(--vn-down)' }}>
                      {(r.net_billion || 0) >= 0 ? '+' : ''}{r.net_billion?.toFixed(1) || '0.0'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Panel 2: Corporate Events */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title"><Calendar size={14} color="var(--violet)" /> Sự Kiện Quyền & ĐHĐCĐ (F006)</span>
          </div>
          <div style={{ padding: '12px', maxHeight: '280px', overflowY: 'auto' }}>
            {events.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--cream3)' }}>Không có sự kiện mới</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {events.slice(0, 8).map((ev, i) => (
                  <div key={i} style={{ padding: '8px 10px', background: 'var(--bg3)', borderRadius: 'var(--rad)', borderLeft: '2px solid var(--violet)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                      <span className="sans" style={{ fontWeight: 700, color: 'var(--cream)' }}>{ev.symbol}</span>
                      <span className="mono" style={{ fontSize: '10px', color: 'var(--gold)' }}>{ev.ex_date}</span>
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--cream2)' }}>{ev.event_title || ev.event_type}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Panel 3: Financial News Stream */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title"><Newspaper size={14} color="var(--teal)" /> Tin Tức Tài Chính Real-Time</span>
          </div>
          <div style={{ padding: '12px', maxHeight: '280px', overflowY: 'auto' }}>
            {news.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--cream3)' }}>Đang nạp tin tức CafeF...</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {news.slice(0, 7).map((item, i) => (
                  <div key={i} style={{ borderBottom: '0.5px solid var(--border)', paddingBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
                      <span className="badge badge-teal" style={{ fontSize: '9px' }}>{item.symbol || 'VN-INDEX'}</span>
                      <span className="mono" style={{ fontSize: '10px', color: 'var(--cream3)' }}>{item.published_at?.slice(0, 16)}</span>
                    </div>
                    <a
                      href={item.source_url || '#'}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: '11px', color: 'var(--cream)', textDecoration: 'none', lineHeight: 1.5, display: 'block' }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--teal)')}
                      onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--cream)')}
                    >
                      {item.headline}
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
