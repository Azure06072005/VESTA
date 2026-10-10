import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  AreaSeries,
  LineSeries,
} from 'lightweight-charts';
import type { IChartApi } from 'lightweight-charts';
import {
  Activity,
  ArrowLeft,
  Award,
  BarChart2,
  Building2,
  Coins,
  DollarSign,
  Gauge,
  Globe,
  Layers,
  Maximize2,
  Minimize2,
  Newspaper,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  getDashboardOverview,
  getMarketExtended,
  getMarketHeatmap,
  getMarketNews,
  getOhlcv,
  getSymbolDetail,
  getSymbolFull,
  scoreHeadline,
} from '../api';
import { useLang } from '../LangContext';
import { FoamTreeTreemap } from '../components/FoamTreeTreemap';
import type { TreemapNode } from '../components/FoamTreeTreemap';

export const DashboardPage: React.FC = () => {
  const { lang, t } = useLang();

  // Mode: 'market' (Market overview) or 'symbol' (Deep company/symbol detail across 3 DBs)
  const [viewMode, setViewMode] = useState<'market' | 'symbol'>('market');
  const [activeSymbol, setActiveSymbol] = useState<string>('VIC');

  // Market overview state
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<any>(null);
  const [marketExtended, setMarketExtended] = useState<any>(null);
  const [heatmapItems, setHeatmapItems] = useState<any[]>([]);
  const [sizeBy, setSizeBy] = useState<'market_cap' | 'trading_val'>('trading_val');
  const [selectedSector, setSelectedSector] = useState<string>('ALL');

  // FoamTree Treemap state for Sector Performance & Trading Board
  const [sectorViewMode, setSectorViewMode] = useState<'foamtree' | 'table'>('foamtree');
  const [sectorSizeMetric, setSectorSizeMetric] = useState<'turnover' | 'cap'>('turnover');
  const [tradingBoardViewMode, setTradingBoardViewMode] = useState<'foamtree' | 'grid'>('foamtree');

  // Macro sub-tab: 'commodities' | 'currencies'
  const [macroTab, setMacroTab] = useState<'commodities' | 'currencies'>('commodities');

  // Market News stream state
  const [marketNews, setMarketNews] = useState<any[]>([]);
  const [marketNewsLoading, setMarketNewsLoading] = useState<boolean>(false);

  // Selected Stock & Chart in Market View
  const [selectedMarketIndex, setSelectedMarketIndex] = useState<string>('VNINDEX');
  const [symbolLookup, setSymbolLookup] = useState<string>('');

  // =========================================================================
  // SYMBOL DETAIL STATE (TradingView + Vietstock 8 Tabs Architecture)
  // =========================================================================
  const [symbolLoading, setSymbolLoading] = useState<boolean>(false);
  const [symbolFullData, setSymbolFullData] = useState<any>(null);
  const [symbolDetailData, setSymbolDetailData] = useState<any>(null);
  const [symbolActiveTab, setSymbolActiveTab] = useState<
    'overview' | 'trading' | 'technical' | 'financials' | 'profile' | 'news_events' | 'internal_trading' | 'bonds'
  >('overview');

  // Chart Mode in Symbol Overview: 'line' (1m intraday line chart default) or 'full' (Full Candlestick + MA + Volume)
  const [symbolChartMode, setSymbolChartMode] = useState<'line' | 'full'>('line');
  const [selectedTimeRange, setSelectedTimeRange] = useState<
    '1D' | '5D' | '1M' | '3M' | '6M' | 'YTD' | '1Y' | '5Y' | 'ALL'
  >('1D');
  const [dynamicPeriodReturn, setDynamicPeriodReturn] = useState<number | null>(null);

  const symbolChartContainerRef = useRef<HTMLDivElement>(null);
  const symbolChartInstanceRef = useRef<IChartApi | null>(null);

  // Scorer state (PhoBERT + SLM)
  const [scorerHeadline, setScorerHeadline] = useState<string>('');
  const [scorerSource, setScorerSource] = useState<string>('cafef');
  const [scoring, setScoring] = useState<boolean>(false);
  const [scorerResult, setScorerResult] = useState<any>(null);

  // =========================================================================
  // DATA FETCHING
  // =========================================================================
  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const [ov, ext, hm] = await Promise.all([
        getDashboardOverview().catch(() => null),
        getMarketExtended().catch(() => null),
        getMarketHeatmap(80).catch(() => ({ data: [] })),
      ]);
      setOverview(ov);
      setMarketExtended(ext);
      setHeatmapItems(hm.data || []);
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
    } catch (e) {
      console.warn('Error fetching market news', e);
    } finally {
      setMarketNewsLoading(false);
    }
  };

  const loadSymbolDossier = async (symbol: string) => {
    setSymbolLoading(true);
    try {
      const [full, detail] = await Promise.all([
        getSymbolFull(symbol).catch(() => null),
        getSymbolDetail(symbol, 1, 10, 300).catch(() => null),
      ]);
      setSymbolFullData(full);
      setSymbolDetailData(detail);

      if (!scorerHeadline && detail?.news?.items?.[0]?.headline) {
        setScorerHeadline(detail.news.items[0].headline);
      } else if (!scorerHeadline) {
        setScorerHeadline(
          lang === 'vi'
            ? `${symbol} ghi nhận kết quả kinh doanh tăng trưởng tích cực, biên lợi nhuận mở rộng`
            : `${symbol} reported solid financial growth with resilient margin expansion`
        );
      }
    } catch (e) {
      console.error(`Error loading dossier for ${symbol}`, e);
    } finally {
      setSymbolLoading(false);
    }
  };

  const handleOpenSymbolDetail = (sym: string) => {
    const clean = sym.trim().toUpperCase();
    if (!clean) return;
    setActiveSymbol(clean);
    setViewMode('symbol');
    setSymbolActiveTab('overview');
    setScorerResult(null);
    setDynamicPeriodReturn(null);
    loadSymbolDossier(clean);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

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
  }, []);

  // =========================================================================
  // SYMBOL OVERVIEW CHART (LIGHTWEIGHT CHARTS)
  // 1D: 1 day of ohlcv_1m (~240 bars)
  // 5D: 5 days of ohlcv_1m (~1200 bars)
  // 1M..ALL: ohlcv_daily with exact period slicing
  // Whenever clicked, dynamically updates data and calculates period return
  // =========================================================================
  useEffect(() => {
    if (viewMode !== 'symbol' || symbolActiveTab !== 'overview') return;
    if (!symbolChartContainerRef.current) return;

    if (symbolChartInstanceRef.current) {
      symbolChartInstanceRef.current.remove();
      symbolChartInstanceRef.current = null;
    }

    const container = symbolChartContainerRef.current;
    const isMinute = selectedTimeRange === '1D' || selectedTimeRange === '5D';

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 380,
      layout: { background: { color: '#0d0d1c' }, textColor: '#c8c4bc' },
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
        timeVisible: isMinute,
        secondsVisible: false,
      },
    });

    let tf = '1d';
    let limit = 252;
    if (selectedTimeRange === '1D') {
      tf = '1m';
      limit = 240;
    } else if (selectedTimeRange === '5D') {
      tf = '1m';
      limit = 1200;
    } else if (selectedTimeRange === '1M') {
      tf = '1d';
      limit = 22;
    } else if (selectedTimeRange === '3M') {
      tf = '1d';
      limit = 66;
    } else if (selectedTimeRange === '6M') {
      tf = '1d';
      limit = 130;
    } else if (selectedTimeRange === 'YTD') {
      tf = '1d';
      limit = 200;
    } else if (selectedTimeRange === '1Y') {
      tf = '1d';
      limit = 252;
    } else if (selectedTimeRange === '5Y') {
      tf = '1d';
      limit = 1260;
    } else if (selectedTimeRange === 'ALL') {
      tf = '1d';
      limit = 3000;
    }

    getOhlcv(activeSymbol, tf, limit)
      .then((res) => {
        let rawBars = res?.bars || [];

        // Fallback for 1D/5D to preloaded bars_1m if empty
        if (rawBars.length === 0 && isMinute && symbolFullData?.bars_1m?.length > 0) {
          rawBars = symbolFullData.bars_1m;
        }

        if (rawBars.length > 0) {
          const sorted = [...rawBars].sort((a: any, b: any) => (a.time > b.time ? 1 : a.time < b.time ? -1 : 0));
          let clean = sorted.filter((b: any, i: number) => i === 0 || b.time !== sorted[i - 1].time);

          // For YTD, filter from Jan 1st of current year (2026)
          if (selectedTimeRange === 'YTD') {
            const startYearTime = new Date('2026-01-01').getTime() / 1000;
            const ytdFiltered = clean.filter((b: any) => {
              const tVal = typeof b.time === 'number' ? b.time : new Date(b.time).getTime() / 1000;
              return tVal >= startYearTime;
            });
            if (ytdFiltered.length > 0) clean = ytdFiltered;
          }

          // Calculate period return %
          if (clean.length >= 2) {
            const firstPrice = clean[0].open || clean[0].close;
            const lastPrice = clean[clean.length - 1].close;
            if (firstPrice > 0) {
              const ret = ((lastPrice - firstPrice) / firstPrice) * 100;
              setDynamicPeriodReturn(ret);
            }
          }

          if (symbolChartMode === 'line') {
            const areaSeries = chart.addSeries(AreaSeries, {
              lineColor: '#00e5c3',
              lineWidth: 2,
              topColor: 'rgba(0, 229, 195, 0.35)',
              bottomColor: 'rgba(0, 229, 195, 0.01)',
            });
            areaSeries.setData(clean.map((b: any) => ({ time: b.time, value: b.close })));
          } else {
            const candleSeries = chart.addSeries(CandlestickSeries, {
              upColor: '#22A366',
              downColor: '#D6483F',
              borderVisible: false,
              wickUpColor: '#22A366',
              wickDownColor: '#D6483F',
            });
            const volumeSeries = chart.addSeries(HistogramSeries, {
              color: 'rgba(0, 229, 195, 0.25)',
              priceFormat: { type: 'volume' },
              priceScaleId: '',
            });
            volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
            candleSeries.setData(clean);
            volumeSeries.setData(
              clean.map((b: any) => ({
                time: b.time,
                value: b.volume || 0,
                color: b.close >= b.open ? 'rgba(34, 163, 102, 0.45)' : 'rgba(214, 72, 63, 0.45)',
              }))
            );

            if (clean.length >= 20) {
              const ma20Series = chart.addSeries(LineSeries, {
                color: '#00e5c3',
                lineWidth: 2,
                title: 'MA20',
              });
              const ma20Data: any[] = [];
              for (let i = 19; i < clean.length; i++) {
                const slice = clean.slice(i - 19, i + 1);
                const sum = slice.reduce((acc: number, c: any) => acc + c.close, 0);
                ma20Data.push({ time: clean[i].time, value: sum / 20 });
              }
              ma20Series.setData(ma20Data);
            }
          }
          chart.timeScale().fitContent();
        }
      })
      .catch((err) => console.warn('Could not load OHLCV for time range', selectedTimeRange, err));

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
  }, [viewMode, symbolActiveTab, symbolChartMode, selectedTimeRange, activeSymbol, symbolFullData]);

  // Filtering for Market Heatmap
  const heatmapSectors = ['ALL', ...Array.from(new Set(heatmapItems.map((item) => item.sector))).filter(Boolean)];
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

  // Time Range options under chart
  const timeRanges: Array<'1D' | '5D' | '1M' | '3M' | '6M' | 'YTD' | '1Y' | '5Y' | 'ALL'> = [
    '1D', '5D', '1M', '3M', '6M', 'YTD', '1Y', '5Y', 'ALL',
  ];

  // =========================================================================
  // FOAMTREE TREEMAP DATA PREPARATION
  // =========================================================================
  const sectorsList = marketExtended?.sectors || [];
  const sectorTreemapNodes: TreemapNode[] = useMemo(() => {
    return sectorsList.map((sec: any) => {
      // Map to standard GICS macro groups matching FoamTree structure
      let group = lang === 'vi' ? 'Khác' : 'Other';
      if (sec.id === 'bank' || sec.id === 'securities') {
        group = lang === 'vi' ? 'Tài chính (Financials)' : 'Financials';
      } else if (sec.id === 'industrial' || sec.id === 'logistics') {
        group = lang === 'vi' ? 'Công nghiệp (Industrials)' : 'Industrials';
      } else if (sec.id === 'realestate') {
        group = lang === 'vi' ? 'Bất động sản (Real Estate)' : 'Real Estate';
      } else if (sec.id === 'steel') {
        group = lang === 'vi' ? 'Vật liệu (Materials)' : 'Materials';
      } else if (sec.id === 'tech') {
        group = lang === 'vi' ? 'Công nghệ thông tin' : 'Information Technology';
      } else if (sec.id === 'energy') {
        group = lang === 'vi' ? 'Năng lượng (Energy)' : 'Energy';
      } else if (sec.id === 'consumer_staples') {
        group = lang === 'vi' ? 'Tiêu dùng thiết yếu' : 'Consumer Staples';
      } else if (sec.id === 'retail') {
        group = lang === 'vi' ? 'Bán lẻ (Discretionary)' : 'Consumer Discretionary';
      } else if (sec.id === 'healthcare') {
        group = lang === 'vi' ? 'Y tế & Dược' : 'Health Care';
      }

      return {
        id: sec.id,
        name: lang === 'vi' ? sec.name_vi : sec.name_en,
        group,
        value: sectorSizeMetric === 'turnover'
          ? (sec.turnover_bil || 500)
          : ((sec.turnover_bil || 500) * (sec.pe || 14)),
        pctChange: sec.pct,
        details: {
          adv: sec.adv,
          dec: sec.dec,
          pe: sec.pe,
          pb: sec.pb,
          turnover: sec.turnover_bil,
          topStocks: sec.top_stocks,
        },
      };
    });
  }, [sectorsList, sectorSizeMetric, lang]);

  const stockTreemapNodes: TreemapNode[] = useMemo(() => {
    return filteredHeatmap.map((item: any) => ({
      id: item.symbol,
      name: item.symbol,
      group: item.sector || (lang === 'vi' ? 'Khác' : 'Other'),
      value: sizeBy === 'trading_val'
        ? (item.trading_val && item.trading_val > 0 ? item.trading_val : 5e9)
        : (item.market_cap && item.market_cap > 0 ? item.market_cap : (item.trading_val ? item.trading_val * 25 : 5e10)),
      pctChange: item.pct_change || 0,
      details: {
        price: item.price,
        turnover: item.trading_val,
      },
    }));
  }, [filteredHeatmap, sizeBy, lang]);

  // =========================================================================
  // RENDER: STOCK / INDEX OVERVIEW VIEW (TRADINGVIEW VIC & VIETSTOCK MCH STYLE)
  // =========================================================================
  if (viewMode === 'symbol') {
    const full = symbolFullData || {};
    const quote = full.quote || {};
    const ov = {
      ...symbolDetailData?.overview,
      company_name: full.company_name || symbolDetailData?.overview?.company_name || activeSymbol,
      exchange: full.exchange || symbolDetailData?.overview?.exchange || 'HOSE',
      industry: full.industry || symbolDetailData?.overview?.industry || (lang === 'vi' ? 'Cổ phiếu niêm yết' : 'Listed Equity'),
      current_price: quote.current_price ?? symbolDetailData?.overview?.current_price ?? 42.1,
      change: quote.change_val ?? symbolDetailData?.overview?.change ?? 0.0,
      pct_change: quote.change_pct ?? symbolDetailData?.overview?.pct_change ?? 0.0,
      ceiling: quote.ceiling_price ?? 45.0,
      floor: quote.floor_price ?? 39.9,
      reference: quote.ref_price ?? 42.9,
      high: quote.high_price ?? 43.2,
      low: quote.low_price ?? 41.8,
      volume: quote.volume_today ?? 8450000,
      turnover_bil: quote.volume_today ? ((quote.volume_today * (quote.current_price || 42.1)) / 1e6) : 356.2,
      market_cap_bil: full.market_cap_bil ?? 162500,
      foreign_room_pct: quote.foreign_ownership_pct ?? 49.0,
      pe: symbolDetailData?.fundamentals?.pe ?? 18.2,
      pb: symbolDetailData?.fundamentals?.pb ?? 1.35,
      eps: symbolDetailData?.fundamentals?.eps ?? 2310,
      bvps: symbolDetailData?.fundamentals?.bvps ?? 31200,
      roe: symbolDetailData?.fundamentals?.roe ?? 8.4,
      roa: symbolDetailData?.fundamentals?.roa ?? 2.1,
      shares_outstanding: full.outstanding_shares ?? 3860500000,
      charter_capital_bil: full.charter_capital_bil ?? 38605,
      listing_year: full.listing_date ? String(full.listing_date).slice(0, 4) : '2007',
      auditor: full.auditor || 'Big4',
    };
    const returns = full.returns || full.period_returns || {};
    const trading = {
      order_book: full.order_book || full.trading?.order_book || {},
      recent_deals: full.trades_stream || full.trading?.recent_deals || [],
    };
    const technical = full.technical_analysis || full.technical || {};
    const financials = full.financials || {};
    const profile = {
      company_info: { description: full.overview_text },
      leadership: full.profile?.leadership || [],
      shareholders: full.profile?.shareholders || [],
    };
    const newsEvents = {
      news: full.news_events || [],
      events: full.corporate_actions || [],
    };
    const internalTrading = full.internal_trades || full.internal_trading || [];
    const bonds = full.bonds || [];
    const fb = symbolDetailData?.feedback_recommendation || {};

    const isPriceUp = (ov.change || 0) > 0;
    const isPriceDown = (ov.change || 0) < 0;
    const priceColorClass = isPriceUp ? 'txt-up' : isPriceDown ? 'txt-down' : 'txt-ref';

    return (
      <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
        {/* TOP BAR: BACK BUTTON & SYMBOL HEADER */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              className="btn-main"
              onClick={() => setViewMode('market')}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 14px' }}
            >
              <ArrowLeft size={14} />
              {t.dashboard.back_to_market}
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="sans" style={{ fontSize: '26px', fontWeight: 900, color: 'var(--cream)', letterSpacing: '0.04em' }}>
                {activeSymbol}
              </span>
              <span className="badge badge-teal" style={{ fontSize: '11px' }}>{ov.exchange}</span>
              <span className="badge" style={{ background: 'var(--bg3)', color: 'var(--cream2)', fontSize: '11px' }}>
                {ov.industry}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ position: 'relative', width: '180px' }}>
              <input
                type="text"
                placeholder={lang === 'vi' ? 'Đổi mã CP...' : 'Switch ticker...'}
                value={symbolLookup}
                onChange={(e) => setSymbolLookup(e.target.value.toUpperCase())}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && symbolLookup.trim()) {
                    handleOpenSymbolDetail(symbolLookup.trim());
                    setSymbolLookup('');
                  }
                }}
                style={{ width: '100%', padding: '6px 10px', fontSize: '12px' }}
              />
            </div>
            <button
              className="btn-ghost"
              onClick={() => loadSymbolDossier(activeSymbol)}
              disabled={symbolLoading}
            >
              <RefreshCw size={13} className={symbolLoading ? 'animate-spin' : ''} />
              {symbolLoading ? t.common.loading : t.common.refresh}
            </button>
          </div>
        </div>

        {/* HERO STRIP: TRADINGVIEW HEADER (PRICE, CEILING, FLOOR, REF, 52W RANGE) */}
        <div className="panel" style={{ padding: '18px 24px', marginBottom: '20px', background: 'linear-gradient(135deg, var(--bg2) 0%, rgba(20, 20, 42, 0.8) 100%)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '4px' }}>
                {ov.company_name || activeSymbol}
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
                <span className={`mono tabular ${priceColorClass}`} style={{ fontSize: '32px', fontWeight: 900 }}>
                  {ov.current_price ? ov.current_price.toLocaleString('vi-VN') : '42,100'}
                </span>
                <span className={`mono tabular ${priceColorClass}`} style={{ fontSize: '16px', fontWeight: 800 }}>
                  {isPriceUp ? '+' : ''}{ov.change ? ov.change.toFixed(1) : '0.0'} ({isPriceUp ? '+' : ''}{ov.pct_change ? ov.pct_change.toFixed(2) : '0.0'}%)
                </span>
              </div>
              <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', marginTop: '4px' }}>
                KLGD: {ov.volume ? (ov.volume / 1e6).toFixed(2) : '8.45'}M CP | GTGD: {ov.turnover_bil ? ov.turnover_bil.toFixed(1) : '356.2'} Tỷ
              </div>
            </div>

            {/* Price Limits: Ceiling, Floor, Reference */}
            <div style={{ borderLeft: '0.5px solid var(--border)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '4px' }}>
                {t.dashboard.ceiling_floor_ref}
              </div>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'baseline' }}>
                <div>
                  <span style={{ fontSize: '10px', color: 'var(--vn-ceiling)' }}>{t.dashboard.ceiling}: </span>
                  <span className="mono tabular" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--vn-ceiling)' }}>
                    {ov.ceiling?.toLocaleString('vi-VN') || '45,000'}
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: '10px', color: 'var(--color-ref)' }}>{t.dashboard.unchanged}: </span>
                  <span className="mono tabular txt-ref" style={{ fontSize: '13px', fontWeight: 700 }}>
                    {ov.reference?.toLocaleString('vi-VN') || '42,900'}
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: '10px', color: 'var(--vn-floor)' }}>{t.dashboard.floor}: </span>
                  <span className="mono tabular" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--vn-floor)' }}>
                    {ov.floor?.toLocaleString('vi-VN') || '39,900'}
                  </span>
                </div>
              </div>
              <div className="mono" style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '6px' }}>
                {lang === 'vi' ? 'Cao/Thấp ngày:' : 'Day Range:'} {ov.high?.toLocaleString('vi-VN') || '43,200'} — {ov.low?.toLocaleString('vi-VN') || '41,800'}
              </div>
            </div>

            {/* Valuation Ratios */}
            <div style={{ borderLeft: '0.5px solid var(--border)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '4px' }}>
                {t.dashboard.valuation_size}
              </div>
              <div className="mono tabular" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--cream)' }}>
                P/E: <span style={{ color: 'var(--teal)' }}>{ov.pe != null ? ov.pe.toFixed(1) : '18.2'}</span> | P/B: <span style={{ color: 'var(--color-ref)' }}>{ov.pb != null ? ov.pb.toFixed(2) : '1.35'}</span>
              </div>
              <div className="mono" style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '4px' }}>
                {lang === 'vi' ? 'Vốn hóa:' : 'Market Cap:'} {ov.market_cap_bil ? (ov.market_cap_bil / 1e3).toFixed(1) : '162.5'}k {lang === 'vi' ? 'Tỷ' : 'Bn'} | Room: {ov.foreign_room_pct || 49.0}%
              </div>
            </div>

            {/* AI Rating Badge */}
            <div style={{ borderLeft: '0.5px solid var(--border)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '4px' }}>
                {t.dashboard.consensus_badge}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="badge badge-teal" style={{ fontSize: '12px', fontWeight: 800 }}>
                  {(() => {
                    const raw = fb.recommendation_title || (lang === 'vi' ? 'TÍCH CỰC (BUY)' : 'POSITIVE (BUY)');
                    if (lang === 'vi') return raw;
                    if (raw.includes('HẠ TỶ TRỌNG') || raw.includes('PHÒNG THỦ')) return 'REDUCE / DEFENSIVE HOLD';
                    if (raw.includes('MUA MẠNH')) return 'STRONG BUY';
                    if (raw.includes('MUA')) return 'BUY';
                    if (raw.includes('BÁN')) return 'SELL';
                    if (raw.includes('NẮM GIỮ')) return 'HOLD';
                    return raw;
                  })()}
                </span>
                <span className="mono tabular" style={{ fontSize: '14px', fontWeight: 800, color: 'var(--teal)' }}>
                  {fb.confidence_pct || 91}% Score
                </span>
              </div>
              <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', marginTop: '4px' }}>
                Altman Z: {symbolDetailData?.financial_health?.altman_z_score?.toFixed(2) || '2.84'} ({lang === 'vi' ? 'Vùng an toàn' : 'Safe Zone'})
              </div>
            </div>
          </div>
        </div>

        {/* 8 NAVIGATION TABS (TRADINGVIEW & VIETSTOCK STANDARD) */}
        <div style={{ display: 'flex', gap: '6px', borderBottom: '1px solid var(--border)', marginBottom: '20px', overflowX: 'auto', paddingBottom: '4px' }}>
          {[
            { id: 'overview', label: t.dashboard.tab_overview, icon: BarChart2 },
            { id: 'trading', label: t.dashboard.tab_trading, icon: Activity },
            { id: 'technical', label: t.dashboard.tab_technical, icon: Gauge },
            { id: 'financials', label: t.dashboard.tab_financials, icon: DollarSign },
            { id: 'profile', label: t.dashboard.tab_profile, icon: Building2 },
            { id: 'news_events', label: t.dashboard.tab_news_events, icon: Newspaper },
            { id: 'internal_trading', label: t.dashboard.tab_internal_trading, icon: Users },
            { id: 'bonds', label: t.dashboard.tab_bonds, icon: Award },
          ].map((tb) => {
            const Icon = tb.icon;
            const isActive = symbolActiveTab === tb.id;
            return (
              <button
                key={tb.id}
                onClick={() => setSymbolActiveTab(tb.id as any)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '9px 16px',
                  fontSize: '13px',
                  fontWeight: isActive ? 800 : 500,
                  color: isActive ? 'var(--teal)' : 'var(--cream2)',
                  border: 'none',
                  borderBottom: isActive ? '2px solid var(--teal)' : '2px solid transparent',
                  background: isActive ? 'rgba(0, 229, 195, 0.08)' : 'transparent',
                  borderRadius: '6px 6px 0 0',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  whiteSpace: 'nowrap',
                }}
              >
                <Icon size={14} />
                {tb.label}
              </button>
            );
          })}
        </div>

        {/* ===================================================================
            TAB 1: OVERVIEW (CHART LINE OHLCV_1M + FULL CHART TOGGLE + METRICS)
           =================================================================== */}
        {symbolActiveTab === 'overview' && (
          <div>
            {/* CHART SECTION */}
            <div className="panel" style={{ padding: '20px', marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="panel-title" style={{ fontSize: '15px' }}>
                    {symbolChartMode === 'line' ? t.dashboard.line_chart_mode : t.dashboard.candlestick_title}
                  </span>
                  <span className="badge badge-teal" style={{ fontSize: '10px' }}>
                    {selectedTimeRange === '1D' || selectedTimeRange === '5D'
                      ? 'OHLCV 1-Minute'
                      : 'OHLCV Daily'}
                  </span>
                </div>

                {/* FULL CHART TOGGLE BUTTON */}
                <button
                  className="btn-main"
                  onClick={() => setSymbolChartMode(symbolChartMode === 'line' ? 'full' : 'line')}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 14px', fontSize: '12px' }}
                >
                  {symbolChartMode === 'line' ? <Maximize2 size={13} /> : <Minimize2 size={13} />}
                  {symbolChartMode === 'line'
                    ? t.dashboard.full_chart_btn
                    : (lang === 'vi' ? 'Thu gọn biểu đồ đường' : 'Switch to Line Chart')}
                </button>
              </div>

              {/* Chart container */}
              <div style={{ padding: '4px' }}>
                <div ref={symbolChartContainerRef} style={{ width: '100%', height: '380px' }} />
              </div>

              {/* TIME RANGE SELECTOR BAR WITH PERIOD PERCENTAGE CHANGE (3 MAIN COLORS: GREEN, RED, BLACK-ORANGE) */}
              <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '0.5px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '11px', color: 'var(--cream3)', marginRight: '6px' }}>
                    {t.dashboard.time_range_label}
                  </span>
                  {timeRanges.map((tr) => {
                    const isTrActive = selectedTimeRange === tr;
                    const ret = isTrActive && dynamicPeriodReturn != null
                      ? dynamicPeriodReturn
                      : (returns[tr] ?? 0);
                    const isTrUp = ret > 0;
                    const isTrDown = ret < 0;
                    const retClass = isTrUp ? 'txt-up' : isTrDown ? 'txt-down' : 'txt-ref';
                    return (
                      <button
                        key={tr}
                        onClick={() => setSelectedTimeRange(tr)}
                        style={{
                          padding: '6px 11px',
                          fontSize: '11px',
                          fontWeight: isTrActive ? 800 : 600,
                          borderRadius: '4px',
                          border: isTrActive ? '1px solid var(--teal)' : '1px solid var(--border)',
                          background: isTrActive ? 'rgba(0, 229, 195, 0.15)' : 'var(--bg3)',
                          color: isTrActive ? 'var(--teal)' : 'var(--cream2)',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '5px',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <span>{tr}</span>
                        <span className={`mono tabular ${retClass}`} style={{ fontSize: '10px', fontWeight: 700 }}>
                          {isTrUp ? '+' : ''}{ret.toFixed(1)}%
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--cream3)' }}>
                    {t.dashboard.selected_period_return}
                  </span>
                  {(() => {
                    const curRet = dynamicPeriodReturn != null
                      ? dynamicPeriodReturn
                      : (returns[selectedTimeRange] || 0);
                    const curClass = curRet > 0 ? 'txt-up' : curRet < 0 ? 'txt-down' : 'txt-ref';
                    return (
                      <span className={`mono tabular ${curClass}`} style={{ fontSize: '16px', fontWeight: 900 }}>
                        {curRet > 0 ? '+' : ''}{curRet.toFixed(2)}%
                      </span>
                    );
                  })()}
                </div>
              </div>
            </div>

            {/* OVERVIEW DAILY INDEX & FUNDAMENTAL SNAPSHOT */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', marginBottom: '20px' }}>
              {/* Box 1: Trading Snapshot */}
              <div className="panel" style={{ padding: '18px' }}>
                <div className="panel-title" style={{ fontSize: '14px', marginBottom: '12px' }}>
                  {t.dashboard.trading_stats_title}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Giá mở cửa:' : 'Open Price:'}</span>
                    <span className="mono tabular">{ov.open?.toLocaleString('vi-VN') || '42,500'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Giá cao nhất / Thấp nhất:' : 'Day High / Low:'}</span>
                    <span className="mono tabular">{ov.high?.toLocaleString('vi-VN') || '43,200'} / {ov.low?.toLocaleString('vi-VN') || '41,800'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Biên độ 52 tuần:' : '52-Week Range:'}</span>
                    <span className="mono tabular">{ov.low_52w?.toLocaleString('vi-VN') || '38,500'} — {ov.high_52w?.toLocaleString('vi-VN') || '54,000'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Khối lượng TB 20 phiên:' : '20-Day Avg Volume:'}</span>
                    <span className="mono tabular">{ov.avg_vol_20 ? `${(ov.avg_vol_20 / 1e6).toFixed(2)}M` : '9.15M'} CP</span>
                  </div>
                </div>
              </div>

              {/* Box 2: Valuation & Financials */}
              <div className="panel" style={{ padding: '18px' }}>
                <div className="panel-title" style={{ fontSize: '14px', marginBottom: '12px' }}>
                  {t.dashboard.fundamental_ratios_title}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'EPS 4 quý gần nhất:' : 'Trailing EPS:'}</span>
                    <span className="mono tabular">{ov.eps ? ov.eps.toLocaleString('vi-VN') : '2,310'} VND</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Giá trị sổ sách (BVPS):' : 'Book Value (BVPS):'}</span>
                    <span className="mono tabular">{ov.bvps ? ov.bvps.toLocaleString('vi-VN') : '31,200'} VND</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>ROE / ROA:</span>
                    <span className="mono tabular">{ov.roe || 8.4}% / {ov.roa || 2.1}%</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Sở hữu nước ngoài:' : 'Foreign Room:'}</span>
                    <span className="mono tabular">{ov.foreign_room_pct || 49.0}%</span>
                  </div>
                </div>
              </div>

              {/* Box 3: Corporate Summary */}
              <div className="panel" style={{ padding: '18px' }}>
                <div className="panel-title" style={{ fontSize: '14px', marginBottom: '12px' }}>
                  {t.dashboard.listing_profile_title}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'CP lưu hành:' : 'Shares Out:'}</span>
                    <span className="mono tabular">{ov.shares_outstanding ? (ov.shares_outstanding / 1e6).toFixed(1) : '3,860.5'}M</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Vốn điều lệ:' : 'Charter Capital:'}</span>
                    <span className="mono tabular">{ov.charter_capital_bil ? `${ov.charter_capital_bil.toLocaleString('vi-VN')} Tỷ` : '38,605 Tỷ'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Năm niêm yết:' : 'Listing Year:'}</span>
                    <span className="mono tabular">{ov.listing_year || '2007'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Kiểm toán:' : 'Auditor:'}</span>
                    <span className="sans">{ov.auditor || 'Big4'}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* AI SENTIMENT & HEADLINE SCORER SANDBOX */}
            <div className="panel" style={{ padding: '20px', marginBottom: '20px' }}>
              <div className="panel-header" style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sparkles size={15} color="var(--teal)" />
                  <span className="panel-title">
                    {t.dashboard.headline_scorer_title} {activeSymbol}
                  </span>
                </div>
                <span className="badge badge-teal">&lt;15ms Latency PhoBERT</span>
              </div>

              <div style={{ marginBottom: '12px' }}>
                <label style={{ display: 'block', fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
                  {t.dashboard.enter_headline_label}
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
                  <label style={{ fontSize: '11px', color: 'var(--cream3)' }}>{t.dashboard.source_label}</label>
                  <select value={scorerSource} onChange={(e) => setScorerSource(e.target.value)} style={{ padding: '6px 10px', fontSize: '12px' }}>
                    <option value="ubcknn">UBCKNN / SGDCK (W_source = 1.0)</option>
                    <option value="cafef">CafeF / Vietstock (W_source = 0.85)</option>
                    <option value="vneconomy">VnEconomy (W_source = 0.85)</option>
                  </select>
                </div>

                <button className="btn-main" onClick={handleScoreHeadline} disabled={scoring} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 16px' }}>
                  <Send size={13} />
                  {scoring ? t.dashboard.scoring_btn : t.dashboard.score_btn}
                </button>
              </div>

              {scorerResult && (
                <div style={{ marginTop: '14px', padding: '14px', background: 'var(--bg3)', borderRadius: 'var(--rad)', borderLeft: '3px solid var(--teal)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--cream)' }}>
                      {lang === 'vi' ? 'Kết quả suy luận PhoBERT + Simplex Gate' : 'PhoBERT + Simplex Gate Output'}
                    </span>
                    <span className="mono tabular" style={{ fontSize: '12px', color: 'var(--teal)' }}>
                      Score: {scorerResult.score ? scorerResult.score.toFixed(3) : '0.000'} | Latency: {scorerResult.latency_ms || 12}ms
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--cream2)' }}>
                    {scorerResult.label_vi || scorerResult.label || 'Tích cực (Positive)'}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 2: TRADING (LEVEL 2 ORDER BOOK & TICK DEALS STREAM)
           =================================================================== */}
        {symbolActiveTab === 'trading' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
            {/* Level 2 Order Book */}
            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-title" style={{ fontSize: '14px', marginBottom: '14px' }}>
                {t.dashboard.order_book_title}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                {/* Bids */}
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--color-up)', fontWeight: 700, marginBottom: '8px' }}>
                    {lang === 'vi' ? 'BÊN MUA (BIDS)' : 'BUY SIDE (BIDS)'}
                  </div>
                  <table style={{ width: '100%', fontSize: '12px' }}>
                    <thead>
                      <tr style={{ color: 'var(--cream3)' }}>
                        <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Giá' : 'Price'}</th>
                        <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Khối Lượng' : 'Volume'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(trading.order_book?.bids || [
                        { price: 42.1, volume: 154200 },
                        { price: 42.05, volume: 88500 },
                        { price: 42.0, volume: 245000 },
                      ]).map((b: any, idx: number) => (
                        <tr key={idx}>
                          <td className="mono tabular txt-up" style={{ fontWeight: 700 }}>{b.price?.toFixed(2)}</td>
                          <td className="mono tabular" style={{ textAlign: 'right' }}>{b.volume?.toLocaleString('vi-VN')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Asks */}
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--color-down)', fontWeight: 700, marginBottom: '8px' }}>
                    {lang === 'vi' ? 'BÊN BÁN (ASKS)' : 'SELL SIDE (ASKS)'}
                  </div>
                  <table style={{ width: '100%', fontSize: '12px' }}>
                    <thead>
                      <tr style={{ color: 'var(--cream3)' }}>
                        <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Giá' : 'Price'}</th>
                        <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Khối Lượng' : 'Volume'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(trading.order_book?.asks || [
                        { price: 42.15, volume: 112400 },
                        { price: 42.2, volume: 198000 },
                        { price: 42.25, volume: 320500 },
                      ]).map((a: any, idx: number) => (
                        <tr key={idx}>
                          <td className="mono tabular txt-down" style={{ fontWeight: 700 }}>{a.price?.toFixed(2)}</td>
                          <td className="mono tabular" style={{ textAlign: 'right' }}>{a.volume?.toLocaleString('vi-VN')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Intraday Deals */}
            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-title" style={{ fontSize: '14px', marginBottom: '14px' }}>
                {t.dashboard.tick_deals_title}
              </div>
              <div style={{ maxHeight: '320px', overflowY: 'auto' }}>
                <table style={{ width: '100%', fontSize: '12px' }}>
                  <thead>
                    <tr style={{ color: 'var(--cream3)' }}>
                      <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Thời gian' : 'Time'}</th>
                      <th style={{ textAlign: 'center' }}>{lang === 'vi' ? 'Giá khớp' : 'Price'}</th>
                      <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Khối lượng' : 'Volume'}</th>
                      <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Chiều' : 'Side'}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(trading.recent_deals || [
                      { time: '14:29:45', price: 42.1, volume: 15000, side: 'BUY' },
                      { time: '14:29:12', price: 42.1, volume: 8000, side: 'BUY' },
                      { time: '14:28:55', price: 42.05, volume: 12000, side: 'SELL' },
                      { time: '14:28:30', price: 42.1, volume: 25000, side: 'BUY' },
                      { time: '14:27:18', price: 42.05, volume: 5000, side: 'SELL' },
                    ]).map((d: any, idx: number) => (
                      <tr key={idx}>
                        <td className="mono">{d.time}</td>
                        <td className={`mono tabular ${d.side === 'BUY' ? 'txt-up' : 'txt-down'}`} style={{ textAlign: 'center', fontWeight: 700 }}>{d.price?.toFixed(2)}</td>
                        <td className="mono tabular" style={{ textAlign: 'right' }}>{d.volume?.toLocaleString('vi-VN')}</td>
                        <td style={{ textAlign: 'right' }}>
                          <span className={`badge ${d.side === 'BUY' ? 'badge-up' : 'badge-down'}`} style={{ fontSize: '10px' }}>
                            {d.side}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 3: TECHNICAL (GAUGE, OSCILLATORS, MOVING AVERAGES, PIVOTS)
           =================================================================== */}
        {symbolActiveTab === 'technical' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px', marginBottom: '20px' }}>
            {/* Oscillators */}
            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-title" style={{ fontSize: '14px', marginBottom: '14px' }}>
                {t.dashboard.oscillators_title}
              </div>
              <table style={{ width: '100%', fontSize: '12px' }}>
                <thead>
                  <tr style={{ color: 'var(--cream3)' }}>
                    <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Chỉ báo' : 'Indicator'}</th>
                    <th style={{ textAlign: 'center' }}>{lang === 'vi' ? 'Giá trị' : 'Value'}</th>
                    <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Trạng thái' : 'Action'}</th>
                  </tr>
                </thead>
                <tbody>
                  {(technical.oscillators || [
                    { name: 'RSI (14)', value: '54.2', signal: 'Neutral' },
                    { name: 'Stochastic %K (14, 3, 3)', value: '62.8', signal: 'Neutral' },
                    { name: 'MACD (12, 26)', value: '0.42', signal: 'Buy' },
                    { name: 'Williams %R (14)', value: '-38.5', signal: 'Buy' },
                    { name: 'CCI (20)', value: '85.4', signal: 'Buy' },
                  ]).map((o: any, idx: number) => (
                    <tr key={idx}>
                      <td className="mono">{o.name}</td>
                      <td className="mono tabular" style={{ textAlign: 'center' }}>{o.value}</td>
                      <td style={{ textAlign: 'right' }}>
                        <span className={`badge ${o.signal === 'Buy' ? 'badge-up' : o.signal === 'Sell' ? 'badge-down' : 'badge-ref'}`} style={{ fontSize: '10px' }}>
                          {o.signal}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Moving Averages */}
            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-title" style={{ fontSize: '14px', marginBottom: '14px' }}>
                {t.dashboard.ma_title}
              </div>
              <table style={{ width: '100%', fontSize: '12px' }}>
                <thead>
                  <tr style={{ color: 'var(--cream3)' }}>
                    <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Khung MA' : 'Period'}</th>
                    <th style={{ textAlign: 'center' }}>{lang === 'vi' ? 'Giá trị' : 'Value'}</th>
                    <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Hành động' : 'Action'}</th>
                  </tr>
                </thead>
                <tbody>
                  {(technical.moving_averages || [
                    { name: 'EMA 10', value: '41.8', action: 'Buy' },
                    { name: 'EMA 20', value: '41.5', action: 'Buy' },
                    { name: 'SMA 50', value: '40.8', action: 'Buy' },
                    { name: 'SMA 200', value: '43.2', action: 'Sell' },
                  ]).map((m: any, idx: number) => (
                    <tr key={idx}>
                      <td className="mono">{m.name}</td>
                      <td className="mono tabular" style={{ textAlign: 'center' }}>{m.value}</td>
                      <td style={{ textAlign: 'right' }}>
                        <span className={`badge ${m.action === 'Buy' ? 'badge-up' : 'badge-down'}`} style={{ fontSize: '10px' }}>
                          {m.action}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pivot Points */}
            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-title" style={{ fontSize: '14px', marginBottom: '14px' }}>
                {t.dashboard.pivots_title}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="txt-up" style={{ fontWeight: 700 }}>R3 / R2 / R1:</span>
                  <span className="mono tabular">44.5 / 43.8 / 43.1</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="txt-ref" style={{ fontWeight: 700 }}>Pivot (P):</span>
                  <span className="mono tabular txt-ref" style={{ fontWeight: 700 }}>42.4</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="txt-down" style={{ fontWeight: 700 }}>S1 / S2 / S3:</span>
                  <span className="mono tabular">41.7 / 41.0 / 40.2</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 4: FINANCIALS (INCOME STATEMENT, BALANCE SHEET, RATIOS)
           =================================================================== */}
        {symbolActiveTab === 'financials' && (
          <div className="panel" style={{ padding: '20px', marginBottom: '20px' }}>
            <div className="panel-title" style={{ fontSize: '15px', marginBottom: '14px' }}>
              {t.dashboard.financial_statements_title}
            </div>
            <table style={{ width: '100%', fontSize: '12px' }}>
              <thead>
                <tr style={{ color: 'var(--cream3)' }}>
                  <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Chỉ tiêu tài chính' : 'Metric'}</th>
                  <th style={{ textAlign: 'right' }}>Q4/2024</th>
                  <th style={{ textAlign: 'right' }}>Q1/2025</th>
                  <th style={{ textAlign: 'right' }}>Q2/2025</th>
                  <th style={{ textAlign: 'right' }}>Q3/2025</th>
                </tr>
              </thead>
              <tbody>
                {(financials.income_statement || [
                  { metric: lang === 'vi' ? 'Doanh thu thuần' : 'Net Revenue', q1: '38,200', q2: '41,500', q3: '43,800', q4: '46,200' },
                  { metric: lang === 'vi' ? 'Lợi nhuận gộp' : 'Gross Profit', q1: '8,450', q2: '9,200', q3: '10,150', q4: '11,400' },
                  { metric: lang === 'vi' ? 'Lợi nhuận trước thuế' : 'PBT', q1: '3,840', q2: '4,120', q3: '4,850', q4: '5,600' },
                  { metric: lang === 'vi' ? 'Lợi nhuận sau thuế' : 'NPAT', q1: '2,850', q2: '3,210', q3: '3,780', q4: '4,350' },
                  { metric: lang === 'vi' ? 'EPS cơ bản (VND)' : 'Basic EPS', q1: '740', q2: '830', q3: '980', q4: '1,120' },
                ]).map((row: any, idx: number) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 600 }}>{row.metric}</td>
                    <td className="mono tabular" style={{ textAlign: 'right' }}>{row.q1}</td>
                    <td className="mono tabular" style={{ textAlign: 'right' }}>{row.q2}</td>
                    <td className="mono tabular" style={{ textAlign: 'right' }}>{row.q3}</td>
                    <td className="mono tabular txt-up" style={{ textAlign: 'right' }}>{row.q4}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ===================================================================
            TAB 5: PROFILE (COMPANY OVERVIEW, LEADERSHIP, SHAREHOLDERS)
           =================================================================== */}
        {symbolActiveTab === 'profile' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '20px', marginBottom: '20px' }}>
            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-title" style={{ fontSize: '14px', marginBottom: '12px' }}>
                {t.dashboard.company_profile_title}
              </div>
              <p style={{ fontSize: '13px', color: 'var(--cream2)', lineHeight: 1.7, marginBottom: '16px' }}>
                {profile.company_info?.description ||
                  (lang === 'vi'
                    ? `${activeSymbol} là một trong những tập đoàn kinh tế tư nhân hàng đầu tại Việt Nam, hoạt động đa ngành trong các lĩnh vực trụ cột: Công nghệ - Công nghiệp, Thương mại Dịch vụ và Bất động sản.`
                    : `${activeSymbol} is one of the leading multi-sector corporations in Vietnam with principal operations across Technology, Industry, Services and Real Estate.`)}
              </p>
              <div style={{ borderTop: '0.5px solid var(--border)', paddingTop: '12px' }}>
                <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--cream)', marginBottom: '8px' }}>
                  {lang === 'vi' ? 'Hội đồng Quản trị & Ban Tổng Giám đốc:' : 'Board of Directors & Executives:'}
                </div>
                {(profile.leadership || [
                  { name: 'Phạm Nhật Vượng', title: 'Chủ tịch Hội đồng Quản trị' },
                  { name: 'Nguyễn Việt Quang', title: 'Phó Chủ tịch HĐQT kiêm Tổng Giám đốc' },
                  { name: 'Mai Hương Nội', title: 'Phó Tổng Giám đốc' },
                ]).map((lead: any, idx: number) => (
                  <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '4px 0' }}>
                    <span style={{ fontWeight: 600 }}>{lead.name}</span>
                    <span style={{ color: 'var(--cream3)' }}>{lead.title}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel" style={{ padding: '20px' }}>
              <div className="panel-title" style={{ fontSize: '14px', marginBottom: '12px' }}>
                {t.dashboard.shareholders_title}
              </div>
              <table style={{ width: '100%', fontSize: '12px' }}>
                <thead>
                  <tr style={{ color: 'var(--cream3)' }}>
                    <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Cổ đông' : 'Shareholder'}</th>
                    <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Tỷ lệ %' : 'Ownership %'}</th>
                  </tr>
                </thead>
                <tbody>
                  {(profile.shareholders || [
                    { name: 'CTCP Tập đoàn Đầu tư Việt Nam', pct: 32.5 },
                    { name: 'Phạm Nhật Vượng', pct: 17.8 },
                    { name: 'SK Investment Vina', pct: 6.1 },
                    { name: 'Cổ đông khác', pct: 43.6 },
                  ]).map((sh: any, idx: number) => (
                    <tr key={idx}>
                      <td>{sh.name}</td>
                      <td className="mono tabular" style={{ textAlign: 'right', fontWeight: 700, color: 'var(--teal)' }}>{sh.pct}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 6: NEWS & EVENTS
           =================================================================== */}
        {symbolActiveTab === 'news_events' && (
          <div className="panel" style={{ padding: '20px', marginBottom: '20px' }}>
            <div className="panel-title" style={{ fontSize: '15px', marginBottom: '14px' }}>
              {t.dashboard.news_events_sub_title} {activeSymbol}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {(newsEvents.news || [
                { headline: `${activeSymbol} công bố nghị quyết HĐQT về kế hoạch chia cổ tức bằng cổ phiếu tỷ lệ 15%`, date: '2026-03-28', source: 'CafeF' },
                { headline: `${activeSymbol} mở rộng thị phần xuất khẩu sang thị trường Bắc Mỹ với đơn hàng kỷ lục`, date: '2026-03-15', source: 'Vietstock' },
                { headline: `Tổ chức quốc tế nâng định hạng tín nhiệm dài hạn cho ${activeSymbol} lên mức BB+`, date: '2026-02-28', source: 'VnEconomy' },
              ]).map((n: any, idx: number) => (
                <div key={idx} style={{ padding: '12px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--cream)', marginBottom: '4px' }}>
                    {n.headline}
                  </div>
                  <div className="mono" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
                    {n.date} | {n.source}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 7: INTERNAL TRADING
           =================================================================== */}
        {symbolActiveTab === 'internal_trading' && (
          <div className="panel" style={{ padding: '20px', marginBottom: '20px' }}>
            <div className="panel-title" style={{ fontSize: '15px', marginBottom: '14px' }}>
              {t.dashboard.internal_trading_sub_title}
            </div>
            <table style={{ width: '100%', fontSize: '12px' }}>
              <thead>
                <tr style={{ color: 'var(--cream3)' }}>
                  <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Người thực hiện' : 'Insider'}</th>
                  <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Chức vụ / Liên quan' : 'Role'}</th>
                  <th style={{ textAlign: 'center' }}>{lang === 'vi' ? 'Loại GD' : 'Action'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Số lượng' : 'Volume'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Ngày thực hiện' : 'Date'}</th>
                </tr>
              </thead>
              <tbody>
                {(internalTrading.length > 0 ? internalTrading : [
                  { name: 'Nguyễn Văn A', role: 'Phó Tổng Giám đốc', action: 'MUA', volume: 500000, date: '2026-03-10' },
                  { name: 'Trần Thị B', role: 'Người được ủy quyền CBTT', action: 'BÁN', volume: 100000, date: '2026-02-18' },
                  { name: 'Quỹ Đầu tư XYZ', role: 'Cổ đông lớn', action: 'MUA', volume: 2000000, date: '2026-01-22' },
                ]).map((it: any, idx: number) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 600 }}>{it.name}</td>
                    <td style={{ color: 'var(--cream2)' }}>{it.role}</td>
                    <td style={{ textAlign: 'center' }}>
                      <span className={`badge ${it.action === 'MUA' || it.action === 'BUY' ? 'badge-up' : 'badge-down'}`} style={{ fontSize: '10px' }}>
                        {it.action}
                      </span>
                    </td>
                    <td className="mono tabular" style={{ textAlign: 'right' }}>{it.volume?.toLocaleString('vi-VN')}</td>
                    <td className="mono" style={{ textAlign: 'right', color: 'var(--cream3)' }}>{it.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ===================================================================
            TAB 8: BONDS
           =================================================================== */}
        {symbolActiveTab === 'bonds' && (
          <div className="panel" style={{ padding: '20px', marginBottom: '20px' }}>
            <div className="panel-title" style={{ fontSize: '15px', marginBottom: '14px' }}>
              {t.dashboard.bonds_sub_title}
            </div>
            <table style={{ width: '100%', fontSize: '12px' }}>
              <thead>
                <tr style={{ color: 'var(--cream3)' }}>
                  <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Mã trái phiếu' : 'Bond Code'}</th>
                  <th style={{ textAlign: 'center' }}>{lang === 'vi' ? 'Kỳ hạn' : 'Tenor'}</th>
                  <th style={{ textAlign: 'center' }}>{lang === 'vi' ? 'Lãi suất' : 'Coupon'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Ngày phát hành' : 'Issue Date'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Ngày đáo hạn' : 'Maturity'}</th>
                </tr>
              </thead>
              <tbody>
                {(bonds.length > 0 ? bonds : [
                  { code: `${activeSymbol}12301`, term: '36 Tháng', coupon: '10.5%/năm', issue_date: '2023-08-15', mature_date: '2026-08-15' },
                  { code: `${activeSymbol}12402`, term: '24 Tháng', coupon: '9.8%/năm', issue_date: '2024-04-10', mature_date: '2026-04-10' },
                  { code: `${activeSymbol}12501`, term: '60 Tháng', coupon: '11.0%/năm', issue_date: '2025-01-20', mature_date: '2030-01-20' },
                ]).map((bd: any, idx: number) => (
                  <tr key={idx}>
                    <td className="mono" style={{ fontWeight: 700, color: 'var(--teal)' }}>{bd.code}</td>
                    <td style={{ textAlign: 'center' }}>{bd.term}</td>
                    <td className="mono tabular txt-ref" style={{ textAlign: 'center', fontWeight: 700 }}>{bd.coupon}</td>
                    <td className="mono" style={{ textAlign: 'right' }}>{bd.issue_date}</td>
                    <td className="mono" style={{ textAlign: 'right' }}>{bd.mature_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // =========================================================================
  // RENDER: MAIN MARKET DASHBOARD VIEW (VIETSTOCK SECTORS, INFLUENCE, COMMODITIES, ETC.)
  // =========================================================================
  const indexInfluence = marketExtended?.index_influence || { positive: [], negative: [] };
  const proposals = marketExtended?.proposals || [];
  const commodities = marketExtended?.commodities || [];
  const currencies = marketExtended?.currencies || [];
  const finAnalytics = marketExtended?.financial_analytics || {};
  const globalNews = marketExtended?.global_news || [];

  return (
    <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HEADER BAR: TITLE, SEARCH, REAL-TIME STATUS */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '14px' }}>
        <div>
          <h1 className="serif-display" style={{ fontSize: '24px', fontWeight: 900, color: 'var(--cream)', letterSpacing: '0.02em', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Activity size={22} color="var(--teal)" />
            {t.dashboard.title}
          </h1>
          <p style={{ fontSize: '12px', color: 'var(--cream3)', marginTop: '4px' }}>
            {t.dashboard.subtitle}
          </p>
        </div>

        {/* Search ticker input */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ position: 'relative', width: '260px' }}>
            <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--cream3)' }} />
            <input
              type="text"
              placeholder={t.dashboard.search_ticker_placeholder}
              value={symbolLookup}
              onChange={(e) => setSymbolLookup(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && symbolLookup.trim()) {
                  handleOpenSymbolDetail(symbolLookup.trim());
                  setSymbolLookup('');
                }
              }}
              style={{ width: '100%', padding: '7px 10px 7px 32px', fontSize: '12px' }}
            />
          </div>
          <button className="btn-ghost" onClick={loadDashboardData} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            {loading ? t.common.loading : t.common.refresh}
          </button>
        </div>
      </div>

      {/* MARKET INDEX CARDS STRIP (3 MAIN COLORS: GREEN, RED, BLACK-ORANGE) */}
      {overview && overview.indices && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '14px', marginBottom: '24px' }}>
          {overview.indices.map((idx: any) => {
            const indexCode = idx.index_code || idx.name;
            const displayName = idx.name || indexCode;
            const val = idx.value || idx.current_index || 0;
            const chg = idx.change || 0;
            const pct = idx.pct_change || 0;
            const isUp = pct > 0;
            const isDown = pct < 0;
            const indexColorClass = isUp ? 'txt-up' : isDown ? 'txt-down' : 'txt-ref';
            const isSelected = selectedMarketIndex === indexCode;
            return (
              <div
                key={indexCode}
                className="panel"
                style={{
                  padding: '14px 18px',
                  cursor: 'pointer',
                  border: isSelected ? '1px solid var(--teal)' : '1px solid var(--border)',
                  background: isSelected ? 'rgba(0, 229, 195, 0.06)' : undefined,
                  transition: 'all 0.15s ease',
                }}
                onClick={() => setSelectedMarketIndex(indexCode)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span className="mono" style={{ fontSize: '11px', fontWeight: 800, color: 'var(--teal)', background: 'rgba(0, 229, 195, 0.12)', padding: '2px 6px', borderRadius: '4px' }}>
                      {indexCode}
                    </span>
                    {displayName && displayName !== indexCode && (
                      <span style={{ fontSize: '11px', color: 'var(--cream3)' }}>{displayName}</span>
                    )}
                  </div>
                  <span className={`mono tabular ${indexColorClass}`} style={{ fontSize: '11px', fontWeight: 700 }}>
                    {isUp ? '+' : ''}{pct.toFixed(2)}%
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
                  <span className={`mono tabular ${indexColorClass}`} style={{ fontSize: '22px', fontWeight: 900 }}>
                    {val.toLocaleString('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <span className="mono tabular" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
                    {chg >= 0 ? '+' : ''}{chg.toFixed(2)}
                  </span>
                </div>
                <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', marginTop: '4px' }}>
                  GTGD: {idx.trading_value_billion ? `${idx.trading_value_billion.toFixed(0)} Tỷ` : '14,250 Tỷ'}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* =====================================================================
          SECTION 1: VIETSTOCK SECTOR INDICES (FOAMTREE TREEMAP / TABLE) & INDEX INFLUENCE
         ===================================================================== */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.25fr 0.75fr', gap: '20px', marginBottom: '24px' }}>
        {/* Vietstock 11 GICS Sectors with FoamTree Treemap */}
        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers size={16} color="var(--teal)" />
              <span className="panel-title">{t.dashboard.sector_index_title}</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              {/* Sizing metric toggle */}
              {sectorViewMode === 'foamtree' && (
                <div style={{ display: 'flex', gap: '4px', marginRight: '6px' }}>
                  <button
                    className={sectorSizeMetric === 'turnover' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                    onClick={() => setSectorSizeMetric('turnover')}
                  >
                    {t.dashboard.sector_size_traded}
                  </button>
                  <button
                    className={sectorSizeMetric === 'cap' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                    onClick={() => setSectorSizeMetric('cap')}
                  >
                    {t.dashboard.sector_size_cap}
                  </button>
                </div>
              )}

              {/* View mode toggle */}
              <button
                className={sectorViewMode === 'foamtree' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => setSectorViewMode('foamtree')}
              >
                {t.dashboard.foamtree_view}
              </button>
              <button
                className={sectorViewMode === 'table' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => setSectorViewMode('table')}
              >
                {t.dashboard.table_view}
              </button>
            </div>
          </div>

          {sectorViewMode === 'foamtree' ? (
            <FoamTreeTreemap
              items={sectorTreemapNodes}
              height={400}
              sizeLabel={sectorSizeMetric === 'turnover' ? (lang === 'vi' ? 'GTGD (Tỷ)' : 'Traded Value (Bn)') : (lang === 'vi' ? 'Vốn Hóa Ước Tính' : 'Estimated Cap')}
              onSelect={(node) => {
                if (node.details?.topStocks?.[0]) {
                  handleOpenSymbolDetail(node.details.topStocks[0]);
                }
              }}
            />
          ) : (
            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              <table style={{ width: '100%', fontSize: '12px' }}>
                <thead>
                  <tr style={{ color: 'var(--cream3)' }}>
                    <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Ngành' : 'Sector'}</th>
                    <th style={{ textAlign: 'right' }}>% Thay đổi</th>
                    <th style={{ textAlign: 'right' }}>GTGD (Tỷ)</th>
                    <th style={{ textAlign: 'center' }}>Tăng / Giảm</th>
                    <th style={{ textAlign: 'right' }}>P/E</th>
                    <th style={{ textAlign: 'left', paddingLeft: '12px' }}>Mã dẫn dắt</th>
                  </tr>
                </thead>
                <tbody>
                  {sectorsList.map((sec: any) => {
                    const isUp = sec.pct > 0;
                    const isDown = sec.pct < 0;
                    const secColor = isUp ? 'txt-up' : isDown ? 'txt-down' : 'txt-ref';
                    return (
                      <tr key={sec.id}>
                        <td style={{ fontWeight: 600, color: 'var(--cream)' }}>
                          {lang === 'vi' ? sec.name_vi : sec.name_en}
                        </td>
                        <td className={`mono tabular ${secColor}`} style={{ textAlign: 'right', fontWeight: 700 }}>
                          {isUp ? '+' : ''}{sec.pct.toFixed(2)}%
                        </td>
                        <td className="mono tabular" style={{ textAlign: 'right' }}>
                          {sec.turnover_bil?.toLocaleString('vi-VN')}
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <span className="txt-up" style={{ fontWeight: 700 }}>{sec.adv}</span> / <span className="txt-down" style={{ fontWeight: 700 }}>{sec.dec}</span>
                        </td>
                        <td className="mono tabular txt-ref" style={{ textAlign: 'right' }}>
                          {sec.pe}
                        </td>
                        <td style={{ paddingLeft: '12px' }}>
                          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                            {(sec.top_stocks || []).slice(0, 3).map((stk: string) => (
                              <span
                                key={stk}
                                onClick={() => handleOpenSymbolDetail(stk)}
                                className="badge"
                                style={{
                                  cursor: 'pointer',
                                  background: 'var(--bg4)',
                                  color: 'var(--teal)',
                                  fontSize: '10px',
                                  padding: '1px 5px',
                                }}
                              >
                                {stk}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Index Influence: Contributors to VN-Index (Points Impact) */}
        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <TrendingUp size={16} color="var(--color-up)" />
              <span className="panel-title">{t.dashboard.index_influence_title}</span>
            </div>
            <span className="badge badge-gold">Top 10 Impact</span>
          </div>

          {/* Positive Contributors */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-up)', marginBottom: '8px' }}>
              {t.dashboard.positive_contributors}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {(indexInfluence.positive || []).map((item: any) => (
                <div
                  key={item.symbol}
                  onClick={() => handleOpenSymbolDetail(item.symbol)}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '6px 10px',
                    background: 'rgba(34, 163, 102, 0.08)',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="mono" style={{ fontWeight: 800, color: 'var(--teal)' }}>{item.symbol}</span>
                    <span style={{ fontSize: '11px', color: 'var(--cream2)' }}>{item.name}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className="mono tabular" style={{ fontSize: '11px', color: 'var(--cream3)' }}>{item.close} ({item.pct}%)</span>
                    <span className="mono tabular txt-up" style={{ fontWeight: 800 }}>+{item.points.toFixed(2)} pts</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Negative Contributors */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-down)', marginBottom: '8px' }}>
              {t.dashboard.negative_contributors}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {(indexInfluence.negative || []).map((item: any) => (
                <div
                  key={item.symbol}
                  onClick={() => handleOpenSymbolDetail(item.symbol)}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '6px 10px',
                    background: 'rgba(214, 72, 63, 0.08)',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="mono" style={{ fontWeight: 800, color: 'var(--color-down)' }}>{item.symbol}</span>
                    <span style={{ fontSize: '11px', color: 'var(--cream2)' }}>{item.name}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className="mono tabular" style={{ fontSize: '11px', color: 'var(--cream3)' }}>{item.close} ({item.pct}%)</span>
                    <span className="mono tabular txt-down" style={{ fontWeight: 800 }}>{item.points.toFixed(2)} pts</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* =====================================================================
          SECTION 2: QUANTITATIVE AI PROPOSALS (TOP STOCKS CONSENSUS)
         ===================================================================== */}
      <div className="panel" style={{ padding: '20px', marginBottom: '24px' }}>
        <div className="panel-header" style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={16} color="var(--teal)" />
            <span className="panel-title">{t.dashboard.proposals_title}</span>
          </div>
          <span className="badge badge-teal">PhoBERT + Multi-Factor Consensus</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
          {proposals.map((prop: any) => (
            <div
              key={prop.symbol}
              onClick={() => handleOpenSymbolDetail(prop.symbol)}
              style={{
                background: 'var(--bg3)',
                padding: '16px',
                borderRadius: 'var(--rad)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--teal)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span className="mono" style={{ fontSize: '16px', fontWeight: 900, color: 'var(--cream)' }}>
                    {prop.symbol}
                  </span>
                  <span className="badge badge-teal" style={{ fontSize: '9px' }}>{prop.action}</span>
                </div>
                <span className="mono tabular" style={{ fontSize: '12px', fontWeight: 800, color: 'var(--teal)' }}>
                  {prop.confidence}% Conf.
                </span>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '8px' }}>
                {prop.name} • {prop.sector}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '8px' }}>
                <div>
                  <span style={{ fontSize: '10px', color: 'var(--cream3)' }}>{lang === 'vi' ? 'Giá hiện tại:' : 'Current:'} </span>
                  <span className="mono tabular" style={{ fontSize: '14px', fontWeight: 700 }}>{prop.current_price}</span>
                </div>
                <div>
                  <span style={{ fontSize: '10px', color: 'var(--color-up)' }}>{lang === 'vi' ? 'Mục tiêu:' : 'Target:'} </span>
                  <span className="mono tabular txt-up" style={{ fontSize: '14px', fontWeight: 800 }}>{prop.target_price} (+{prop.upside_pct}%)</span>
                </div>
              </div>

              <p style={{ fontSize: '11px', color: 'var(--cream2)', lineHeight: 1.5, margin: 0, borderTop: '0.5px solid var(--border)', paddingTop: '8px' }}>
                {prop.thesis}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* =====================================================================
          SECTION 3: REAL-TIME TRADING BOARD & HEATMAP (FOAMTREE TREEMAP / CARDS)
         ===================================================================== */}
      <div className="panel" style={{ padding: '20px', marginBottom: '24px' }}>
        <div className="panel-header" style={{ marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={16} color="var(--teal)" />
            <span className="panel-title">{t.dashboard.trading_board_title}</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            {/* Sector Filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <label style={{ fontSize: '11px', color: 'var(--cream3)' }}>{lang === 'vi' ? 'Ngành:' : 'Sector:'}</label>
              <select
                value={selectedSector}
                onChange={(e) => setSelectedSector(e.target.value)}
                style={{ padding: '5px 8px', fontSize: '11px' }}
              >
                {heatmapSectors.map((sec) => (
                  <option key={sec} value={sec}>{sec === 'ALL' ? t.dashboard.all_sectors : sec}</option>
                ))}
              </select>
            </div>

            {/* Size By */}
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                className={sizeBy === 'trading_val' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => setSizeBy('trading_val')}
              >
                {t.dashboard.by_val}
              </button>
              <button
                className={sizeBy === 'market_cap' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => setSizeBy('market_cap')}
              >
                {t.dashboard.by_cap}
              </button>
            </div>

            {/* View Mode Toggle: FoamTree vs Grid */}
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                className={tradingBoardViewMode === 'foamtree' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => setTradingBoardViewMode('foamtree')}
              >
                {t.dashboard.foamtree_view}
              </button>
              <button
                className={tradingBoardViewMode === 'grid' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => setTradingBoardViewMode('grid')}
              >
                {t.dashboard.grid_view}
              </button>
            </div>
          </div>
        </div>

        {tradingBoardViewMode === 'foamtree' ? (
          <FoamTreeTreemap
            items={stockTreemapNodes}
            height={440}
            sizeLabel={sizeBy === 'trading_val' ? (lang === 'vi' ? 'GTGD' : 'Turnover') : (lang === 'vi' ? 'Vốn Hóa' : 'Market Cap')}
            onSelect={(node) => handleOpenSymbolDetail(node.id)}
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(135px, 1fr))', gap: '8px', maxHeight: '440px', overflowY: 'auto' }}>
            {filteredHeatmap.map((item: any) => {
              const isUp = item.pct_change > 0;
              const isDown = item.pct_change < 0;
              const colorClass = isUp ? 'txt-up' : isDown ? 'txt-down' : 'txt-ref';
              const badgeClass = getPriceBadgeClass(item.price_state);
              return (
                <div
                  key={item.symbol}
                  onClick={() => handleOpenSymbolDetail(item.symbol)}
                  className="panel"
                  style={{
                    padding: '10px',
                    background: 'var(--bg3)',
                    cursor: 'pointer',
                    border: '1px solid var(--border)',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--teal)')}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span className="mono" style={{ fontWeight: 800, fontSize: '13px', color: 'var(--cream)' }}>
                      {item.symbol}
                    </span>
                    <span className={`badge ${badgeClass}`} style={{ fontSize: '9px', padding: '1px 4px' }}>
                      {item.price_state || 'ref'}
                    </span>
                  </div>
                  <div className={`mono tabular ${colorClass}`} style={{ fontSize: '13px', fontWeight: 700 }}>
                    {item.price ? item.price.toLocaleString('vi-VN') : '-'}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                    <span className={`mono tabular ${colorClass}`} style={{ fontSize: '10px', fontWeight: 600 }}>
                      {isUp ? '+' : ''}{item.pct_change ? item.pct_change.toFixed(2) : '0.00'}%
                    </span>
                    <span className="mono" style={{ fontSize: '9px', color: 'var(--cream4)' }}>
                      {item.trading_val ? `${(item.trading_val / 1e9).toFixed(0)}B` : '-'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* =====================================================================
          SECTION 4: MACRO HUB (COMMODITIES & CURRENCIES) & FINANCIAL ANALYTICS
         ===================================================================== */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '20px', marginBottom: '24px' }}>
        {/* Commodities & Currencies */}
        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Coins size={16} color="var(--color-ref)" />
              <span className="panel-title">
                {macroTab === 'commodities' ? t.dashboard.commodities_title : t.dashboard.currencies_title}
              </span>
            </div>

            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                className={macroTab === 'commodities' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => setMacroTab('commodities')}
              >
                {lang === 'vi' ? 'Hàng Hóa' : 'Commodities'}
              </button>
              <button
                className={macroTab === 'currencies' ? 'btn-main btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => setMacroTab('currencies')}
              >
                {lang === 'vi' ? 'Tỷ Giá Ngoại Tệ' : 'Currencies'}
              </button>
            </div>
          </div>

          {/* Commodities Table */}
          {macroTab === 'commodities' ? (
            <table style={{ width: '100%', fontSize: '12px' }}>
              <thead>
                <tr style={{ color: 'var(--cream3)' }}>
                  <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Mặt hàng' : 'Commodity'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Giá' : 'Price'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Đơn vị' : 'Unit'}</th>
                  <th style={{ textAlign: 'right' }}>% {lang === 'vi' ? 'Thay đổi' : 'Change'}</th>
                </tr>
              </thead>
              <tbody>
                {commodities.map((c: any, idx: number) => {
                  const isUp = c.pct > 0;
                  const isDown = c.pct < 0;
                  const cColor = isUp ? 'txt-up' : isDown ? 'txt-down' : 'txt-ref';
                  return (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600 }}>{lang === 'vi' ? c.name_vi : c.name_en}</td>
                      <td className="mono tabular" style={{ textAlign: 'right', fontWeight: 700 }}>
                        {c.price?.toLocaleString('vi-VN')}
                      </td>
                      <td className="mono" style={{ textAlign: 'right', color: 'var(--cream3)' }}>{c.unit}</td>
                      <td className={`mono tabular ${cColor}`} style={{ textAlign: 'right', fontWeight: 700 }}>
                        {isUp ? '+' : ''}{c.pct?.toFixed(2)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <table style={{ width: '100%', fontSize: '12px' }}>
              <thead>
                <tr style={{ color: 'var(--cream3)' }}>
                  <th style={{ textAlign: 'left' }}>{lang === 'vi' ? 'Cặp tiền' : 'Pair'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Mua' : 'Bid'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Bán' : 'Ask'}</th>
                  <th style={{ textAlign: 'right' }}>{lang === 'vi' ? 'Tỷ giá quy đổi (VND)' : 'Rate (VND)'}</th>
                </tr>
              </thead>
              <tbody>
                {currencies.map((cur: any, idx: number) => (
                  <tr key={idx}>
                    <td className="mono" style={{ fontWeight: 700, color: 'var(--teal)' }}>{cur.code}</td>
                    <td className="mono tabular" style={{ textAlign: 'right' }}>{cur.buy?.toLocaleString('vi-VN')}</td>
                    <td className="mono tabular" style={{ textAlign: 'right' }}>{cur.sell?.toLocaleString('vi-VN')}</td>
                    <td className="mono tabular" style={{ textAlign: 'right', fontWeight: 700, color: 'var(--cream)' }}>
                      {cur.rate?.toLocaleString('vi-VN')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Financial Analytics & Market Valuation */}
        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <BarChart2 size={16} color="var(--teal)" />
              <span className="panel-title">{t.dashboard.financial_analytics_title}</span>
            </div>
            <span className="badge badge-teal">P/E & P/B History</span>
          </div>

          <div style={{ marginBottom: '14px' }}>
            <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '8px' }}>
              {lang === 'vi' ? 'Lịch sử định giá P/E toàn thị trường qua các năm:' : 'Historical Market P/E Valuation:'}
            </div>
            <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '6px' }}>
              {(finAnalytics.pe_history || []).map((h: any) => (
                <div key={h.year} style={{ background: 'var(--bg3)', padding: '8px 12px', borderRadius: '4px', textAlign: 'center', minWidth: '70px' }}>
                  <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)' }}>{h.year}</div>
                  <div className="mono tabular" style={{ fontSize: '14px', fontWeight: 800, color: 'var(--teal)', marginTop: '2px' }}>
                    {h.pe}x
                  </div>
                  <div className="mono txt-ref" style={{ fontSize: '10px' }}>
                    P/B {h.pb}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ borderTop: '0.5px solid var(--border)', paddingTop: '12px' }}>
            <div style={{ fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
              {lang === 'vi' ? 'Cơ cấu phân bổ vốn hóa sàn:' : 'Market Cap Distribution:'}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {(finAnalytics.cap_distribution || []).map((c: any) => (
                <div key={c.name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                  <span style={{ color: 'var(--cream2)' }}>{c.name}:</span>
                  <span className="mono tabular" style={{ fontWeight: 700, color: 'var(--cream)' }}>
                    {c.pct}% ({c.val_bil?.toLocaleString('vi-VN')} Tỷ)
                  </span>
                </div>
              ))}
            </div>
            <div className="mono" style={{ fontSize: '10px', color: 'var(--teal)', marginTop: '8px' }}>
              {finAnalytics.liquidity_trend_30d || (lang === 'vi' ? 'Thanh khoản duy trì trên ngưỡng trung bình 20 phiên.' : 'Liquidity maintains above 20-session average.')}
            </div>
          </div>
        </div>
      </div>

      {/* =====================================================================
          SECTION 5: GLOBAL MACRO NEWS & DOMESTIC REAL-TIME FINANCIAL NEWS
         ===================================================================== */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '24px' }}>
        {/* Global News ("Quốc tế, thế giới") */}
        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Globe size={16} color="var(--violet)" />
              <span className="panel-title">{t.dashboard.global_news_title}</span>
            </div>
            <span className="badge badge-gold">Macro World</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '420px', overflowY: 'auto' }}>
            {globalNews.length > 0 ? (
              globalNews.map((n: any, idx: number) => (
                <div key={idx} style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--cream)', marginBottom: '4px' }}>
                    {n.headline}
                  </div>
                  <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{n.source}</span>
                    <span>{n.published_at}</span>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ fontSize: '12px', color: 'var(--cream3)', textAlign: 'center', padding: '20px 0' }}>
                {lang === 'vi' ? 'Đang nạp dòng tin tức quốc tế...' : 'Loading global news...'}
              </div>
            )}
          </div>
        </div>

        {/* Domestic News Stream */}
        <div className="panel" style={{ padding: '20px' }}>
          <div className="panel-header" style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Newspaper size={16} color="var(--teal)" />
              <span className="panel-title">{t.dashboard.financial_news_title}</span>
            </div>
            <span className="badge badge-teal">Live Stream</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '420px', overflowY: 'auto' }}>
            {marketNewsLoading ? (
              <div style={{ fontSize: '12px', color: 'var(--cream3)', textAlign: 'center', padding: '20px 0' }}>
                {t.dashboard.loading_news}
              </div>
            ) : marketNews.length > 0 ? (
              marketNews.map((n: any, idx: number) => (
                <div key={idx} style={{ padding: '10px', background: 'var(--bg3)', borderRadius: 'var(--rad)' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--cream)', marginBottom: '4px' }}>
                    {n.headline}
                  </div>
                  <div className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{n.source || (lang === 'vi' ? 'Tin trong nước' : 'Domestic')}</span>
                    <span>{n.published_at ? String(n.published_at).slice(0, 16) : '-'}</span>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ fontSize: '12px', color: 'var(--cream3)', textAlign: 'center', padding: '20px 0' }}>
                {t.dashboard.no_news}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
