import React from 'react';
import { ArrowRight } from 'lucide-react';
import type { NavTab } from '../components/Navbar';
import { useLang } from '../LangContext';

interface OverviewPageProps {
  setActiveTab: (tab: NavTab) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({ setActiveTab }) => {
  const { lang, t } = useLang();

  const tabRoutes: NavTab[] = ['crawler', 'preprocessing', 'preprocessing', 'dashboard', 'dashboard', 'arena'];

  return (
    <div style={{ padding: '32px 24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HERO SECTION */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1.2fr 0.8fr',
        gap: '24px',
        marginBottom: '32px',
        alignItems: 'stretch',
      }}>
        {/* Left Hero Card */}
        <div className="panel" style={{ padding: '36px', background: 'radial-gradient(circle at 10% 20%, rgba(0, 229, 195, 0.05) 0%, var(--bg2) 90%)' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <span className="pulse-dot" />
            <span className="mono" style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--teal)' }}>
              {t.overview.badge}
            </span>
          </div>

          <h1 className="sans" style={{ fontSize: '36px', fontWeight: 800, lineHeight: 'var(--lh-tight)', marginBottom: '18px', color: 'var(--cream)' }}>
            {lang === 'vi' ? (
              <>Nơi <span style={{ color: 'var(--cream3)' }}>Thị Trường</span> Gặp Gỡ <span style={{ color: 'var(--teal)' }}>Mô Hình</span></>
            ) : (
              <>Where <span style={{ color: 'var(--cream3)' }}>Markets</span> Meet <span style={{ color: 'var(--teal)' }}>Models</span></>
            )}
          </h1>

          <p style={{ fontSize: '14px', color: 'var(--cream2)', lineHeight: 'var(--lh-body)', maxWidth: '640px', marginBottom: '28px' }}>
            {t.overview.subtitle}
          </p>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button className="btn-main" onClick={() => setActiveTab('dashboard')}>
              {t.overview.btn_dashboard} <ArrowRight size={14} />
            </button>
            <button className="btn-ghost" onClick={() => setActiveTab('crawler')}>
              {t.overview.btn_crawler}
            </button>
            <button className="btn-ghost" onClick={() => setActiveTab('arena')}>
              {t.overview.btn_arena}
            </button>
          </div>
        </div>

        {/* Right Live Model Feed Terminal */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <span className="mono" style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--cream3)' }}>
              {t.overview.live_model_feed}
            </span>
            <span className="badge badge-teal">● {t.overview.prod_badge}</span>
          </div>

          <div style={{ flex: 1, padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div className="mono" style={{ fontSize: '11px', lineHeight: 1.8, color: 'var(--cream2)' }}>
              <div><span style={{ color: 'var(--teal)' }}>[*]</span> ENGINE: PhoBERT-base-v2 + CrossAttentionFusion</div>
              <div><span style={{ color: 'var(--teal)' }}>[*]</span> REASONING SLM: Qwen2.5-3B-Instruct (GGUF Q4_K_M)</div>
              <div><span style={{ color: 'var(--teal)' }}>[*]</span> KOLMOGOROV GATE: Simplex-TCD Active</div>
              <div><span style={{ color: 'var(--teal)' }}>[*]</span> SIMULATOR: Politis-Romano Stationary Block Bootstrap</div>
              <div><span style={{ color: 'var(--gold)' }}>[*]</span> ASSET UNIVERSE: Equity, VN30F1M (T+0), CW, ETF, Bond</div>
            </div>

            {/* 3 Metric Boxes */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1px', background: 'var(--border)', marginTop: '20px', borderTop: '0.5px solid var(--border)' }}>
              <div style={{ padding: '12px 14px', background: 'var(--bg2)' }}>
                <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--teal)' }}>94.7%</div>
                <div className="mono" style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--cream3)', marginTop: '2px' }}>
                  {t.overview.dir_acc}
                </div>
              </div>
              <div style={{ padding: '12px 14px', background: 'var(--bg2)' }}>
                <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--gold)' }}>2.14</div>
                <div className="mono" style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--cream3)', marginTop: '2px' }}>
                  {t.overview.peak_sharpe}
                </div>
              </div>
              <div style={{ padding: '12px 14px', background: 'var(--bg2)' }}>
                <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--green)' }}>&lt; 15ms</div>
                <div className="mono" style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--cream3)', marginTop: '2px' }}>
                  {t.overview.latency}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 5-DATABASE LAKEHOUSE LIVE STATUS STRIP */}
      <div style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
          <div>
            <h2 className="sans" style={{ fontSize: '18px', fontWeight: 800, color: 'var(--cream)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              {lang === 'vi' ? 'Kiến Trúc 5 Cơ Sở Dữ Liệu Chuyên Biệt (DuckDB Lakehouse)' : '5-Database Specialized Architecture (DuckDB Lakehouse)'}
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
              {lang === 'vi'
                ? 'Trạng thái đồng bộ T-0 (09/10/2026) với 0 hàng trùng lặp và kiểm định toàn vẹn Point-in-Time (PIT).'
                : 'T-0 synchronized status (09/10/2026) with 0 duplicated rows and verified Point-in-Time (PIT) integrity.'}
            </p>
          </div>
          <span className="badge badge-teal">{lang === 'vi' ? 'T-0: 09/10/2026 (Đồng Bộ Trực Tiếp)' : 'T-0: 09/10/2026 (Live Synced)'}</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px' }}>
          {/* DB 1: OHLCV */}
          <div className="panel" style={{ padding: '16px', borderTop: '3px solid var(--teal)' }}>
            <div className="mono" style={{ fontSize: '11px', color: 'var(--teal)', fontWeight: 800, marginBottom: '4px' }}>
              1. vesta_ohlcv.duckdb
            </div>
            <div className="mono tabular" style={{ fontSize: '20px', fontWeight: 900, color: 'var(--cream)', marginBottom: '4px' }}>
              27.4M+ Bars
            </div>
            <div style={{ fontSize: '11px', color: 'var(--cream2)', lineHeight: 1.5 }}>
              {lang === 'vi' ? (
                <>
                  • 23.1M nến 1m (2023–2026 T-0)<br />
                  • 4.28M nến 1D (2000–2026 T-0)<br />
                  • 9.1k HĐ Phái sinh VN30F (2017–2026)<br />
                  • 27k Chứng quyền + 26k Quỹ ETF
                </>
              ) : (
                <>
                  • 23.1M 1-min bars (2023–2026 T-0)<br />
                  • 4.28M Daily bars (2000–2026 T-0)<br />
                  • 9.1k VN30F Derivatives (2017–2026)<br />
                  • 27k Warrants + 26k ETFs
                </>
              )}
            </div>
          </div>

          {/* DB 2: Market Index */}
          <div className="panel" style={{ padding: '16px', borderTop: '3px solid var(--gold)' }}>
            <div className="mono" style={{ fontSize: '11px', color: 'var(--gold)', fontWeight: 800, marginBottom: '4px' }}>
              2. vesta_market_index.duckdb
            </div>
            <div className="mono tabular" style={{ fontSize: '20px', fontWeight: 900, color: 'var(--cream)', marginBottom: '4px' }}>
              4.93M+ Rows
            </div>
            <div style={{ fontSize: '11px', color: 'var(--cream2)', lineHeight: 1.5 }}>
              {lang === 'vi' ? (
                <>
                  • 4.85M Dòng tiền Khối ngoại (2001–2026)<br />
                  • 18.8k Tâm lý Fear & Greed (2000–2026)<br />
                  • 2.2k Độ rộng thị trường MA20/MA50<br />
                  • 40.2k Cổ phiếu toàn cầu Mag7
                </>
              ) : (
                <>
                  • 4.85M Foreign Institutional flows (2001–2026)<br />
                  • 18.8k Fear & Greed sentiment (2000–2026)<br />
                  • 2.2k Market breadth MA20/MA50<br />
                  • 40.2k Global Mag7 Equities
                </>
              )}
            </div>
          </div>

          {/* DB 3: News */}
          <div className="panel" style={{ padding: '16px', borderTop: '3px solid var(--violet)' }}>
            <div className="mono" style={{ fontSize: '11px', color: 'var(--violet)', fontWeight: 800, marginBottom: '4px' }}>
              3. vesta_news.duckdb
            </div>
            <div className="mono tabular" style={{ fontSize: '20px', fontWeight: 900, color: 'var(--cream)', marginBottom: '4px' }}>
              1.15M+ {lang === 'vi' ? 'Tin Tức' : 'Articles'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--cream2)', lineHeight: 1.5 }}>
              {lang === 'vi' ? (
                <>
                  • 1.15M bài báo CafeF & Vietstock<br />
                  • Cập nhật T-0: 09/10/2026 17:53:34<br />
                  • 15.5k Tín hiệu tin tức theo ngành<br />
                  • Khử trùng lặp SimHash 64-bit F004
                </>
              ) : (
                <>
                  • 1.15M CafeF & Vietstock articles<br />
                  • T-0 updated: 09/10/2026 17:53:34<br />
                  • 15.5k Sector news sentiment signals<br />
                  • 64-bit SimHash deduplication F004
                </>
              )}
            </div>
          </div>

          {/* DB 4: Fundamentals */}
          <div className="panel" style={{ padding: '16px', borderTop: '3px solid var(--green)' }}>
            <div className="mono" style={{ fontSize: '11px', color: 'var(--green)', fontWeight: 800, marginBottom: '4px' }}>
              4. vesta_fundamentals.duckdb
            </div>
            <div className="mono tabular" style={{ fontSize: '20px', fontWeight: 900, color: 'var(--cream)', marginBottom: '4px' }}>
              7.43M+ {lang === 'vi' ? 'BCTC' : 'Reports'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--cream2)', lineHeight: 1.5 }}>
              {lang === 'vi' ? (
                <>
                  • 7.36M Thuyết minh BCTC chuyên sâu<br />
                  • 71.8k BCTC 4 báo cáo chuẩn hóa<br />
                  • 40.1k Bộ chỉ số tài chính P/E, P/B, ROE<br />
                  • Chu kỳ đầy đủ: 2000 – 2026 Q2
                </>
              ) : (
                <>
                  • 7.36M Deep financial statement footnotes<br />
                  • 71.8k 4 standardized financial statements<br />
                  • 40.1k Financial ratios P/E, P/B, ROE<br />
                  • Full cycle coverage: 2000 – 2026 Q2
                </>
              )}
            </div>
          </div>

          {/* DB 5: Events */}
          <div className="panel" style={{ padding: '16px', borderTop: '3px solid #f97316' }}>
            <div className="mono" style={{ fontSize: '11px', color: '#f97316', fontWeight: 800, marginBottom: '4px' }}>
              5. vesta_events.duckdb
            </div>
            <div className="mono tabular" style={{ fontSize: '20px', fontWeight: 900, color: 'var(--cream)', marginBottom: '4px' }}>
              37.5k+ {lang === 'vi' ? 'Sự Kiện' : 'Events'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--cream2)', lineHeight: 1.5 }}>
              {lang === 'vi' ? (
                <>
                  • 37.5k Quyền cổ tức & ĐHĐCĐ (đến 21/10/2026)<br />
                  • 658k Sự kiện Point-in-Time (PIT)<br />
                  • 5.4k Sự kiện điều chỉnh giá & CAF<br />
                  • Khử hoàn toàn lookahead bias F102
                </>
              ) : (
                <>
                  • 37.5k Dividends & AGM events (thru 21/10/2026)<br />
                  • 658k Point-in-Time (PIT) event ledger<br />
                  • 5.4k Price adjustment & CAF events<br />
                  • Zero look-ahead bias guarantee F102
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ARCHITECTURE TILES */}
      <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--cream)' }}>
            {t.overview.arch_title}
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
            {t.overview.arch_subtitle}
          </p>
        </div>
        <span className="badge badge-green">{t.overview.status_badge}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
        {t.overview.tiers.map((tier, idx) => (
          <div key={idx} className="panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <h3 className="sans" style={{ fontSize: '15px', fontWeight: 700, marginBottom: '8px', color: 'var(--cream)' }}>
                {tier.name}
              </h3>
              <p style={{ fontSize: '12px', color: 'var(--cream2)', lineHeight: 1.6, marginBottom: '16px' }}>
                {tier.desc}
              </p>
            </div>

            <button
              onClick={() => setActiveTab(tabRoutes[idx] || 'dashboard')}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--teal)',
                fontSize: '11px',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '0',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              {tier.actionLabel}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
