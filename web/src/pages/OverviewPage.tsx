import React from 'react';
import { ArrowRight } from 'lucide-react';
import type { NavTab } from '../components/Navbar';

interface OverviewPageProps {
  setActiveTab: (tab: NavTab) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({ setActiveTab }) => {
  const tiers = [
    {
      id: 'F0xx',
      name: 'Lakehouse Ingestion',
      count: '30 / 30',
      status: 'passing',
      desc: '13 phân hệ DuckDB: OHLCV, BCTC, Thuyết minh, CafeF News, Phái sinh VN30F, ETF, Trái phiếu HNX.',
      action: () => setActiveTab('crawler'),
      actionLabel: 'Mở Crawler Controller →',
    },
    {
      id: 'F1xx',
      name: 'Point-in-Time Preprocessing',
      count: '6 / 6',
      status: 'passing',
      desc: 'Quy trình PIT Join (F102) 0% look-ahead bias, kiểm toán chất lượng 11 chiều (F103), bóc tách cổ đông lớn.',
      action: () => setActiveTab('preprocessing'),
      actionLabel: 'Xem QA Pipeline →',
    },
    {
      id: 'F2xx',
      name: 'Econometric Proof & Gating',
      count: '4 / 4',
      status: 'passing',
      desc: 'Kiểm toán cụm Symbol/Month Bootstrap, DSR/PBO Bailey & Lopez de Prado, ma trận 16 Regimes (F203).',
      action: () => setActiveTab('preprocessing'),
      actionLabel: 'Xem Ma trận F203 →',
    },
    {
      id: 'F3xx',
      name: 'Deep Modeling & Consistency',
      count: '5 / 5',
      status: 'passing',
      desc: 'PhoBERT-base v2 FinDPO, Cross-Attention Multimodal Fusion, Kolmogorov Simplex-TCD (F304), Local SLM Qwen-2.5-3B CoT (F305).',
      action: () => setActiveTab('feedback'),
      actionLabel: 'Thử nghiệm Chấm điểm AI →',
    },
    {
      id: 'F4xx',
      name: 'Real-Time Serving & Drift',
      count: '3 / 3',
      status: 'passing',
      desc: 'FastAPI streaming inference sub-15ms, SimHash deduplication, Drift Monitor t+5/t+30, Continuous feedback loop.',
      action: () => setActiveTab('feedback'),
      actionLabel: 'Kiểm tra Drift Monitor →',
    },
    {
      id: 'F5xx',
      name: 'Multi-Bot Strategy Arena',
      count: '2 / 2',
      status: 'passing',
      desc: 'Đấu trường 308 bots chiến lược, vốn 10M VNĐ (odd-lot 1-99), 5 kịch bản thị trường Monte Carlo, AI Strategy Generator (F502).',
      action: () => setActiveTab('arena'),
      actionLabel: 'Vào Đấu trường 308 Bots →',
    },
  ];

  return (
    <div style={{ padding: '32px 24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HERO SECTION (Kế thừa từ Anhkiet.dev / kietfolio) */}
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
              DATA SCIENCE & QUANTITATIVE AI LABS
            </span>
          </div>

          <h1 className="sans" style={{ fontSize: '38px', fontWeight: 800, lineHeight: 1.15, marginBottom: '18px', color: 'var(--cream)' }}>
            Where <span style={{ color: 'var(--cream3)' }}>Markets</span> Meet <span style={{ color: 'var(--teal)' }}>Models</span>
          </h1>

          <p style={{ fontSize: '14px', color: 'var(--cream2)', lineHeight: 1.7, maxWidth: '640px', marginBottom: '28px' }}>
            Hệ sinh thái giao dịch định lượng tự trị thế hệ mới cho thị trường tài chính Việt Nam.
            Tích hợp mô hình ngôn ngữ suy luận chuyên sâu <strong>Qwen-2.5-3B CoT</strong>,
            mạng nơ-ron đa phương thức <strong>PhoBERT Cross-Attention</strong>,
            và đấu trường vi cấu trúc <strong>308 Bots</strong> kiểm soát rủi ro đa tài sản (Cổ phiếu, Phái sinh VN30F, ETF, Trái phiếu).
          </p>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button className="btn-main" onClick={() => setActiveTab('dashboard')}>
              Khám Phá Bảng Điện Thị Trường <ArrowRight size={14} />
            </button>
            <button className="btn-ghost" onClick={() => setActiveTab('crawler')}>
              Quản Trị Cào Dữ Liệu Lakehouse
            </button>
            <button className="btn-ghost" onClick={() => setActiveTab('arena')}>
              Đấu Trường Bot (10M VNĐ)
            </button>
          </div>
        </div>

        {/* Right Live Model Feed Terminal (Kế thừa từ kietfolio live terminal) */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <span className="mono" style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--cream3)' }}>
              Live Model Feed
            </span>
            <span className="badge badge-teal">● PROD INFERENCE</span>
          </div>

          <div style={{ flex: 1, padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div className="mono" style={{ fontSize: '11px', lineHeight: 1.8, color: 'var(--cream2)' }}>
              <div><span style={{ color: 'var(--teal)' }}>[*]</span> ENGINE: PhoBERT-base-v2 + CrossAttentionFusion</div>
              <div><span style={{ color: 'var(--teal)' }}>[*]</span> REASONING SLM: Qwen2.5-3B-Instruct (GGUF Q4_K_M)</div>
              <div><span style={{ color: 'var(--teal)' }}>[*]</span> KOLMOGOROV GATE: Simplex-TCD Active (10 Checkers)</div>
              <div><span style={{ color: 'var(--teal)' }}>[*]</span> SIMULATOR: Politis-Romano Stationary Block Bootstrap</div>
              <div><span style={{ color: 'var(--gold)' }}>[*]</span> ASSET UNIVERSE: Equity, VN30F1M (T+0), CW, ETF, Bond</div>
            </div>

            {/* 3 Metric Boxes */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1px', background: 'var(--border)', marginTop: '20px', borderTop: '0.5px solid var(--border)' }}>
              <div style={{ padding: '12px 14px', background: 'var(--bg2)' }}>
                <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--teal)' }}>94.7%</div>
                <div className="mono" style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--cream3)', marginTop: '2px' }}>
                  DIR ACCURACY
                </div>
              </div>
              <div style={{ padding: '12px 14px', background: 'var(--bg2)' }}>
                <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--gold)' }}>2.14</div>
                <div className="mono" style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--cream3)', marginTop: '2px' }}>
                  PEAK SHARPE
                </div>
              </div>
              <div style={{ padding: '12px 14px', background: 'var(--bg2)' }}>
                <div className="mono tabular" style={{ fontSize: '16px', fontWeight: 700, color: 'var(--green)' }}>&lt; 15ms</div>
                <div className="mono" style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--cream3)', marginTop: '2px' }}>
                  LATENCY
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 5-TIER PIPELINE ROADMAP */}
      <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--cream)' }}>
            VESTA Architecture Tiers (F000 ➔ F501)
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
            Chuỗi pipeline 5 tầng từ hồ dữ liệu lớn đến mô hình AI và đấu trường bot
          </p>
        </div>
        <span className="badge badge-green">48 / 50 FEATURES PASSING</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
        {tiers.map((tier) => (
          <div key={tier.id} className="panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                <span className="mono badge badge-teal">{tier.id}</span>
                <span className="mono tabular" style={{ fontSize: '11px', fontWeight: 700, color: 'var(--teal)' }}>
                  ✓ {tier.count}
                </span>
              </div>
              <h3 className="sans" style={{ fontSize: '15px', fontWeight: 700, marginBottom: '8px', color: 'var(--cream)' }}>
                {tier.name}
              </h3>
              <p style={{ fontSize: '12px', color: 'var(--cream2)', lineHeight: 1.6, marginBottom: '16px' }}>
                {tier.desc}
              </p>
            </div>

            <button
              onClick={tier.action}
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
