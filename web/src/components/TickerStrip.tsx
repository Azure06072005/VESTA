import React from 'react';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { useLang } from '../LangContext';

interface IndexItem {
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

export const TickerStrip: React.FC<TickerStripProps> = ({ indices = [], foreignNet = 0.0 }) => {
  const { lang } = useLang();

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
        <span className="mono" style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--teal)' }}>
          {lang === 'vi' ? 'THỊ TRƯỜNG TRỰC TIẾP:' : 'MARKETS LIVE:'}
        </span>
        {indices.length === 0 ? (
          <span className="mono" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
            {lang === 'vi' ? 'Đang đồng bộ dữ liệu ...' : 'Syncing data...'}
          </span>
        ) : (
          indices.map((idx, i) => {
            const isUp = idx.status === 'up' || idx.change > 0;
            const color = isUp ? 'var(--vn-up)' : 'var(--vn-down)';
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className="mono" style={{ fontSize: '11px', fontWeight: 800, color: 'var(--teal)' }}>
                  {idx.index_code || idx.name}
                </span>
                <span className="mono tabular" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cream2)' }}>
                  {idx.value != null ? idx.value.toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US', { minimumFractionDigits: 2 }) : '-'}
                </span>
                <span className="mono tabular" style={{ fontSize: '10px', fontWeight: 700, color, display: 'flex', alignItems: 'center' }}>
                  {isUp ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                  {isUp ? '+' : ''}{idx.change.toFixed(2)} ({isUp ? '+' : ''}{idx.pct_change.toFixed(2)}%)
                </span>
              </div>
            );
          })
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', borderLeft: '0.5px solid var(--border)', paddingLeft: '16px' }}>
          <span className="sans" style={{ fontSize: '11px', fontWeight: 600, color: 'var(--cream3)' }}>
            {lang === 'vi' ? 'Khối ngoại ròng:' : 'Foreign Net:'}
          </span>
          <span className="mono tabular" style={{ fontSize: '11px', fontWeight: 700, color: foreignNet >= 0 ? 'var(--vn-up)' : 'var(--vn-down)' }}>
            {foreignNet >= 0 ? '+' : ''}{foreignNet.toFixed(1)} {lang === 'vi' ? 'Tỷ VNĐ' : 'Billion VND'}
          </span>
        </div>
      </div>
    </div>
  );
};
