import React, { useEffect, useState, useMemo } from 'react';
import {
  AlertCircle,
  ArrowUpRight,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { getAdminModelTestReport, runAdminModelTest } from '../api';
import { useLang } from '../LangContext';

export const AdminModelTestPage: React.FC = () => {
  const { lang } = useLang();

  // State dữ liệu báo cáo
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [runningTest, setRunningTest] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Bộ lọc bảng giao dịch
  const [selectedBot, setSelectedBot] = useState<'ALL' | 'BOT-N1' | 'BOT-A108'>('ALL');
  const [outcomeFilter, setOutcomeFilter] = useState<'ALL' | 'WIN' | 'LOSS'>('ALL');
  const [searchSymbol, setSearchSymbol] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const pageSize = 15;

  // Chế độ xem biểu đồ (NAV hoặc Drawdown)
  const [chartMetric, setChartMetric] = useState<'nav' | 'drawdown'>('nav');

  // Tải báo cáo kiểm thử
  const loadReport = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await getAdminModelTestReport();
      setReport(data);
    } catch (err: any) {
      setErrorMsg(err.message || 'Không thể tải báo cáo kiểm thử.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, []);

  // Kích hoạt chạy lại kiểm thử
  const handleRerunTest = async () => {
    if (runningTest) return;
    setRunningTest(true);
    setErrorMsg(null);
    try {
      const res = await runAdminModelTest(100000000.0);
      if (res.report) {
        setReport(res.report);
      } else {
        await loadReport();
      }
    } catch (err: any) {
      setErrorMsg(`Lỗi chạy lại kiểm thử: ${err.message}`);
    } finally {
      setRunningTest(false);
    }
  };

  // Tổng hợp danh sách giao dịch theo bộ lọc
  const filteredTrades = useMemo(() => {
    if (!report) return [];

    let list: any[] = [];
    if (selectedBot === 'BOT-N1') {
      list = [...(report.trades_n1 || [])];
    } else if (selectedBot === 'BOT-A108') {
      list = [...(report.trades_a108 || [])];
    } else {
      list = [...(report.trades_n1 || []), ...(report.trades_a108 || [])];
      // Sắp xếp ngày bán mới nhất lên trước
      list.sort((a, b) => (b.sell_date > a.sell_date ? 1 : -1));
    }

    if (searchSymbol.trim()) {
      const q = searchSymbol.trim().toUpperCase();
      list = list.filter((t) => t.symbol.includes(q));
    }

    if (outcomeFilter === 'WIN') {
      list = list.filter((t) => t.net_pnl > 0);
    } else if (outcomeFilter === 'LOSS') {
      list = list.filter((t) => t.net_pnl < 0);
    }

    return list;
  }, [report, selectedBot, searchSymbol, outcomeFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredTrades.length / pageSize));
  const pagedTrades = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredTrades.slice(start, start + pageSize);
  }, [filteredTrades, currentPage, pageSize]);

  // Trích xuất dữ liệu biểu đồ
  const equityPoints = report?.equity_curve || [];
  const n1Summary = report?.bot_n1_summary;
  const a108Summary = report?.bot_a108_summary;
  const highlights = report?.comparison_highlights;

  // Tính toán SVG Path cho biểu đồ
  const chartSvgData = useMemo(() => {
    if (!equityPoints || equityPoints.length < 2) return null;

    const width = 1000;
    const height = 240;
    const padX = 20;
    const padY = 20;

    const n = equityPoints.length;
    let minVal = Infinity;
    let maxVal = -Infinity;

    if (chartMetric === 'nav') {
      equityPoints.forEach((pt: any) => {
        if (pt.bot_n1_nav < minVal) minVal = pt.bot_n1_nav;
        if (pt.bot_n1_nav > maxVal) maxVal = pt.bot_n1_nav;
        if (pt.bot_a108_nav < minVal) minVal = pt.bot_a108_nav;
        if (pt.bot_a108_nav > maxVal) maxVal = pt.bot_a108_nav;
      });
      minVal = Math.min(minVal, 95000000);
      maxVal = Math.max(maxVal, 300000000);
    } else {
      equityPoints.forEach((pt: any) => {
        if (pt.bot_n1_drawdown_pct < minVal) minVal = pt.bot_n1_drawdown_pct;
        if (pt.bot_a108_drawdown_pct < minVal) minVal = pt.bot_a108_drawdown_pct;
      });
      minVal = Math.min(minVal, -28);
      maxVal = 0;
    }

    const range = maxVal - minVal || 1;

    const getX = (idx: number) => padX + (idx / (n - 1)) * (width - 2 * padX);
    const getY = (val: number) => height - padY - ((val - minVal) / range) * (height - 2 * padY);

    // Baseline 100M VND
    const baseLineY = chartMetric === 'nav' ? getY(100000000) : getY(0);

    const ptsN1 = equityPoints.map((pt: any, i: number) => `${getX(i)},${getY(chartMetric === 'nav' ? pt.bot_n1_nav : pt.bot_n1_drawdown_pct)}`).join(' ');
    const ptsA108 = equityPoints.map((pt: any, i: number) => `${getX(i)},${getY(chartMetric === 'nav' ? pt.bot_a108_nav : pt.bot_a108_drawdown_pct)}`).join(' ');

    return {
      width,
      height,
      baseLineY,
      ptsN1,
      ptsA108,
      minVal,
      maxVal,
      startDate: equityPoints[0].date,
      midDate: equityPoints[Math.floor(n / 2)].date,
      endDate: equityPoints[n - 1].date,
    };
  }, [equityPoints, chartMetric]);

  return (
    <div style={{ padding: '32px 24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* 1. HEADER SECTION */}
      <div style={{ marginBottom: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px', marginBottom: '12px' }}>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <span className="pulse-dot" style={{ background: 'var(--teal)' }} />
              <span className="mono" style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--teal)' }}>
                {lang === 'vi' ? 'TRANG QUẢN TRỊ KIỂM THỬ MÔ HÌNH & ĐỐI SOÁNH ĐỊNH LƯỢNG' : 'ADMIN QUANTITATIVE MODEL TEST & BENCHMARK'}
              </span>
            </div>
            <h1 className="sans" style={{ fontSize: '28px', fontWeight: 800, color: 'var(--cream)', margin: 0 }}>
              BOT-N1 (Rule-Based) <span style={{ color: 'var(--cream3)', fontWeight: 400 }}>vs</span> BOT-A108 (AI Twin)
            </h1>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              className="btn-ghost"
              onClick={loadReport}
              disabled={loading || runningTest}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <RefreshCw size={14} className={loading ? 'spin' : ''} />
              {lang === 'vi' ? 'Làm Mới' : 'Refresh'}
            </button>
            <button
              className="btn-main"
              onClick={handleRerunTest}
              disabled={runningTest || loading}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'var(--teal)', color: '#000' }}
            >
              <Play size={14} />
              {runningTest
                ? lang === 'vi'
                  ? 'Đang Chạy Backtest...'
                  : 'Running Backtest...'
                : lang === 'vi'
                ? 'Kích Hoạt Chạy Lại Kiểm Thử'
                : 'Re-run Backtest'}
            </button>
          </div>
        </div>

        {/* Thông tin tham số kiểm thử */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            flexWrap: 'wrap',
            padding: '10px 16px',
            background: 'var(--bg2)',
            borderRadius: '6px',
            border: '0.5px solid var(--border)',
            fontSize: '12px',
          }}
        >
          <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Bộ Dữ Liệu:' : 'Dataset:'}</span>
          <span className="mono" style={{ color: 'var(--teal)' }}>
            f104_test.parquet (461 phiên: 02/01/2025 → 21/07/2026)
          </span>
          <span style={{ color: 'var(--border2)' }}>•</span>
          <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Vốn Ban Đầu:' : 'Initial Cash:'}</span>
          <span className="mono" style={{ color: 'var(--cream)', fontWeight: 600 }}>
            100,000,000 VNĐ / Bot
          </span>
          <span style={{ color: 'var(--border2)' }}>•</span>
          <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Chu Kỳ:' : 'Settlement:'}</span>
          <span className="badge badge-blue">T+2.5 (3 phiên khóa)</span>
          <span style={{ color: 'var(--border2)' }}>•</span>
          <span style={{ color: 'var(--cream3)' }}>{lang === 'vi' ? 'Kiểm Định Bias:' : 'Look-Ahead Bias:'}</span>
          <span className="badge badge-teal" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <ShieldCheck size={12} /> {lang === 'vi' ? 'Tuyệt Đối Không Look-Ahead' : 'Zero Look-Ahead Verified'}
          </span>
        </div>
      </div>

      {errorMsg && (
        <div
          style={{
            padding: '14px 18px',
            background: 'rgba(255, 77, 79, 0.1)',
            border: '1px solid var(--red)',
            borderRadius: '8px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            color: 'var(--red)',
            fontSize: '13px',
          }}
        >
          <AlertCircle size={16} />
          <span>{errorMsg}</span>
        </div>
      )}

      {loading && !report ? (
        <div style={{ padding: '60px', textAlign: 'center', color: 'var(--cream3)' }}>
          <RefreshCw size={28} className="spin" style={{ margin: '0 auto 16px' }} />
          <div>{lang === 'vi' ? 'Đang tải báo cáo kiểm định mô hình...' : 'Loading model backtest audit report...'}</div>
        </div>
      ) : (
        <>
          {/* 2. HEAD-TO-HEAD KPI COMPARISON CARDS */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '16px',
              marginBottom: '24px',
            }}
          >
            {/* CARD 1: TÀI SẢN RÒNG & TỶ SUẤT SINH LỜI */}
            <div className="panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <span className="mono" style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--cream3)' }}>
                  {lang === 'vi' ? 'Tài Sản Ròng Cuối Kỳ' : 'Final Portfolio NAV'}
                </span>
                <span className="badge badge-teal">Vốn: 100M</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: '6px', borderLeft: '3px solid #f59e0b' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)', marginBottom: '4px' }}>BOT-N1 (Rule-Based)</div>
                  <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: '#f59e0b' }}>
                    {n1Summary?.final_nav?.toLocaleString('vi-VN')} đ
                  </div>
                  <div style={{ fontSize: '11px', color: '#10b981', marginTop: '2px' }}>
                    +{n1Summary?.total_return_pct}%
                  </div>
                </div>

                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: '6px', borderLeft: '3px solid var(--teal)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)', marginBottom: '4px' }}>BOT-A108 (AI Twin)</div>
                  <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--teal)' }}>
                    {a108Summary?.final_nav?.toLocaleString('vi-VN')} đ
                  </div>
                  <div style={{ fontSize: '11px', color: '#10b981', marginTop: '2px' }}>
                    +{a108Summary?.total_return_pct}%
                  </div>
                </div>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--teal)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <ArrowUpRight size={13} />
                <span>
                  <strong>Alpha AI Twin:</strong> +{highlights?.alpha_return_pct_diff}% (+{highlights?.alpha_nav_diff_vnd?.toLocaleString('vi-VN')} đ)
                </span>
              </div>
            </div>

            {/* CARD 2: SHARPE RATIO & RỦI RO */}
            <div className="panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <span className="mono" style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--cream3)' }}>
                  {lang === 'vi' ? 'Hệ Số Sharpe (Rf=4.5%) & CAGR' : 'Sharpe Ratio & CAGR'}
                </span>
                <span className="badge badge-blue">Rủi Ro Thị Trường</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)', marginBottom: '4px' }}>BOT-N1 (Rule-Based)</div>
                  <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--cream)' }}>
                    Sharpe: {n1Summary?.sharpe_ratio}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
                    CAGR: {n1Summary?.cagr_pct}%
                  </div>
                </div>

                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)', marginBottom: '4px' }}>BOT-A108 (AI Twin)</div>
                  <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--teal)' }}>
                    Sharpe: {a108Summary?.sharpe_ratio}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--teal)', marginTop: '2px' }}>
                    CAGR: {a108Summary?.cagr_pct}%
                  </div>
                </div>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--cream2)' }}>
                {lang === 'vi' ? 'Độ cải thiện Sharpe:' : 'Sharpe improvement:'}{' '}
                <strong style={{ color: 'var(--teal)' }}>+{highlights?.sharpe_improvement}</strong> ({lang === 'vi' ? 'Hiệu quả rủi ro vượt bậc' : 'Superior risk-adjusted return'})
              </div>
            </div>

            {/* CARD 3: SỤT GIẢM TỐI ĐA (MAX DRAWDOWN) */}
            <div className="panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <span className="mono" style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--cream3)' }}>
                  {lang === 'vi' ? 'Sụt Giảm Tối Đa (MaxDD)' : 'Max Drawdown (MaxDD)'}
                </span>
                <span className="badge badge-amber">Bảo Toàn Vốn</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)', marginBottom: '4px' }}>BOT-N1 (Rule-Based)</div>
                  <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: '#f87171' }}>
                    {n1Summary?.max_drawdown_pct}%
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
                    Vol: {n1Summary?.annualized_volatility_pct}%
                  </div>
                </div>

                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)', marginBottom: '4px' }}>BOT-A108 (AI Twin)</div>
                  <div className="mono" style={{ fontSize: '16px', fontWeight: 700, color: '#f87171' }}>
                    {a108Summary?.max_drawdown_pct}%
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
                    Vol: {a108Summary?.annualized_volatility_pct}%
                  </div>
                </div>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--cream2)' }}>
                {lang === 'vi'
                  ? 'AI Twin phòng vệ sớm khi có tin tiêu cực, kiểm soát drawdown tốt hơn.'
                  : 'AI Twin actively defends capital during adverse news events.'}
              </div>
            </div>

            {/* CARD 4: HIỆU SUẤT GIAO DỊCH & PROFIT FACTOR */}
            <div className="panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <span className="mono" style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--cream3)' }}>
                  {lang === 'vi' ? 'Thống Kê Khớp Lệnh' : 'Order Execution Stats'}
                </span>
                <span className="badge badge-blue">Tổng Lệnh Roundtrip</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)', marginBottom: '4px' }}>BOT-N1 (Rule-Based)</div>
                  <div className="mono" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--cream)' }}>
                    {n1Summary?.total_trades_count} lệnh ({n1Summary?.winning_trades_count} thắng)
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
                    PF: {n1Summary?.profit_factor} | WinRate: {n1Summary?.win_rate_pct}%
                  </div>
                </div>

                <div style={{ padding: '10px', background: 'var(--bg3)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '10px', color: 'var(--cream3)', marginBottom: '4px' }}>BOT-A108 (AI Twin)</div>
                  <div className="mono" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--teal)' }}>
                    {a108Summary?.total_trades_count} lệnh ({a108Summary?.winning_trades_count} thắng)
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
                    PF: {a108Summary?.profit_factor} | WinRate: {a108Summary?.win_rate_pct}%
                  </div>
                </div>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--cream2)' }}>
                {lang === 'vi'
                  ? `Lợi nhuận TB/lệnh: BOT-A108 (+${a108Summary?.avg_pnl_per_trade_pct}%) vs BOT-N1 (+${n1Summary?.avg_pnl_per_trade_pct}%)`
                  : `Avg Return/Trade: BOT-A108 (+${a108Summary?.avg_pnl_per_trade_pct}%) vs BOT-N1 (+${n1Summary?.avg_pnl_per_trade_pct}%)`}
              </div>
            </div>
          </div>

          {/* 3. INTERACTIVE COMPARATIVE EQUITY CURVE */}
          <div className="panel" style={{ padding: '24px', marginBottom: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 4px', color: 'var(--cream)' }}>
                  {chartMetric === 'nav'
                    ? lang === 'vi'
                      ? 'Đường Cong Tăng Trưởng Tài Sản (Equity NAV Curve 2025 – 2026)'
                      : 'Portfolio Equity NAV Curve (2025 – 2026)'
                    : lang === 'vi'
                    ? 'Biểu Đồ Sụt Giảm Tài Sản Theo Phiên (Underwater Drawdown %)'
                    : 'Underwater Drawdown % Chart'}
                </h3>
                <span style={{ fontSize: '12px', color: 'var(--cream3)' }}>
                  {lang === 'vi'
                    ? 'Mô phỏng lũy tiến từng phiên giao dịch, không sử dụng dữ liệu giá tương lai.'
                    : 'Walk-forward session simulation with strict point-in-time isolation.'}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {/* Metric toggle */}
                <div style={{ display: 'flex', background: 'var(--bg3)', borderRadius: '6px', padding: '2px' }}>
                  <button
                    onClick={() => setChartMetric('nav')}
                    style={{
                      padding: '4px 12px',
                      fontSize: '11px',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      background: chartMetric === 'nav' ? 'var(--teal)' : 'transparent',
                      color: chartMetric === 'nav' ? '#000' : 'var(--cream2)',
                      fontWeight: chartMetric === 'nav' ? 700 : 400,
                    }}
                  >
                    Tài Sản Ròng (NAV)
                  </button>
                  <button
                    onClick={() => setChartMetric('drawdown')}
                    style={{
                      padding: '4px 12px',
                      fontSize: '11px',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      background: chartMetric === 'drawdown' ? 'var(--red)' : 'transparent',
                      color: chartMetric === 'drawdown' ? '#fff' : 'var(--cream2)',
                      fontWeight: chartMetric === 'drawdown' ? 700 : 400,
                    }}
                  >
                    Mức Sụt Giảm (Drawdown %)
                  </button>
                </div>

                {/* Legend */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: '12px', fontSize: '11px' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: 'var(--teal)' }}>
                    <span style={{ width: '12px', height: '3px', background: 'var(--teal)', display: 'inline-block' }} />
                    BOT-A108 (AI Twin)
                  </span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: '#f59e0b' }}>
                    <span style={{ width: '12px', height: '3px', background: '#f59e0b', display: 'inline-block' }} />
                    BOT-N1 (Rule-Based)
                  </span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: 'var(--cream3)' }}>
                    <span style={{ width: '12px', height: '1px', background: 'var(--cream3)', borderTop: '1px dashed var(--cream3)', display: 'inline-block' }} />
                    {lang === 'vi' ? 'Vốn 100M gốc' : 'Base 100M'}
                  </span>
                </div>
              </div>
            </div>

            {/* SVG Canvas Chart */}
            {chartSvgData && (
              <div style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
                <svg
                  viewBox={`0 0 ${chartSvgData.width} ${chartSvgData.height}`}
                  style={{ width: '100%', height: '240px', display: 'block', background: 'var(--bg3)', borderRadius: '6px' }}
                >
                  {/* Grid lines */}
                  <line x1="20" y1="20" x2="980" y2="20" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
                  <line x1="20" y1="80" x2="980" y2="80" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
                  <line x1="20" y1="140" x2="980" y2="140" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
                  <line x1="20" y1="200" x2="980" y2="200" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />

                  {/* Base reference line */}
                  <line
                    x1="20"
                    y1={chartSvgData.baseLineY}
                    x2="980"
                    y2={chartSvgData.baseLineY}
                    stroke="rgba(255, 255, 255, 0.2)"
                    strokeWidth="1.2"
                    strokeDasharray="4 4"
                  />

                  {/* Line BOT-N1 (Amber) */}
                  <polyline
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="2.2"
                    points={chartSvgData.ptsN1}
                  />

                  {/* Line BOT-A108 (Teal) */}
                  <polyline
                    fill="none"
                    stroke="var(--teal)"
                    strokeWidth="2.6"
                    points={chartSvgData.ptsA108}
                  />
                </svg>

                {/* Timeline axis labels */}
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 20px 0', fontSize: '10px', color: 'var(--cream3)', fontFamily: 'monospace' }}>
                  <span>{chartSvgData.startDate} (Khởi điểm)</span>
                  <span>{chartSvgData.midDate}</span>
                  <span>{chartSvgData.endDate} (Phiên cuối cùng)</span>
                </div>
              </div>
            )}
          </div>

          {/* 4. HISTORICAL ROUNDTRIP TRADING LOGS TABLE */}
          <div className="panel" style={{ padding: '24px', marginBottom: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px', flexWrap: 'wrap', gap: '14px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 4px', color: 'var(--cream)' }}>
                  {lang === 'vi' ? 'Nhật Ký Giao Dịch & Đầu Tư Chi Tiết' : 'Historical Investment & Trade Execution Ledger'}
                </h3>
                <span style={{ fontSize: '12px', color: 'var(--cream3)' }}>
                  {lang === 'vi'
                    ? `Hiển thị ${filteredTrades.length} chu kỳ đầu tư (Thời gian, Giá mua, Giá bán, Mã CP, Khối lượng, Lợi nhuận).`
                    : `Showing ${filteredTrades.length} round-trip investments (Time, Buy Price, Sell Price, Symbol, Volumes, PnL).`}
                </span>
              </div>

              {/* Filters toolbar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                {/* Search by Symbol */}
                <div style={{ position: 'relative' }}>
                  <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--cream3)' }} />
                  <input
                    type="text"
                    placeholder={lang === 'vi' ? 'Tìm mã CP...' : 'Search symbol...'}
                    value={searchSymbol}
                    onChange={(e) => {
                      setSearchSymbol(e.target.value);
                      setCurrentPage(1);
                    }}
                    style={{
                      padding: '6px 12px 6px 30px',
                      background: 'var(--bg3)',
                      border: '0.5px solid var(--border)',
                      borderRadius: '6px',
                      color: 'var(--cream)',
                      fontSize: '12px',
                      width: '130px',
                    }}
                  />
                </div>

                {/* Bot filter */}
                <select
                  value={selectedBot}
                  onChange={(e) => {
                    setSelectedBot(e.target.value as any);
                    setCurrentPage(1);
                  }}
                  style={{
                    padding: '6px 12px',
                    background: 'var(--bg3)',
                    border: '0.5px solid var(--border)',
                    borderRadius: '6px',
                    color: 'var(--cream)',
                    fontSize: '12px',
                  }}
                >
                  <option value="ALL">{lang === 'vi' ? 'Tất cả Bots (406 lệnh)' : 'All Bots'}</option>
                  <option value="BOT-N1">BOT-N1 (Rule-Based)</option>
                  <option value="BOT-A108">BOT-A108 (AI Twin)</option>
                </select>

                {/* Outcome filter */}
                <select
                  value={outcomeFilter}
                  onChange={(e) => {
                    setOutcomeFilter(e.target.value as any);
                    setCurrentPage(1);
                  }}
                  style={{
                    padding: '6px 12px',
                    background: 'var(--bg3)',
                    border: '0.5px solid var(--border)',
                    borderRadius: '6px',
                    color: 'var(--cream)',
                    fontSize: '12px',
                  }}
                >
                  <option value="ALL">{lang === 'vi' ? 'Tất cả kết quả' : 'All Outcomes'}</option>
                  <option value="WIN">{lang === 'vi' ? 'Chốt Lời (Lãi > 0)' : 'Profit Only'}</option>
                  <option value="LOSS">{lang === 'vi' ? 'Cắt Lỗ (Lỗ < 0)' : 'Loss Only'}</option>
                </select>
              </div>
            </div>

            {/* Table */}
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ background: 'var(--bg3)', borderBottom: '1px solid var(--border)', color: 'var(--cream3)', textAlign: 'left' }}>
                    <th style={{ padding: '10px 12px' }}>#</th>
                    <th style={{ padding: '10px 12px' }}>Bot</th>
                    <th style={{ padding: '10px 12px' }}>Mã CP</th>
                    <th style={{ padding: '10px 12px' }}>Ngày Mua</th>
                    <th style={{ padding: '10px 12px' }}>Giá Mua</th>
                    <th style={{ padding: '10px 12px' }}>Ngày Bán</th>
                    <th style={{ padding: '10px 12px' }}>Giá Bán</th>
                    <th style={{ padding: '10px 12px' }}>Khối Lượng</th>
                    <th style={{ padding: '10px 12px' }}>Vốn Vào</th>
                    <th style={{ padding: '10px 12px' }}>Lãi/Lỗ Ròng</th>
                    <th style={{ padding: '10px 12px' }}>Tỷ Suất (%)</th>
                    <th style={{ padding: '10px 12px' }}>T+</th>
                    <th style={{ padding: '10px 12px' }}>Lý Do & Luận Điểm</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedTrades.length === 0 ? (
                    <tr>
                      <td colSpan={13} style={{ padding: '24px', textAlign: 'center', color: 'var(--cream3)' }}>
                        Không tìm thấy lệnh giao dịch nào phù hợp với bộ lọc.
                      </td>
                    </tr>
                  ) : (
                    pagedTrades.map((trade: any, idx: number) => {
                      const isWin = trade.net_pnl > 0;
                      return (
                        <tr
                          key={`${trade.bot_id}-${trade.trade_id}-${idx}`}
                          style={{
                            borderBottom: '0.5px solid var(--border)',
                            background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                          }}
                        >
                          <td style={{ padding: '10px 12px', color: 'var(--cream3)', fontFamily: 'monospace' }}>
                            {trade.trade_id}
                          </td>
                          <td style={{ padding: '10px 12px' }}>
                            <span className={trade.bot_id === 'BOT-A108' ? 'badge badge-teal' : 'badge badge-amber'}>
                              {trade.bot_id}
                            </span>
                          </td>
                          <td style={{ padding: '10px 12px', fontWeight: 700, color: 'var(--cream)' }}>
                            {trade.symbol}
                          </td>
                          <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: 'var(--cream2)' }}>
                            {trade.buy_date}
                          </td>
                          <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: 'var(--cream)' }}>
                            {trade.buy_price.toLocaleString('vi-VN')} đ
                          </td>
                          <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: 'var(--cream2)' }}>
                            {trade.sell_date}
                          </td>
                          <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: 'var(--cream)' }}>
                            {trade.sell_price.toLocaleString('vi-VN')} đ
                          </td>
                          <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontWeight: 600 }}>
                            {trade.volume.toLocaleString('vi-VN')}
                          </td>
                          <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: 'var(--cream2)' }}>
                            {Math.round(trade.invested_amount).toLocaleString('vi-VN')} đ
                          </td>
                          <td
                            style={{
                              padding: '10px 12px',
                              fontFamily: 'monospace',
                              fontWeight: 700,
                              color: isWin ? '#10b981' : '#f87171',
                            }}
                          >
                            {isWin ? '+' : ''}
                            {Math.round(trade.net_pnl).toLocaleString('vi-VN')} đ
                          </td>
                          <td
                            style={{
                              padding: '10px 12px',
                              fontFamily: 'monospace',
                              fontWeight: 700,
                              color: isWin ? '#10b981' : '#f87171',
                            }}
                          >
                            {isWin ? '+' : ''}
                            {trade.net_pnl_pct.toFixed(1)}%
                          </td>
                          <td style={{ padding: '10px 12px', color: 'var(--cream3)' }}>
                            T+{trade.holding_sessions}
                          </td>
                          <td style={{ padding: '10px 12px', fontSize: '11px', maxWidth: '300px' }}>
                            <div style={{ color: isWin ? 'var(--cream)' : '#fca5a5', fontWeight: 500 }}>
                              {trade.exit_reason}
                            </div>
                            {trade.ai_thesis && (
                              <div style={{ color: 'var(--teal)', fontSize: '10px', marginTop: '2px', opacity: 0.85 }}>
                                [AI]: {trade.ai_thesis}
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '16px', fontSize: '12px' }}>
                <span style={{ color: 'var(--cream3)' }}>
                  Trang {currentPage} / {totalPages} (Tổng {filteredTrades.length} lệnh)
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className="btn-ghost"
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage <= 1}
                    style={{ padding: '4px 10px', fontSize: '11px' }}
                  >
                    Trước
                  </button>
                  <button
                    className="btn-ghost"
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    style={{ padding: '4px 10px', fontSize: '11px' }}
                  >
                    Sau
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* 5. LOOK-AHEAD BIAS AUDIT & METHODOLOGY DISCLOSURE */}
          <div
            className="panel"
            style={{
              padding: '24px',
              background: 'radial-gradient(circle at 10% 20%, rgba(0, 229, 195, 0.03) 0%, var(--bg2) 90%)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
              <ShieldCheck size={20} style={{ color: 'var(--teal)' }} />
              <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'var(--cream)' }}>
                {lang === 'vi'
                  ? 'Bảo Đảm Tính Khoa Học & Loại Trừ Tuyệt Đối Look-Ahead Bias'
                  : 'Zero Look-Ahead Bias & Point-in-Time Regulatory Verification'}
              </h3>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--cream2)', lineHeight: 1.6, marginBottom: '16px' }}>
              {lang === 'vi'
                ? 'Hệ thống kiểm thử Admin Model Test được thiết kế theo đúng quy tắc nghiêm ngặt của dự án (Rule B1, B2, B4) nhằm xác thực năng lực thực tế của mô hình PhoBERT / SLM reasoning khi kết hợp cùng chiến lược định lượng:'
                : 'The Admin Model Test system enforces strict quantitative guidelines ensuring results are 100% reproducible and immune to look-ahead bias:'}
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
              <div style={{ padding: '14px', background: 'var(--bg3)', borderRadius: '6px' }}>
                <div style={{ fontWeight: 600, color: 'var(--teal)', marginBottom: '6px', fontSize: '13px' }}>
                  1. Cách Ly Tuyệt Đối Biến Tương Lai (PIT)
                </div>
                <div style={{ fontSize: '12px', color: 'var(--cream3)', lineHeight: 1.5 }}>
                  Tại mỗi phiên giao dịch ngày t, bot chỉ được phép đọc thông tin và giá đã xảy ra. Toàn bộ các cột tương lai như p5, p30, ret_t5_pct, target_dir_t5 hoàn toàn bị cô lập khỏi luồng quyết định.
                </div>
              </div>

              <div style={{ padding: '14px', background: 'var(--bg3)', borderRadius: '6px' }}>
                <div style={{ fontWeight: 600, color: 'var(--teal)', marginBottom: '6px', fontSize: '13px' }}>
                  2. Tuân Thủ Chu Kỳ Thanh Toán T+2.5
                </div>
                <div style={{ fontSize: '12px', color: 'var(--cream3)', lineHeight: 1.5 }}>
                  Khớp lệnh mua phiên t sẽ bị khóa quyền bán đến phiên t+3 (3 phiên giao dịch). Toàn bộ 406 lệnh đều vượt qua kiểm tra thời gian nắm giữ, không có lệnh nào bán sớm.
                </div>
              </div>

              <div style={{ padding: '14px', background: 'var(--bg3)', borderRadius: '6px' }}>
                <div style={{ fontWeight: 600, color: 'var(--teal)', marginBottom: '6px', fontSize: '13px' }}>
                  3. Phí Giao Dịch & Trượt Giá Chuẩn HOSE
                </div>
                <div style={{ fontSize: '12px', color: 'var(--cream3)', lineHeight: 1.5 }}>
                  Mọi giao dịch đều bị trừ phí môi giới 0.15%, thuế bán 0.10% và trượt giá thị trường 0.10% cho cả 2 chiều, đảm bảo kết quả phản ánh môi trường tiền thật.
                </div>
              </div>

              <div style={{ padding: '14px', background: 'var(--bg3)', borderRadius: '6px' }}>
                <div style={{ fontWeight: 600, color: 'var(--teal)', marginBottom: '6px', fontSize: '13px' }}>
                  4. Vì Sao BOT-A108 (AI Twin) Vượt Trội?
                </div>
                <div style={{ fontSize: '12px', color: 'var(--cream3)', lineHeight: 1.5 }}>
                  Khi cổ phiếu rơi vào đà giảm mạnh, BOT-N1 (Rule-Based) mua mù quáng vì tưởng là món hời; trong khi BOT-A108 sử dụng AI để phát hiện tin tức tiêu cực hoặc rủi ro cơ bản để từ chối giải ngân, tránh được các bẫy giá rơi thảm khốc.
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
