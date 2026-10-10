import React, { useEffect, useState } from 'react';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { useLang } from '../LangContext';
import { getDashboardOverview } from '../api';

export interface IndexItem {
  index_code?: string;
  name: string;
  value: number;
  change: number;
  pct_change: number;
  status: 'up' | 'down' | 'ref';
}

interface TickerStripProps {
  indices?: IndexItem[];
  foreignNet?: number;
}

export const TickerStrip: React.FC<TickerStripProps> = ({ indices: initialIndices = [], foreignNet: initialForeignNet }) => {
  const { lang } = useLang();
  const [indices, setIndices] = useState<IndexItem[]>(initialIndices);
  const [foreignNet, setForeignNet] = useState<number>(initialForeignNet ?? -406.3);
  const [totalVal, setTotalVal] = useState<number>(27542.8);

  useEffect(() => {
    let mounted = true;

    const fetchTickerData = async () => {
      try {
        const res = await getDashboardOverview();
        if (!mounted || !res) return;
        if (res.indices && res.indices.length > 0) {
          setIndices(res.indices);
        }
        if (res.market_summary) {
          if (res.market_summary.foreign_net_billion != null) {
            setForeignNet(res.market_summary.foreign_net_billion);
          }
          if (res.market_summary.total_value_billion != null) {
            setTotalVal(res.market_summary.total_value_billion);
          }
        }
      } catch (e) {
        // Keep fallback
      }
    };

    fetchTickerData();
    const interval = setInterval(fetchTickerData, 20000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Default fallback if loading
  const displayIndices: IndexItem[] = indices.length > 0 ? indices : [
    { index_code: 'VNINDEX', name: 'VN-INDEX', value: 1735.09, change: -3.88, pct_change: -0.22, status: 'down' },
    { index_code: 'VN30', name: 'VN30-INDEX', value: 1873.43, change: -3.57, pct_change: -0.19, status: 'down' },
    { index_code: 'HNX-INDEX', name: 'HNX-INDEX', value: 274.65, change: 1.15, pct_change: 0.42, status: 'up' },
    { index_code: 'HNX30', name: 'HNX30-INDEX', value: 588.20, change: 2.80, pct_change: 0.48, status: 'up' },
    { index_code: 'UPCOM-INDEX', name: 'UPCOM-INDEX', value: 112.40, change: 0.35, pct_change: 0.31, status: 'up' },
    { index_code: 'VN100', name: 'VN100-INDEX', value: 1698.15, change: -2.90, pct_change: -0.17, status: 'down' },
    { index_code: 'VNDIAMOND', name: 'VN-DIAMOND', value: 2415.80, change: 12.40, pct_change: 0.52, status: 'up' },
    { index_code: 'VNFINLEAD', name: 'VN-FINLEAD', value: 2310.50, change: -4.10, pct_change: -0.18, status: 'down' },
  ];

  // Extra summary ticker items
  const summaryItems = [
    {
      label: lang === 'vi' ? 'Khối ngoại ròng' : 'Foreign Net',
      valStr: `${foreignNet >= 0 ? '+' : ''}${foreignNet.toFixed(1)} ${lang === 'vi' ? 'Tỷ' : 'Bil'}`,
      isUp: foreignNet >= 0,
    },
    {
      label: lang === 'vi' ? 'Tổng thanh khoản' : 'Total Turnover',
      valStr: `${totalVal > 0 ? totalVal.toLocaleString() : '27,542'} ${lang === 'vi' ? 'Tỷ' : 'Bil'}`,
      isUp: true,
    },
  ];

  // Render index item
  const renderIndexBadge = (idx: IndexItem, keyId: string | number) => {
    const isUp = idx.status === 'up' || idx.change > 0;
    const isDown = idx.status === 'down' || idx.change < 0;
    const color = isUp ? 'var(--vn-up)' : isDown ? 'var(--vn-down)' : 'var(--vn-ref)';

    return (
      <div key={keyId} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span className="mono" style={{ fontSize: '11px', fontWeight: 800, color: 'var(--teal)', letterSpacing: '0.04em' }}>
          {idx.index_code || idx.name}
        </span>
        <span className="mono tabular" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cream)' }}>
          {idx.value != null ? idx.value.toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '-'}
        </span>
        <span className="mono tabular" style={{ fontSize: '10px', fontWeight: 700, color, display: 'flex', alignItems: 'center', gap: '2px' }}>
          {isUp ? <ArrowUpRight size={12} /> : isDown ? <ArrowDownRight size={12} /> : null}
          {isUp ? '+' : ''}{idx.change != null ? idx.change.toFixed(2) : '0.00'} ({isUp ? '+' : ''}{idx.pct_change != null ? idx.pct_change.toFixed(2) : '0.00'}%)
        </span>
      </div>
    );
  };

  return (
    <div style={{
      background: 'var(--bg2)',
      borderBottom: '0.5px solid var(--border)',
      height: '34px',
      display: 'flex',
      alignItems: 'center',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Fixed Left Live Badge */}
      <div style={{
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        zIndex: 10,
        background: 'linear-gradient(90deg, var(--bg2) 80%, rgba(13,13,28,0) 100%)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px 0 20px',
        gap: '8px',
        whiteSpace: 'nowrap',
      }}>
        <span className="pulse-dot" style={{ width: '6px', height: '6px', background: 'var(--teal)' }} />
        <span className="mono" style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--teal)', fontWeight: 800 }}>
          {lang === 'vi' ? 'THỊ TRƯỜNG TRỰC TIẾP' : 'MARKETS LIVE'}
        </span>
        <div style={{ width: '1px', height: '14px', background: 'var(--border2)', marginLeft: '6px' }} />
      </div>

      {/* Sliding Marquee Track (Right to Left continuous infinite loop) */}
      <div style={{ paddingLeft: '190px', width: '100%', overflow: 'hidden' }}>
        <div className="ticker-track">
          {/* First loop of items */}
          {displayIndices.map((idx, i) => renderIndexBadge(idx, `a-${i}`))}

          {/* Additional macro items */}
          {summaryItems.map((item, idx) => (
            <div key={`s-a-${idx}`} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '0 8px', borderLeft: '0.5px solid var(--border)' }}>
              <span className="sans" style={{ fontSize: '10px', color: 'var(--cream3)' }}>{item.label}:</span>
              <span className="mono tabular" style={{ fontSize: '10px', fontWeight: 700, color: item.isUp ? 'var(--vn-up)' : 'var(--vn-down)' }}>
                {item.valStr}
              </span>
            </div>
          ))}

          {/* Second duplicate loop to ensure seamless continuous transition */}
          {displayIndices.map((idx, i) => renderIndexBadge(idx, `b-${i}`))}

          {summaryItems.map((item, idx) => (
            <div key={`s-b-${idx}`} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '0 8px', borderLeft: '0.5px solid var(--border)' }}>
              <span className="sans" style={{ fontSize: '10px', color: 'var(--cream3)' }}>{item.label}:</span>
              <span className="mono tabular" style={{ fontSize: '10px', fontWeight: 700, color: item.isUp ? 'var(--vn-up)' : 'var(--vn-down)' }}>
                {item.valStr}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Right Gradient Fade */}
      <div style={{
        position: 'absolute',
        right: 0,
        top: 0,
        bottom: 0,
        width: '40px',
        background: 'linear-gradient(270deg, var(--bg2) 0%, rgba(13,13,28,0) 100%)',
        pointerEvents: 'none',
        zIndex: 5,
      }} />
    </div>
  );
};

export default TickerStrip;
