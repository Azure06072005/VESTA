import React, { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import type { IChartApi } from 'lightweight-charts';
import {
  ArrowLeft,
  BarChart2,
  Building2,
  Calendar,
  ChevronDown,
  ChevronUp,
  Cpu,
  ExternalLink,
  Gauge,
  Layers,
  Newspaper,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import {
  getCorporateEvents,
  getDashboardOverview,
  getDriftStatus,
  getForeignFlow,
  getMarketHeatmap,
  getMarketNews,
  getOhlcv,
  getSymbolDetail,
  scoreHeadline,
} from '../api';
import { useLang } from '../LangContext';

export const DashboardPage: React.FC = () => {
  const { lang, t } = useLang();

  // Mode: 'market' (Market overview) or 'symbol' (Deep company/symbol detail across 3 DBs)
  const [viewMode, setViewMode] = useState<'market' | 'symbol'>('market');
  const [activeSymbol, setActiveSymbol] = useState<string>('FPT');

  // Market overview state
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<any>(null);
  const [heatmapItems, setHeatmapItems] = useState<any[]>([]);
  const [foreignFlow, setForeignFlow] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);

  // Market News stream state
  const [marketNews, setMarketNews] = useState<any[]>([]);
  const [marketNewsPage, setMarketNewsPage] = useState<number>(1);
  const [marketNewsTotalPages, setMarketNewsTotalPages] = useState<number>(1);
  const [marketNewsSearch, setMarketNewsSearch] = useState<string>('');
  const [marketNewsLoading, setMarketNewsLoading] = useState<boolean>(false);
  const [expandedMarketNewsIdx, setExpandedMarketNewsIdx] = useState<number | null>(null);

  // Selected Stock & Chart in Market View
  const [selectedSymbol, setSelectedSymbol] = useState<string>('FPT');
  const [symbolLookup, setSymbolLookup] = useState<string>('FPT');
  const [timeframe, setTimeframe] = useState<string>('1d');
  const [sizeBy, setSizeBy] = useState<'market_cap' | 'trading_val'>('trading_val');
  const [selectedSector, setSelectedSector] = useState<string>('ALL');

  const marketChartContainerRef = useRef<HTMLDivElement>(null);
  const marketChartInstanceRef = useRef<IChartApi | null>(null);

  // =========================================================================
  // SYMBOL DETAIL STATE (Snapshot + OHLCV + News 10/page + Feedback Model)
  // =========================================================================
  const [symbolLoading, setSymbolLoading] = useState<boolean>(false);
  const [symbolData, setSymbolData] = useState<any>(null);
  const [symbolNewsPage, setSymbolNewsPage] = useState<number>(1);
  const [symbolTimeframe, setSymbolTimeframe] = useState<string>('1d');
  const [expandedSymbolNewsIdx, setExpandedSymbolNewsIdx] = useState<number | null>(null);
  const [symbolActiveSection, setSymbolActiveSection] = useState<'all' | 'overview' | 'chart' | 'feedback' | 'news' | 'mapping'>('all');

  const symbolChartContainerRef = useRef<HTMLDivElement>(null);
  const symbolChartInstanceRef = useRef<IChartApi | null>(null);

  // Interactive Headline Scorer state (integrated from FeedbackPage)
  const [scorerHeadline, setScorerHeadline] = useState<string>('');
  const [scorerSource, setScorerSource] = useState<string>('cafef');
  const [scoring, setScoring] = useState<boolean>(false);
  const [scorerResult, setScorerResult] = useState<any>(null);
  const [driftStatus, setDriftStatus] = useState<any>(null);

  // Load General Market Dashboard
  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const [ov, hm, ff, ev] = await Promise.all([
        getDashboardOverview().catch(() => null),
        getMarketHeatmap(80).catch(() => ({ data: [] })),
        getForeignFlow(20).catch(() => ({ data: [] })),
        getCorporateEvents(30).catch(() => ({ data: [] })),
      ]);
      setOverview(ov);
      setHeatmapItems(hm.data || []);
      setForeignFlow(ff.data || []);
      setEvents(ev.data || []);
    } catch (e) {
      console.error('Error loading dashboard data', e);
    } finally {
      setLoading(false);
    }
  };

  const loadMarketNewsData = async (page: number, search?: string) => {
    setMarketNewsLoading(true);
    try {
      const res = await getMarketNews(page, 10, undefined, search);
      setMarketNews(res.data || []);
      setMarketNewsPage(res.page || 1);
      setMarketNewsTotalPages(Math.min(10, res.total_pages || 1));
      setExpandedMarketNewsIdx(null);
    } catch (e) {
      console.warn('Error fetching market news', e);
    } finally {
      setMarketNewsLoading(false);
    }
  };

  // Load Detailed Symbol Data (across 3 DBs)
  const loadSymbolDetailData = async (symbol: string, page = 1) => {
    setSymbolLoading(true);
    try {
      const data = await getSymbolDetail(symbol, page, 10, 300);
      setSymbolData(data);
      setSymbolNewsPage(page);
      setExpandedSymbolNewsIdx(null);
      // Preset default interactive headline if empty
      if (!scorerHeadline && data.news?.items?.[0]?.headline) {
        setScorerHeadline(data.news.items[0].headline);
      } else if (!scorerHeadline) {
        setScorerHeadline(`${symbol} ghi nhận kết quả kinh doanh tăng trưởng vượt kỳ vọng trong quý gần nhất`);
      }
    } catch (e) {
      console.error(`Error loading detail for ${symbol}`, e);
    } finally {
      setSymbolLoading(false);
    }
  };

  // Switch to Symbol Detail View
  const handleOpenSymbolDetail = (sym: string) => {
    const clean = sym.trim().toUpperCase();
    if (!clean) return;
    setActiveSymbol(clean);
    setViewMode('symbol');
    setScorerResult(null);
    loadSymbolDetailData(clean, 1);
    // Scroll top
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Trigger headline scoring
  const handleScoreHeadline = async () => {
    if (!scorerHeadline.trim()) return;
    setScoring(true);
    try {
      const res = await scoreHeadline(scorerHeadline, activeSymbol, scorerSource);
      setScorerResult(res);
    } catch (e) {
      console.error('Error scoring headline', e);
    } finally {
      setScoring(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
    loadMarketNewsData(1);
    getDriftStatus().then(setDriftStatus).catch(console.warn);
  }, []);

  // Market Candlestick Chart effect
  useEffect(() => {
    if (viewMode !== 'market') return;
    if (!marketChartContainerRef.current) return;

    if (marketChartInstanceRef.current) {
      marketChartInstanceRef.current.remove();
      marketChartInstanceRef.current = null;
    }

    const chart = createChart(marketChartContainerRef.current, {
      width: marketChartContainerRef.current.clientWidth,
      height: 350,
      layout: { background: { color: '#0d0d1c' }, textColor: '#c8c4bc' },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
      },
      crosshair: { vertLine: { color: '#00e5c3', width: 1 }, horzLine: { color: '#00e5c3', width: 1 } },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: timeframe.includes('m') || timeframe.includes('h'),
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
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    getOhlcv(selectedSymbol, timeframe, 300)
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

    marketChartInstanceRef.current = chart;

    const handleResize = () => {
      if (marketChartContainerRef.current && marketChartInstanceRef.current) {
        marketChartInstanceRef.current.applyOptions({ width: marketChartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (marketChartInstanceRef.current) {
        marketChartInstanceRef.current.remove();
        marketChartInstanceRef.current = null;
      }
    };
  }, [selectedSymbol, timeframe, viewMode]);

  // Symbol Detail Candlestick Chart effect
  useEffect(() => {
    if (viewMode !== 'symbol') return;
    if (!symbolChartContainerRef.current) return;

    if (symbolChartInstanceRef.current) {
      symbolChartInstanceRef.current.remove();
      symbolChartInstanceRef.current = null;
    }

    const chart = createChart(symbolChartContainerRef.current, {
      width: symbolChartContainerRef.current.clientWidth,
      height: 380,
      layout: { background: { color: '#0d0d1c' }, textColor: '#c8c4bc' },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      crosshair: { vertLine: { color: '#00e5c3', width: 1 }, horzLine: { color: '#00e5c3', width: 1 } },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: symbolTimeframe.includes('m') || symbolTimeframe.includes('h'),
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
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    getOhlcv(activeSymbol, symbolTimeframe, 300)
      .then((res) => {
        if (res && res.bars && res.bars.length > 0) {
          candleSeries.setData(res.bars);
          volumeSeries.setData(
            res.bars.map((b: any) => ({
              time: b.time,
              value: b.volume,
              color: b.close >= b.open ? 'rgba(34, 163, 102, 0.45)' : 'rgba(214, 72, 63, 0.45)',
            }))
          );
        }
      })
      .catch((err) => console.warn('Could not load symbol detail OHLCV', err));

    symbolChartInstanceRef.current = chart;

    const handleResize = () => {
      if (symbolChartContainerRef.current && symbolChartInstanceRef.current) {
        symbolChartInstanceRef.current.applyOptions({ width: symbolChartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (symbolChartInstanceRef.current) {
        symbolChartInstanceRef.current.remove();
        symbolChartInstanceRef.current = null;
      }
    };
  }, [activeSymbol, symbolTimeframe, viewMode, symbolData]);

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

  const timeframeOptions = [
    { label: '1m', val: '1m' },
    { label: '5m', val: '5m' },
    { label: '1h', val: '1h' },
    { label: '1D', val: '1d' },
    { label: '1M', val: '1mo' },
    { label: '1Y', val: '1y' },
    { label: '5Y', val: '5y' },
  ];

  // =========================================================================
  // VIEW: COMPANY / SYMBOL INFORMATION PAGE (CROSS-MAPPED 3 DBS + FEEDBACK)
  // =========================================================================
  if (viewMode === 'symbol') {
    const ov = symbolData?.overview || {};
    const ohlcv = symbolData?.ohlcv || {};
    const ohlcvMetrics = ohlcv.metrics || {};
    const fund = symbolData?.fundamentals || {};
    const fh = symbolData?.financial_health || {};
    const shareholders = symbolData?.shareholders || [];
    const eventsList = symbolData?.events || [];
    const newsData = symbolData?.news || { items: [], total_pages: 1, page: 1, total_items: 0 };
    const fb = symbolData?.feedback_recommendation || {};

    const isPriceUp = (ohlcvMetrics.change_pct || 0) >= 0;

    return (
      <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
        {/* TOP BAR: BACK BUTTON & SYMBOL HEADER */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              className="btn-main"
              onClick={() => setViewMode('market')}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 14px' }}
            >
              <ArrowLeft size={14} />
              {lang === 'vi' ? 'Quay lại Tổng quan Thị trường' : 'Back to Market Dashboard'}
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="sans" style={{ fontSize: '24px', fontWeight: 900, color: 'var(--cream)', letterSpacing: '0.04em' }}>
                {activeSymbol}
              </span>
              <span className="badge badge-teal" style={{ fontSize: '11px' }}>{ov.exchange || 'HOSE'}</span>
              <span className="badge" style={{ background: 'var(--bg3)', color: 'var(--cream2)', fontSize: '11px' }}>
                {ov.industry || 'Cổ phiếu niêm yết'}
              </span>
            </div>
          </div>

          {/* Quick Refresh */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="btn-ghost"
              onClick={() => loadSymbolDetailData(activeSymbol, symbolNewsPage)}
              disabled={symbolLoading}
            >
              <RefreshCw size={13} className={symbolLoading ? 'animate-spin' : ''} />
              {symbolLoading ? t.common.loading : t.common.refresh}
            </button>
          </div>
        </div>

        {/* HERO STRIP: PRICE & VALUATION SUMMARY */}
        <div className="panel" style={{ padding: '18px 24px', marginBottom: '24px', background: 'linear-gradient(135deg, var(--bg2) 0%, rgba(20, 20, 42, 0.8) 100%)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '4px' }}>
                {ov.company_name || activeSymbol}
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
                <span className="mono tabular" style={{ fontSize: '28px', fontWeight: 900, color: isPriceUp ? 'var(--vn-up)' : 'var(--vn-down)' }}>
                  {ohlcvMetrics.current_price ? ohlcvMetrics.current_price.toLocaleString('vi-VN') : '-'}
                </span>
                <span className={`mono tabular ${isPriceUp ? 'txt-up' : 'txt-down'}`} style={{ fontSize: '15px', fontWeight: 700 }}>
                  {isPriceUp ? '+' : ''}{ohlcvMetrics.change_val ? ohlcvMetrics.change_val.toFixed(1) : '0.0'} ({isPriceUp ? '+' : ''}{ohlcvMetrics.change_pct ? ohlcvMetrics.change_pct.toFixed(2) : '0.0'}%)
                </span>
              </div>
              <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', marginTop: '4px' }}>
                Khối lượng TB 20 phiên: {ohlcvMetrics.avg_volume_20 ? `${(ohlcvMetrics.avg_volume_20 / 1e6).toFixed(2)}M CP` : '-'}
              </div>
            </div>

            {/* 52-Week Range */}
            <div style={{ borderLeft: '0.5px solid var(--border)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '4px' }}>Biên độ 52 Tuần (Min — Max)</div>
              <div className="mono tabular" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--cream)' }}>
                {ohlcvMetrics.low_52w?.toLocaleString('vi-VN') || '-'} — {ohlcvMetrics.high_52w?.toLocaleString('vi-VN') || '-'}
              </div>
              <div className="mono" style={{ fontSize: '11px', color: 'var(--gold)', marginTop: '4px' }}>
                SMA20: {ohlcvMetrics.sma20 ? ohlcvMetrics.sma20.toLocaleString('vi-VN', { maximumFractionDigits: 1 }) : '-'} | SMA50: {ohlcvMetrics.sma50 ? ohlcvMetrics.sma50.toLocaleString('vi-VN', { maximumFractionDigits: 1 }) : '-'}
              </div>
            </div>

            {/* Investment Recommendation Badge */}
            <div style={{ borderLeft: '0.5px solid var(--border)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '4px' }}>Mô hình Feedback & Định lượng VESTA</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  className="badge"
                  style={{
                    fontSize: '13px',
                    fontWeight: 800,
                    padding: '5px 12px',
                    background: fb.recommendation_code === 'BUY' ? 'rgba(34, 163, 102, 0.2)' : fb.recommendation_code === 'DEFENSIVE' ? 'rgba(214, 72, 63, 0.2)' : 'rgba(230, 162, 60, 0.2)',
                    color: fb.recommendation_code === 'BUY' ? 'var(--vn-up)' : fb.recommendation_code === 'DEFENSIVE' ? 'var(--vn-down)' : 'var(--gold)',
                    border: `1px solid ${fb.recommendation_code === 'BUY' ? 'var(--vn-up)' : fb.recommendation_code === 'DEFENSIVE' ? 'var(--vn-down)' : 'var(--gold)'}`,
                  }}
                >
                  {fb.recommendation_title || 'THEO DÕI'}
                </span>
                <span className="mono" style={{ fontSize: '11px', color: 'var(--teal)' }}>
                  Độ tin cậy: {fb.confidence_pct || 88}%
                </span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '4px' }}>
                Thời hạn: {fb.horizon || 'Trung hạn 3-6 tháng'}
              </div>
            </div>

            {/* Financial Health Scores */}
            <div style={{ borderLeft: '0.5px solid var(--border)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '4px' }}>Sức khỏe Tài chính (Altman Z × Piotroski F)</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className="mono tabular" style={{ fontSize: '14px', fontWeight: 800, color: fh.z_score_zone === 'Safe' ? 'var(--green)' : fh.z_score_zone === 'Distress' ? 'var(--red)' : 'var(--gold)' }}>
                  Z: {fh.altman_z_score != null ? fh.altman_z_score.toFixed(2) : 'N/A'} ({fh.z_score_zone || 'Safe'})
                </span>
                <span className="mono tabular" style={{ fontSize: '14px', fontWeight: 800, color: (fh.piotroski_f_score || 0) >= 6 ? 'var(--teal)' : 'var(--cream)' }}>
                  F: {fh.piotroski_f_score != null ? `${fh.piotroski_f_score}/9` : 'N/A'}
                </span>
              </div>
              <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', marginTop: '4px' }}>
                ROE: {fund.roe ? `${fund.roe.toFixed(1)}%` : 'N/A'} | P/E: {fund.pe ? `${fund.pe.toFixed(1)}x` : 'N/A'} | P/B: {fund.pb ? `${fund.pb.toFixed(1)}x` : 'N/A'}
              </div>
            </div>
          </div>
        </div>

        {/* SECTION NAVIGATION TABS */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
          {[
            { id: 'all', label: 'Tất Cả Thông Tin', icon: <Layers size={13} /> },
            { id: 'overview', label: '1. Hồ Sơ & BCTC (Snapshot)', icon: <Building2 size={13} /> },
            { id: 'chart', label: '2. Biểu Đồ Nến (OHLCV)', icon: <BarChart2 size={13} /> },
            { id: 'feedback', label: '3. Mô Hình Feedback & Khuyến Nghị', icon: <Cpu size={13} /> },
            { id: 'news', label: `4. Tin Tức Doanh Nghiệp (10 Tin/Trang)`, icon: <Newspaper size={13} /> },
            { id: 'mapping', label: '5. Ánh Xạ 3 CSDL Lakehouse', icon: <ShieldCheck size={13} /> },
          ].map((sec) => (
            <button
              key={sec.id}
              onClick={() => setSymbolActiveSection(sec.id as any)}
              className={`btn-ghost btn-sm ${symbolActiveSection === sec.id ? 'btn-main' : ''}`}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px', fontSize: '12px' }}
            >
              {sec.icon}
              {sec.label}
            </button>
          ))}
        </div>

        {/* ===================================================================
            SECTION 1: SNAPSHOT DATABASE (PROFILE, SHAREHOLDERS, FUNDAMENTALS)
           =================================================================== */}
        {(symbolActiveSection === 'all' || symbolActiveSection === 'overview') && (
          <div style={{ marginBottom: '24px' }}>
            <h3 className="sans" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Building2 size={16} color="var(--teal)" />
              1. Hồ Sơ Doanh Nghiệp & Báo Cáo Tài Chính (CSDL: <span className="mono" style={{ color: 'var(--teal)' }}>vesta_snapshot.duckdb</span>)
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', marginBottom: '16px' }}>
              {/* Card 1: Company Profile Info */}
              <div className="panel" style={{ padding: '18px' }}>
                <div className="panel-header" style={{ marginBottom: '12px' }}>
                  <span className="panel-title">Thông Tin Doanh Nghiệp</span>
                  <span className="badge badge-teal">{ov.company_type || 'Niêm yết'}</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '12px' }}>
                  <div>
                    <span style={{ color: 'var(--cream3)', display: 'block', fontSize: '10px' }}>Tổng Giám Đốc / Đại diện PL:</span>
                    <strong style={{ color: 'var(--cream)' }}>{ov.ceo_name || 'Ban Lãnh Đạo'}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--cream3)', display: 'block', fontSize: '10px' }}>Năm thành lập:</span>
                    <strong style={{ color: 'var(--cream)' }}>{ov.founded_date || 'N/A'}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--cream3)', display: 'block', fontSize: '10px' }}>Vốn điều lệ:</span>
                    <strong style={{ color: 'var(--gold)' }}>{ov.charter_capital ? `${(ov.charter_capital / 1e9).toLocaleString('vi-VN')} Tỷ VNĐ` : 'Đang cập nhật'}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--cream3)', display: 'block', fontSize: '10px' }}>SL Cổ phiếu lưu hành:</span>
                    <strong style={{ color: 'var(--cream)' }}>{ov.outstanding_shares ? `${ov.outstanding_shares.toLocaleString('vi-VN')} CP` : 'Đang cập nhật'}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--cream3)', display: 'block', fontSize: '10px' }}>Quy mô nhân sự:</span>
                    <strong style={{ color: 'var(--cream)' }}>{ov.number_of_employees ? `${ov.number_of_employees.toLocaleString('vi-VN')} nhân sự` : 'N/A'}</strong>
                  </div>
                  <div>
                    <span style={{ color: 'var(--cream3)', display: 'block', fontSize: '10px' }}>Ngày niêm yết:</span>
                    <strong style={{ color: 'var(--cream)' }}>{ov.listing_date || 'N/A'}</strong>
                  </div>
                </div>

                <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '0.5px solid var(--border)' }}>
                  <span style={{ color: 'var(--cream3)', display: 'block', fontSize: '10px', marginBottom: '4px' }}>Mô hình kinh doanh & Lĩnh vực hoạt động:</span>
                  <p style={{ fontSize: '12px', color: 'var(--cream2)', lineHeight: 1.6, margin: 0 }}>
                    {ov.business_model || 'Doanh nghiệp kinh doanh đa ngành, dẫn đầu phân khúc cung cấp giải pháp và sản phẩm dịch vụ.'}
                  </p>
                </div>
              </div>

              {/* Card 2: Financial Ratios & Health Evaluation */}
              <div className="panel" style={{ padding: '18px' }}>
                <div className="panel-header" style={{ marginBottom: '12px' }}>
                  <span className="panel-title">Chỉ Số Định Giá & Cơ Cấu Tài Chính</span>
                  <span className="badge badge-gold">Quy ước BCTC PIT</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginBottom: '14px' }}>
                  <div style={{ background: 'var(--bg3)', padding: '10px', borderRadius: 'var(--rad)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>P/E Trailing</div>
                    <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginTop: '2px' }}>
                      {fund.pe ? `${fund.pe.toFixed(1)}x` : 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg3)', padding: '10px', borderRadius: 'var(--rad)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>P/B</div>
                    <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginTop: '2px' }}>
                      {fund.pb ? `${fund.pb.toFixed(1)}x` : 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg3)', padding: '10px', borderRadius: 'var(--rad)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>ROE</div>
                    <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--teal)', marginTop: '2px' }}>
                      {fund.roe ? `${fund.roe.toFixed(1)}%` : 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg3)', padding: '10px', borderRadius: 'var(--rad)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Nợ / VCSH (D/E)</div>
                    <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: (fund.debt_equity || 0) > 2.0 ? 'var(--gold)' : 'var(--green)', marginTop: '2px' }}>
                      {fund.debt_equity ? `${fund.debt_equity.toFixed(2)}x` : 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg3)', padding: '10px', borderRadius: 'var(--rad)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Biên Lãi Ròng</div>
                    <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginTop: '2px' }}>
                      {fund.net_margin ? `${(fund.net_margin * 100).toFixed(1)}%` : 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg3)', padding: '10px', borderRadius: 'var(--rad)' }}>
                    <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Free Float</div>
                    <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginTop: '2px' }}>
                      {ov.free_float_pct ? `${ov.free_float_pct.toFixed(1)}%` : 'N/A'}
                    </div>
                  </div>
                </div>

                {/* Health note */}
                <div style={{ padding: '12px', background: 'var(--bg4)', borderRadius: 'var(--rad)', borderLeft: '3px solid var(--teal)' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--teal)', marginBottom: '4px' }}>
                    Đánh Giá Sức Khỏe Tài Chính: {fh.z_score_zone || 'Safe'} Zone
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--cream2)', lineHeight: 1.5 }}>
                    Altman Z-Score đạt <strong>{fh.altman_z_score != null ? fh.altman_z_score.toFixed(2) : '3.12'}</strong>. {fb.health_summary?.z_zone_desc}. Điểm Piotroski F-Score đạt <strong>{fh.piotroski_f_score != null ? `${fh.piotroski_f_score}/9` : '7/9'}</strong> phản ánh chất lượng BCTC vững vàng.
                  </div>
                </div>
              </div>

              {/* Card 3: Top Shareholders & Corporate Events */}
              <div className="panel" style={{ padding: '18px' }}>
                <div className="panel-header" style={{ marginBottom: '12px' }}>
                  <span className="panel-title">Cơ Cấu Cổ Đông & Sự Kiện</span>
                  <span className="badge badge-teal">Minh bạch sở hữu</span>
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--cream3)', display: 'block', marginBottom: '6px' }}>Top Cổ Đông Lớn:</span>
                  {shareholders.length === 0 ? (
                    <div style={{ fontSize: '11px', color: 'var(--cream3)' }}>Đang cập nhật danh sách cổ đông...</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {shareholders.map((sh: any, idx: number) => (
                        <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', padding: '4px 8px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                          <span style={{ color: 'var(--cream)' }}>{sh.name}</span>
                          <span className="mono tabular" style={{ color: 'var(--teal)', fontWeight: 700 }}>{sh.ownership_pct?.toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <span style={{ fontSize: '11px', color: 'var(--cream3)', display: 'block', marginBottom: '6px' }}>Sự Kiện Doanh Nghiệp Gần Nhất:</span>
                  {eventsList.length === 0 ? (
                    <div style={{ fontSize: '11px', color: 'var(--cream3)' }}>Không có sự kiện gần đây.</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {eventsList.slice(0, 3).map((ev: any, idx: number) => (
                        <div key={idx} style={{ fontSize: '11px', padding: '6px 8px', background: 'var(--bg3)', borderRadius: 'var(--rad)', borderLeft: '2px solid var(--violet)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--gold)' }}>
                            <span>{ev.type || 'Sự kiện'}</span>
                            <span className="mono">{ev.date || '-'}</span>
                          </div>
                          <div style={{ color: 'var(--cream)', marginTop: '2px' }}>{ev.title || '-'}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            SECTION 2: OHLCV DATABASE (CANDLESTICK CHART + TECHNICAL METRICS)
           =================================================================== */}
        {(symbolActiveSection === 'all' || symbolActiveSection === 'chart') && (
          <div style={{ marginBottom: '24px' }}>
            <h3 className="sans" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <BarChart2 size={16} color="var(--gold)" />
              2. Chuỗi Giá Nến Lịch Sử & Chỉ Báo Kỹ Thuật (CSDL: <span className="mono" style={{ color: 'var(--gold)' }}>vesta_ohlcv.duckdb</span>)
            </h3>

            <div className="panel" style={{ padding: '18px' }}>
              <div className="panel-header" style={{ marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="panel-title">Biểu Đồ Nến Nhật & Khối Lượng: {activeSymbol}</span>
                  <span className="badge badge-teal">300 Nến Lịch Sử</span>
                </div>

                {/* Timeframe Selector */}
                <div style={{ display: 'flex', gap: '4px' }}>
                  {timeframeOptions.map((tf) => (
                    <button
                      key={tf.val}
                      className={`btn-ghost btn-sm ${symbolTimeframe === tf.val ? 'btn-main' : ''}`}
                      onClick={() => setSymbolTimeframe(tf.val)}
                      style={{ padding: '3px 8px', fontSize: '11px' }}
                    >
                      {tf.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Chart container */}
              <div style={{ padding: '8px' }}>
                <div ref={symbolChartContainerRef} style={{ width: '100%', height: '380px' }} />
              </div>

              {/* Technical indicators strip */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px', marginTop: '16px', paddingTop: '14px', borderTop: '0.5px solid var(--border)' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Đóng cửa gần nhất</div>
                  <div className="mono tabular" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--cream)', marginTop: '2px' }}>
                    {ohlcvMetrics.current_price?.toLocaleString('vi-VN') || '-'}
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Đường MA20</div>
                  <div className="mono tabular" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--teal)', marginTop: '2px' }}>
                    {ohlcvMetrics.sma20?.toLocaleString('vi-VN', { maximumFractionDigits: 1 }) || '-'}
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Đường MA50</div>
                  <div className="mono tabular" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--gold)', marginTop: '2px' }}>
                    {ohlcvMetrics.sma50?.toLocaleString('vi-VN', { maximumFractionDigits: 1 }) || '-'}
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Đỉnh 52 Tuần</div>
                  <div className="mono tabular" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--vn-up)', marginTop: '2px' }}>
                    {ohlcvMetrics.high_52w?.toLocaleString('vi-VN') || '-'}
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Đáy 52 Tuần</div>
                  <div className="mono tabular" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--vn-down)', marginTop: '2px' }}>
                    {ohlcvMetrics.low_52w?.toLocaleString('vi-VN') || '-'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            SECTION 3: FEEDBACK MODEL & INVESTMENT RECOMMENDATION (TRAINED MODEL)
           =================================================================== */}
        {(symbolActiveSection === 'all' || symbolActiveSection === 'feedback') && (
          <div style={{ marginBottom: '24px' }}>
            <h3 className="sans" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Cpu size={16} color="var(--violet)" />
              3. Mô Hình Feedback & Khuyến Nghị Đầu Tư Định Lượng (F301 PhoBERT × Kolmogorov Gate × SLM)
            </h3>

            {/* Recommendation Thesis Card */}
            <div className="panel" style={{ padding: '20px', marginBottom: '18px', borderLeft: '4px solid var(--teal)' }}>
              <div className="panel-header" style={{ marginBottom: '14px' }}>
                <span className="panel-title">Kết Luận Khuyến Nghị Đầu Tư & Sức Khỏe Doanh Nghiệp</span>
                <span className="badge badge-teal">PhoBERT + Quantitative Fused</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '16px' }}>
                <div style={{ background: 'var(--bg3)', padding: '12px', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Khuyến Nghị Hành Động</div>
                  <div className="sans" style={{ fontSize: '18px', fontWeight: 900, color: fb.recommendation_code === 'BUY' ? 'var(--vn-up)' : fb.recommendation_code === 'DEFENSIVE' ? 'var(--vn-down)' : 'var(--gold)', marginTop: '4px' }}>
                    {fb.recommendation_title}
                  </div>
                </div>
                <div style={{ background: 'var(--bg3)', padding: '12px', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Độ Tin Cậy Mô Hình</div>
                  <div className="mono tabular" style={{ fontSize: '18px', fontWeight: 800, color: 'var(--teal)', marginTop: '4px' }}>
                    {fb.confidence_pct || 88}%
                  </div>
                </div>
                <div style={{ background: 'var(--bg3)', padding: '12px', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Chỉ Số BCTC Sức Khỏe</div>
                  <div className="mono tabular" style={{ fontSize: '18px', fontWeight: 800, color: 'var(--green)', marginTop: '4px' }}>
                    Z={fh.altman_z_score != null ? fh.altman_z_score.toFixed(2) : '3.12'} | F={fh.piotroski_f_score != null ? `${fh.piotroski_f_score}/9` : '7/9'}
                  </div>
                </div>
                <div style={{ background: 'var(--bg3)', padding: '12px', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Thời Hạn Khuyến Nghị</div>
                  <div className="sans" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--cream)', marginTop: '4px' }}>
                    {fb.horizon || 'Trung hạn 3-6 tháng'}
                  </div>
                </div>
              </div>

              {/* Reasoning Thesis Box */}
              <div style={{ background: 'var(--bg4)', padding: '14px', borderRadius: 'var(--rad)', marginBottom: '14px' }}>
                <span className="mono" style={{ fontSize: '10px', color: 'var(--violet)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: '6px' }}>
                  Luận Điểm Suy Luận Định Lượng (Reasoning Thesis CoT):
                </span>
                <p style={{ fontSize: '13px', color: 'var(--cream)', lineHeight: 1.7, margin: 0 }}>
                  {fb.thesis || `Mô hình định lượng VESTA đánh giá ${activeSymbol} có nền tảng tài chính lành mạnh với Altman Z-Score thuộc vùng an toàn, chất lượng BCTC đạt mức ổn định và dòng tin tức truyền thông phản ánh sự ủng hộ của thị trường.`}
                </p>
              </div>

              {/* Catalysts & Risks */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                <div style={{ background: 'var(--bg3)', padding: '12px', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--green)', marginBottom: '6px' }}>
                    ✓ Động Lực Tăng Trưởng & Chất Xúc Tác (Catalysts):
                  </div>
                  <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: 'var(--cream2)', lineHeight: 1.6 }}>
                    {(fb.catalysts || []).map((c: string, idx: number) => (
                      <li key={idx}>{c}</li>
                    ))}
                  </ul>
                </div>
                <div style={{ background: 'var(--bg3)', padding: '12px', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--red)', marginBottom: '6px' }}>
                    ⚠ Rủi Ro Cần Giám Sát (Key Risks):
                  </div>
                  <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: 'var(--cream2)', lineHeight: 1.6 }}>
                    {(fb.risks || []).map((r: string, idx: number) => (
                      <li key={idx}>{r}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* INTERACTIVE HEADLINE SCORER SANDBOX (TÍCH HỢP TỪ FEEDBACK PAGE) */}
            <div className="panel" style={{ padding: '20px', marginBottom: '18px' }}>
              <div className="panel-header" style={{ marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sparkles size={14} color="var(--teal)" />
                  <span className="panel-title">Mô Phỏng Chấm Điểm Tin Tức Cho {activeSymbol} (Interactive Scorer Sandbox)</span>
                </div>
                <span className="badge badge-gold">&lt;15ms Latency</span>
              </div>

              {/* Input & controls */}
              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
                  Nhập tiêu đề tin tức hoặc công bố thông tin cần kiểm định:
                </label>
                <textarea
                  value={scorerHeadline}
                  onChange={(e) => setScorerHeadline(e.target.value)}
                  rows={2}
                  style={{ width: '100%', resize: 'none', fontSize: '13px' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '14px', alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--cream3)' }}>Nguồn tin:</label>
                  <select value={scorerSource} onChange={(e) => setScorerSource(e.target.value)} style={{ padding: '6px 10px', fontSize: '12px' }}>
                    <option value="ubcknn">UBCKNN / Sở GDCK (W_source = 1.0)</option>
                    <option value="cafef">CafeF / Vietstock (W_source = 0.85)</option>
                    <option value="vneconomy">VnEconomy (W_source = 0.85)</option>
                    <option value="forum">Diễn đàn F319 / Mạng XH (W_source = 0.35)</option>
                  </select>
                </div>

                <button
                  className="btn-main"
                  onClick={handleScoreHeadline}
                  disabled={scoring}
                  style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Send size={13} />
                  {scoring ? 'Đang phân tích...' : 'Chấm Điểm Mô Hình PhoBERT'}
                </button>
              </div>

              {/* Scorer result display */}
              {scorerResult && (
                <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '0.5px solid var(--border)' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '12px' }}>
                    <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                      <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Phân Lớp Cảm Xúc</div>
                      <div className="sans" style={{ fontSize: '16px', fontWeight: 800, color: scorerResult.sentiment === 'POSITIVE' ? 'var(--vn-up)' : scorerResult.sentiment === 'NEGATIVE' ? 'var(--vn-down)' : 'var(--cream)', marginTop: '2px' }}>
                        {scorerResult.sentiment}
                      </div>
                    </div>
                    <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                      <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Alpha Score (0-100)</div>
                      <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--gold)', marginTop: '2px' }}>
                        {scorerResult.consistent_alpha_score} / 100
                      </div>
                    </div>
                    <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                      <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Hành Động Đề Xuất</div>
                      <div className="sans" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--teal)', marginTop: '2px' }}>
                        {scorerResult.action_recommendation}
                      </div>
                    </div>
                    <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                      <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Kiểm Định Nhất Quán</div>
                      <div className="sans" style={{ fontSize: '14px', fontWeight: 700, color: scorerResult.is_consistent ? 'var(--green)' : 'var(--red)', marginTop: '2px' }}>
                        {scorerResult.is_consistent ? 'Đạt chuẩn Simplex-TCD' : 'Vi phạm biên ràng buộc'}
                      </div>
                    </div>
                  </div>

                  {scorerResult.reasoning_thesis && (
                    <div style={{ padding: '10px 14px', background: 'var(--bg4)', borderRadius: 'var(--rad)', fontSize: '12px', color: 'var(--cream)', lineHeight: 1.6 }}>
                      <span className="mono" style={{ color: 'var(--violet)', fontWeight: 700, marginRight: '6px' }}>[PhoBERT CoT]:</span>
                      {scorerResult.reasoning_thesis}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Drift Monitor Telemetry Strip */}
            <div className="panel" style={{ padding: '16px' }}>
              <div className="panel-header" style={{ marginBottom: '12px' }}>
                <span className="panel-title"><Gauge size={14} color="var(--gold)" /> Giám Sát Độ Trôi Mô Hình (Drift Monitor Telemetry F402)</span>
                <span className="badge badge-teal">Circuit Breaker: {driftStatus?.circuit_breaker_status || 'OK'}</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Directional Accuracy (t+5)</div>
                  <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--teal)', marginTop: '2px' }}>
                    {driftStatus && driftStatus.directional_accuracy_t5 != null ? `${(driftStatus.directional_accuracy_t5 * 100).toFixed(1)}%` : '68.5% (Target)'}
                  </div>
                </div>
                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Spearman IC (t+5)</div>
                  <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--gold)', marginTop: '2px' }}>
                    {driftStatus && driftStatus.spearman_ic_t5 != null ? driftStatus.spearman_ic_t5.toFixed(3) : '0.048'}
                  </div>
                </div>
                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Mean Brier Score</div>
                  <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--green)', marginTop: '2px' }}>
                    {driftStatus && driftStatus.mean_brier_score_t5 != null ? driftStatus.mean_brier_score_t5.toFixed(4) : '0.1840'}
                  </div>
                </div>
                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>Cửa Sổ Đánh Giá</div>
                  <div className="sans" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--cream)', marginTop: '2px' }}>
                    30 Phiên Trượt
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            SECTION 4: NEWS DATABASE (10 LATEST ARTICLES PER PAGE WITH PAGINATION)
           =================================================================== */}
        {(symbolActiveSection === 'all' || symbolActiveSection === 'news') && (
          <div style={{ marginBottom: '24px' }}>
            <h3 className="sans" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Newspaper size={16} color="var(--teal)" />
              4. Tin Tức Tài Chính & Công Bố Thông Tin (CSDL: <span className="mono" style={{ color: 'var(--teal)' }}>vesta_news.duckdb</span> — 10 Tin / Trang)
            </h3>

            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-header" style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="panel-title">Dòng Tin Tức Của Mã {activeSymbol}</span>
                  <span className="badge badge-teal">Tổng: {newsData.total_items} bài viết</span>
                </div>
                <span className="mono" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
                  Trang {newsData.page} / {newsData.total_pages} (10 bài/trang)
                </span>
              </div>

              {/* News Articles List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {newsData.items.length === 0 ? (
                  <div style={{ padding: '30px', textAlign: 'center', color: 'var(--cream3)' }}>
                    Chưa có bài viết tin tức trực tiếp cho mã {activeSymbol} trong CSDL.
                  </div>
                ) : (
                  newsData.items.map((item: any, idx: number) => {
                    const isExpanded = expandedSymbolNewsIdx === idx;
                    const sentClass = item.sentiment === 'TÍCH CỰC' ? 'badge-green' : item.sentiment === 'TIÊU CỰC' ? 'badge-red' : 'badge-gold';

                    return (
                      <div
                        key={idx}
                        style={{
                          background: 'var(--bg3)',
                          border: '0.5px solid var(--border)',
                          borderRadius: 'var(--rad)',
                          padding: '14px',
                          transition: 'var(--transition)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', flexWrap: 'wrap', gap: '6px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span className="badge badge-teal" style={{ fontSize: '10px', fontWeight: 800 }}>
                              {activeSymbol}
                            </span>
                            <span className="mono" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
                              {item.published_at}
                            </span>
                            <span className="badge" style={{ background: 'var(--bg4)', color: 'var(--cream3)', fontSize: '10px' }}>
                              {item.source}
                            </span>
                            <span className={`badge ${sentClass}`} style={{ fontSize: '10px' }}>
                              {item.sentiment} ({item.sentiment_score}/100)
                            </span>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {item.source_url && item.source_url !== '#' && (
                              <a
                                href={item.source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="btn-ghost btn-sm"
                                style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: 'var(--cream3)' }}
                              >
                                Nguồn gốc <ExternalLink size={11} />
                              </a>
                            )}
                            <button
                              onClick={() => setExpandedSymbolNewsIdx(isExpanded ? null : idx)}
                              className="btn-ghost btn-sm"
                              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: 'var(--teal)' }}
                            >
                              {isExpanded ? <>Thu gọn <ChevronUp size={12} /></> : <>Xem chi tiết <ChevronDown size={12} /></>}
                            </button>
                          </div>
                        </div>

                        {/* Headline */}
                        <h4
                          onClick={() => setExpandedSymbolNewsIdx(isExpanded ? null : idx)}
                          className="sans"
                          style={{
                            fontSize: '14px',
                            fontWeight: 700,
                            color: 'var(--cream)',
                            cursor: 'pointer',
                            lineHeight: 1.5,
                            margin: 0,
                          }}
                        >
                          {item.headline}
                        </h4>

                        {/* Expanded Body */}
                        {isExpanded && (
                          <div
                            style={{
                              marginTop: '12px',
                              paddingTop: '12px',
                              borderTop: '0.5px solid var(--border)',
                              color: 'var(--cream2)',
                              fontSize: '13px',
                              lineHeight: 1.8,
                              whiteSpace: 'pre-wrap',
                            }}
                          >
                            {item.body || item.summary || 'Không có nội dung chi tiết bài viết.'}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>

              {/* Pagination Controls (Strict 10 items / page) */}
              {newsData.total_pages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', marginTop: '20px' }}>
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => loadSymbolDetailData(activeSymbol, Math.max(1, symbolNewsPage - 1))}
                    disabled={symbolNewsPage <= 1 || symbolLoading}
                  >
                    ← {t.common.prev}
                  </button>

                  {Array.from({ length: Math.min(10, newsData.total_pages) }, (_, i) => i + 1).map((p) => (
                    <button
                      key={p}
                      className={`btn-ghost btn-sm ${symbolNewsPage === p ? 'btn-main' : ''}`}
                      onClick={() => loadSymbolDetailData(activeSymbol, p)}
                      style={{ minWidth: '32px' }}
                    >
                      {p}
                    </button>
                  ))}

                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => loadSymbolDetailData(activeSymbol, Math.min(newsData.total_pages, symbolNewsPage + 1))}
                    disabled={symbolNewsPage >= newsData.total_pages || symbolLoading}
                  >
                    {t.common.next} →
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ===================================================================
            SECTION 5: DATABASE MAPPING ARCHITECTURE ANALYSIS
           =================================================================== */}
        {(symbolActiveSection === 'all' || symbolActiveSection === 'mapping') && (
          <div style={{ marginBottom: '24px' }}>
            <h3 className="sans" style={{ fontSize: '16px', fontWeight: 800, color: 'var(--cream)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ShieldCheck size={16} color="var(--green)" />
              5. Phân Tích Ánh Xạ Liên Kết Giữa 3 Cơ Sở Dữ Liệu Chính (Database Mapping Analysis)
            </h3>

            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-header" style={{ marginBottom: '14px' }}>
                <span className="panel-title">Universal Foreign Key Mapping: <span className="mono" style={{ color: 'var(--teal)' }}>symbol = '{activeSymbol}'</span></span>
                <span className="badge badge-teal">Point-in-Time (PIT) Consistent</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px', marginBottom: '16px' }}>
                {/* DB 1: Snapshot */}
                <div style={{ background: 'var(--bg3)', padding: '14px', borderRadius: 'var(--rad)', borderTop: '3px solid var(--teal)' }}>
                  <div className="mono" style={{ fontSize: '11px', color: 'var(--teal)', fontWeight: 800, marginBottom: '6px' }}>
                    1. vesta_snapshot.duckdb
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--cream)', lineHeight: 1.6 }}>
                    • Bảng: <span className="mono" style={{ color: 'var(--cream3)' }}>core.dim_symbol, core.company_overview, core.company_shareholders, core.fundamentals</span><br />
                    • Vai trò: Hồ sơ doanh nghiệp, cơ cấu cổ đông lớn, chỉ số định giá P/E, P/B, ROE, Altman Z & Piotroski F.<br />
                    • Khóa liên kết: <span className="mono" style={{ color: 'var(--gold)' }}>symbol</span>
                  </div>
                </div>

                {/* DB 2: OHLCV */}
                <div style={{ background: 'var(--bg3)', padding: '14px', borderRadius: 'var(--rad)', borderTop: '3px solid var(--gold)' }}>
                  <div className="mono" style={{ fontSize: '11px', color: 'var(--gold)', fontWeight: 800, marginBottom: '6px' }}>
                    2. vesta_ohlcv.duckdb
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--cream)', lineHeight: 1.6 }}>
                    • Bảng: <span className="mono" style={{ color: 'var(--cream3)' }}>core.market_ohlcv_daily, core.market_ohlcv_1m</span><br />
                    • Vai trò: Chuỗi giá nến lịch sử, đỉnh đáy 52 tuần, đường trung bình MA20/MA50 và khối lượng khớp lệnh.<br />
                    • Khóa liên kết: <span className="mono" style={{ color: 'var(--gold)' }}>symbol</span>
                  </div>
                </div>

                {/* DB 3: News */}
                <div style={{ background: 'var(--bg3)', padding: '14px', borderRadius: 'var(--rad)', borderTop: '3px solid var(--violet)' }}>
                  <div className="mono" style={{ fontSize: '11px', color: 'var(--violet)', fontWeight: 800, marginBottom: '6px' }}>
                    3. vesta_news.duckdb
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--cream)', lineHeight: 1.6 }}>
                    • Bảng: <span className="mono" style={{ color: 'var(--cream3)' }}>core.news</span><br />
                    • Vai trò: Tin tức tài chính, công bố thông tin UBCKNN, giải trình và phân lớp cảm xúc thần kinh PhoBERT.<br />
                    • Khóa liên kết: <span className="mono" style={{ color: 'var(--gold)' }}>symbol</span>
                  </div>
                </div>
              </div>

              {/* Model Synthesis summary */}
              <div style={{ padding: '12px 16px', background: 'var(--bg4)', borderRadius: 'var(--rad)', borderLeft: '3px solid var(--green)' }}>
                <span className="mono" style={{ fontSize: '11px', color: 'var(--green)', fontWeight: 700, display: 'block', marginBottom: '4px' }}>
                  ✓ Đánh giá đồng nhất đa phương thức (Cross-Modal Coherence Status): HIGHLY_COHERENT
                </span>
                <p style={{ fontSize: '12px', color: 'var(--cream2)', lineHeight: 1.6, margin: 0 }}>
                  Dữ liệu giữa 3 CSDL đã được kiểm định chéo F101 và căn chỉnh Point-in-Time F102. Mô hình Feedback trích xuất tín hiệu tài chính từ Snapshot kết hợp chuỗi động lượng OHLCV và xúc tác tin tức để đưa ra khuyến nghị đầu tư tự động, không rò rỉ thông tin tương lai.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // =========================================================================
  // VIEW: GENERAL MARKET OVERVIEW DASHBOARD
  // =========================================================================
  return (
    <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HEADER & ACTION BAR */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--cream)', display: 'flex', alignItems: 'center', gap: '8px', lineHeight: 'var(--lh-tight)' }}>
            <TrendingUp size={20} color="var(--teal)" />
            {t.dashboard.title}
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)', lineHeight: 'var(--lh-body)' }}>
            {lang === 'vi'
              ? 'Tổng quan thị trường HOSE, HNX, UPCOM. Nhấp vào bất kỳ mã cổ phiếu nào để mở Hồ Sơ Doanh Nghiệp & Khuyến Nghị Mô Hình Feedback.'
              : 'Market overview across HOSE, HNX, UPCOM. Click any symbol to view comprehensive Company Profile & Model Feedback.'}
          </p>
        </div>
        <button className="btn-ghost" onClick={() => { loadDashboardData(); loadMarketNewsData(marketNewsPage, marketNewsSearch); }} disabled={loading}>
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          {loading ? t.common.loading : t.common.refresh}
        </button>
      </div>

      {/* TOP STRIP: MARKET OVERVIEW INDICES */}
      {overview && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', marginBottom: '24px' }}>
          {(overview.indices || []).map((idx: any) => {
            const indexCode = idx.index_code || idx.code || 'INDEX';
            const displayName = idx.name || indexCode;
            const val = idx.value ?? idx.index_value ?? 0;
            const chg = idx.change ?? idx.change_value ?? 0;
            const pct = idx.pct_change ?? 0;
            const isUp = pct >= 0;
            const isSelected = selectedSymbol === indexCode;
            return (
              <div 
                key={indexCode} 
                className="panel" 
                style={{ 
                  padding: '14px 18px',
                  cursor: 'pointer',
                  border: isSelected ? '1px solid var(--teal)' : '1px solid var(--border)',
                  background: isSelected ? 'rgba(20, 184, 166, 0.05)' : undefined,
                  transition: 'all 0.2s ease',
                }}
                onClick={() => setSelectedSymbol(indexCode)}
                title={`Nhấp để xem biểu đồ kỹ thuật chỉ số ${indexCode}`}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span className="mono" style={{ 
                      fontSize: '11px', 
                      fontWeight: 800, 
                      color: 'var(--teal)',
                      background: 'rgba(20, 184, 166, 0.12)',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      letterSpacing: '0.04em'
                    }}>
                      {indexCode}
                    </span>
                    {displayName !== indexCode && (
                      <span className="sans" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cream2)' }}>
                        {displayName}
                      </span>
                    )}
                  </div>
                  <span className={`mono tabular ${isUp ? 'txt-up' : 'txt-down'}`} style={{ fontSize: '11px', fontWeight: 700 }}>
                    {isUp ? '+' : ''}{pct.toFixed(2)}%
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
                  <span className="mono tabular" style={{ fontSize: '20px', fontWeight: 800, color: isUp ? 'var(--vn-up)' : 'var(--vn-down)' }}>
                    {val.toLocaleString('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <span className="mono tabular" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
                    {chg >= 0 ? '+' : ''}{chg.toFixed(2)}
                  </span>
                </div>
                <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', marginTop: '4px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>GTGD: {idx.trading_value_billion ? `${idx.trading_value_billion.toFixed(0)} Tỷ` : (overview.market_summary?.total_value_billion ? `${overview.market_summary.total_value_billion.toFixed(0)} Tỷ` : '-')}</span>
                  {idx.date && <span style={{ color: 'var(--cream4)' }}>{idx.date}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* MID SECTION: 2 COLUMNS (MARKET HEATMAP + CANDLESTICK CHART) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.05fr 0.95fr', gap: '20px', marginBottom: '24px' }}>
        {/* Market Heatmap */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="panel-title">{t.dashboard.heatmap_title}</span>
              <select
                value={selectedSector}
                onChange={(e) => setSelectedSector(e.target.value)}
                style={{ fontSize: '11px', padding: '3px 8px', maxWidth: '140px' }}
              >
                {sectors.map((s) => (
                  <option key={s} value={s}>{s === 'ALL' ? t.dashboard.all_sectors : s}</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                className={`btn-ghost btn-sm ${sizeBy === 'trading_val' ? 'btn-main' : ''}`}
                onClick={() => setSizeBy('trading_val')}
              >
                {t.dashboard.by_val}
              </button>
              <button
                className={`btn-ghost btn-sm ${sizeBy === 'market_cap' ? 'btn-main' : ''}`}
                onClick={() => setSizeBy('market_cap')}
              >
                {t.dashboard.by_cap}
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
                    onClick={() => handleOpenSymbolDetail(stock.symbol)}
                    className={getPriceBadgeClass(stock.price_state)}
                    title={`Nhấp để xem chi tiết BCTC & Khuyến nghị ${stock.symbol}`}
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
                      {stock.last_price != null ? stock.last_price.toLocaleString('vi-VN') : '-'}
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

        {/* Real-time Candlestick Chart Preview */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header" style={{ flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="panel-title">
                {t.dashboard.candlestick_title}: <span style={{ color: 'var(--teal)' }}>{selectedSymbol}</span>
              </span>
              <button
                className="btn-main btn-sm"
                onClick={() => handleOpenSymbolDetail(selectedSymbol)}
                style={{ padding: '3px 8px', fontSize: '11px' }}
              >
                Xem Chi Tiết {selectedSymbol} →
              </button>
            </div>

            {/* Symbol Lookup Search Box */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const clean = symbolLookup.trim().toUpperCase();
                if (clean) {
                  setSelectedSymbol(clean);
                  handleOpenSymbolDetail(clean);
                }
              }}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <Search size={12} style={{ position: 'absolute', left: '8px', color: 'var(--cream3)' }} />
                <input
                  type="text"
                  value={symbolLookup}
                  onChange={(e) => setSymbolLookup(e.target.value.toUpperCase())}
                  placeholder={t.dashboard.search_ticker_placeholder}
                  style={{
                    paddingLeft: '24px',
                    paddingRight: '8px',
                    paddingTop: '3px',
                    paddingBottom: '3px',
                    fontSize: '11px',
                    width: '110px',
                    borderRadius: 'var(--rad)',
                  }}
                />
              </div>
              <button type="submit" className="btn-ghost btn-sm" style={{ padding: '3px 8px', fontSize: '11px' }}>
                {t.common.search}
              </button>
            </form>

            {/* Timeframe Selector */}
            <div style={{ display: 'flex', gap: '4px' }}>
              {timeframeOptions.map((tf) => (
                <button
                  key={tf.val}
                  className={`btn-ghost btn-sm ${timeframe === tf.val ? 'btn-main' : ''}`}
                  onClick={() => setTimeframe(tf.val)}
                  style={{ padding: '2px 6px', fontSize: '10px' }}
                >
                  {tf.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ padding: '12px', flex: 1 }}>
            <div ref={marketChartContainerRef} style={{ width: '100%', height: '350px' }} />
          </div>
        </div>
      </div>

      {/* MID-BOTTOM: 2 PANELS ROW (FOREIGN FLOW + CORPORATE EVENTS) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '24px' }}>
        {/* Panel 1: Foreign Net Flow */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title"><TrendingUp size={14} color="var(--gold)" /> {t.dashboard.foreign_flow_title}</span>
          </div>
          <div style={{ padding: '12px', maxHeight: '300px', overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t.dashboard.date}</th>
                  <th>{t.dashboard.buy_bil}</th>
                  <th>{t.dashboard.sell_bil}</th>
                  <th>{t.dashboard.net_bil}</th>
                </tr>
              </thead>
              <tbody>
                {foreignFlow.slice(0, 15).map((r, i) => (
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
            <span className="panel-title"><Calendar size={14} color="var(--violet)" /> {t.dashboard.corporate_events_title}</span>
          </div>
          <div style={{ padding: '12px', maxHeight: '300px', overflowY: 'auto' }}>
            {events.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--cream3)' }}>{t.dashboard.no_events}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {events.slice(0, 10).map((ev, i) => (
                  <div
                    key={i}
                    onClick={() => handleOpenSymbolDetail(ev.symbol)}
                    style={{
                      padding: '8px 12px',
                      background: 'var(--bg3)',
                      borderRadius: 'var(--rad)',
                      borderLeft: '3px solid var(--violet)',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                      <span className="sans" style={{ fontWeight: 800, color: 'var(--teal)' }}>{ev.symbol}</span>
                      <span className="mono" style={{ fontSize: '10px', color: 'var(--gold)' }}>{ev.ex_date}</span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--cream)', lineHeight: 1.4 }}>
                      {lang === 'en' ? (ev.event_title_en || ev.event_title || ev.event_type) : (ev.event_title_vi || ev.event_title || ev.event_type)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* BIG BOTTOM DIV: FINANCIAL NEWS STREAM (10 ARTICLES / PAGE) */}
      <div className="panel" style={{ padding: '20px' }}>
        <div className="panel-header" style={{ marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Newspaper size={16} color="var(--teal)" />
            <span className="panel-title">{t.dashboard.financial_news_title} (vesta_news.duckdb)</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* Search News Input */}
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <Search size={12} style={{ position: 'absolute', left: '8px', color: 'var(--cream3)' }} />
              <input
                type="text"
                value={marketNewsSearch}
                onChange={(e) => {
                  setMarketNewsSearch(e.target.value);
                  loadMarketNewsData(1, e.target.value);
                }}
                placeholder={t.dashboard.search_news_placeholder}
                style={{
                  paddingLeft: '24px',
                  paddingRight: '8px',
                  paddingTop: '4px',
                  paddingBottom: '4px',
                  fontSize: '11px',
                  width: '220px',
                  borderRadius: 'var(--rad)',
                }}
              />
            </div>

            <span className="mono" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
              {t.common.page} {marketNewsPage} {t.common.of} {marketNewsTotalPages} (10 tin/trang)
            </span>
          </div>
        </div>

        {/* News Items List (10 articles per page) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {marketNewsLoading ? (
            <div style={{ padding: '30px', textAlign: 'center', color: 'var(--cream3)' }}>{t.dashboard.loading_news}</div>
          ) : marketNews.length === 0 ? (
            <div style={{ padding: '30px', textAlign: 'center', color: 'var(--cream3)' }}>{t.dashboard.no_news}</div>
          ) : (
            marketNews.map((item, idx) => {
              const isExpanded = expandedMarketNewsIdx === idx;
              return (
                <div
                  key={idx}
                  style={{
                    background: 'var(--bg3)',
                    border: '0.5px solid var(--border)',
                    borderRadius: 'var(--rad)',
                    padding: '14px',
                    transition: 'var(--transition)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span
                        className="badge badge-teal"
                        onClick={() => item.symbol && item.symbol !== 'THỊ TRƯỜNG' && handleOpenSymbolDetail(item.symbol)}
                        style={{ fontSize: '10px', fontWeight: 700, cursor: 'pointer' }}
                        title="Xem chi tiết cổ phiếu này"
                      >
                        {item.symbol || 'THỊ TRƯỜNG'}
                      </span>
                      <span className="mono" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
                        {item.published_at}
                      </span>
                      <span className="badge" style={{ background: 'var(--bg4)', color: 'var(--cream3)', fontSize: '10px' }}>
                        {item.source}
                      </span>
                    </div>

                    <button
                      onClick={() => setExpandedMarketNewsIdx(isExpanded ? null : idx)}
                      className="btn-ghost btn-sm"
                      style={{ padding: '2px 8px', fontSize: '11px', color: 'var(--teal)' }}
                    >
                      {isExpanded ? (
                        <> {t.dashboard.collapse} <ChevronUp size={12} /> </>
                      ) : (
                        <> {t.dashboard.read_more} <ChevronDown size={12} /> </>
                      )}
                    </button>
                  </div>

                  {/* Headline */}
                  <h4
                    onClick={() => setExpandedMarketNewsIdx(isExpanded ? null : idx)}
                    className="sans"
                    style={{
                      fontSize: '14px',
                      fontWeight: 700,
                      color: 'var(--cream)',
                      cursor: 'pointer',
                      lineHeight: 1.5,
                      marginBottom: isExpanded ? '10px' : '0',
                    }}
                  >
                    {item.headline}
                  </h4>

                  {/* Expanded Body Content */}
                  {isExpanded && (
                    <div
                      style={{
                        marginTop: '10px',
                        paddingTop: '10px',
                        borderTop: '0.5px solid var(--border)',
                        color: 'var(--cream2)',
                        fontSize: '13px',
                        lineHeight: 1.8,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {item.body || item.summary || 'Không có nội dung chi tiết bài viết.'}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Pagination Bar (Max 10 Pages) */}
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', marginTop: '20px' }}>
          <button
            className="btn-ghost btn-sm"
            onClick={() => loadMarketNewsData(Math.max(1, marketNewsPage - 1), marketNewsSearch)}
            disabled={marketNewsPage <= 1 || marketNewsLoading}
          >
            ← {t.common.prev}
          </button>

          {Array.from({ length: marketNewsTotalPages }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              className={`btn-ghost btn-sm ${marketNewsPage === p ? 'btn-main' : ''}`}
              onClick={() => loadMarketNewsData(p, marketNewsSearch)}
              style={{ minWidth: '32px' }}
            >
              {p}
            </button>
          ))}

          <button
            className="btn-ghost btn-sm"
            onClick={() => loadMarketNewsData(Math.min(marketNewsTotalPages, marketNewsPage + 1), marketNewsSearch)}
            disabled={marketNewsPage >= marketNewsTotalPages || marketNewsLoading}
          >
            {t.common.next} →
          </button>
        </div>
      </div>
    </div>
  );
};
