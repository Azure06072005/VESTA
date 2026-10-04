import React from 'react';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';

interface IndexItem {
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

export const TickerStrip: React.FC<TickerStripProps> = ({ indices, foreignNet = -185.0 }) => {
  const defaultIndices: IndexItem[] = [
    { name: 'VN-INDEX', value: 1288.45, change: 8.62, pct_change: 0.67, status: 'up' },
    { name: 'VN30-INDEX', value: 1352.18, change: 11.20, pct_change: 0.84, status: 'up' },
    { name: 'VN30F1M', value: 1354.50, change: 12.30, pct_change: 0.92, status: 'up' },
    { name: 'HNX-INDEX', value: 236.85, change: -0.45, pct_change: -0.19, status: 'down' },
    { name: 'UPCOM-INDEX', value: 92.15, change: 0.28, pct_change: 0.31, status: 'up' },
  ];

  const items = indices && indices.length > 0 ? indices : defaultIndices;

  return (
    <div style={{
      background: 'var(--bg2)',
      borderBottom: '0.5px solid var(--border)',
      height: '34px',
      display: 'flex',
      alignItems: 'center',
      padding: '0 24px',
      overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '28px', whiteSpace: 'nowrap' }}>
        <span className="mono" style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--cream3)' }}>
          MARKETS LIVE:
        </span>
        {items.map((idx, i) => {
          const isUp = idx.status === 'up' || idx.change > 0;
          const color = isUp ? 'var(--vn-up)' : 'var(--vn-down)';
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span className="sans" style={{ fontSize: '11px', fontWeight: 700, color: 'var(--cream)' }}>
                {idx.name}
              </span>
              <span className="mono tabular" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cream2)' }}>
                {idx.value.toLocaleString('vi-VN', { minimumFractionDigits: 2 })}
              </span>
              <span className="mono tabular" style={{ fontSize: '10px', fontWeight: 700, color, display: 'flex', alignItems: 'center' }}>
                {isUp ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                {isUp ? '+' : ''}{idx.change.toFixed(2)} ({isUp ? '+' : ''}{idx.pct_change.toFixed(2)}%)
              </span>
            </div>
          );
        })}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', borderLeft: '0.5px solid var(--border)', paddingLeft: '16px' }}>
          <span className="sans" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cream3)' }}>
            Khối ngoại ròng:
          </span>
          <span className="mono tabular" style={{ fontSize: '11px', fontWeight: 700, color: foreignNet >= 0 ? 'var(--vn-up)' : 'var(--vn-down)' }}>
            {foreignNet >= 0 ? '+' : ''}{foreignNet.toFixed(1)} Tỷ VNĐ
          </span>
        </div>
      </div>
    </div>
  );
};
