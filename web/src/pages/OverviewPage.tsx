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
