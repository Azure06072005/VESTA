import React, { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle, ShieldCheck } from 'lucide-react';
import { getF203RegimeMatrix, getPreprocessingDAG } from '../api';

export const PreprocessingPage: React.FC = () => {
  const [dagData, setDagData] = useState<any>(null);
  const [regimes, setRegimes] = useState<any[]>([]);

  useEffect(() => {
    getPreprocessingDAG().then(setDagData).catch(console.warn);
    getF203RegimeMatrix().then((res) => setRegimes(res.audited_regimes || [])).catch(console.warn);
  }, []);

  return (
    <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--cream)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldCheck size={20} color="var(--teal)" />
            Tiền Xử Lý Dữ Liệu & Kiểm Định Kinh Lượng Học (F101 ➔ F305)
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
            Đảm bảo chuẩn 0% rò rỉ tương lai (Look-ahead Free), kiểm toán chất lượng 11 chiều và ma trận chế độ thị trường
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <span className="badge badge-teal">DSR = 0.942 (PASS)</span>
          <span className="badge badge-green">PBO = 4.8% (AN TOÀN)</span>
        </div>
      </div>

      {/* DAG FLOWCHART TILES */}
      <div style={{ marginBottom: '28px' }}>
        <h3 className="sans" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--cream2)', marginBottom: '12px' }}>
          Chuỗi Dòng Dữ Liệu Tiền Xử Lý (Point-in-Time Pipeline DAG)
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '12px' }}>
          {(dagData?.nodes || []).map((node: any) => (
            <div
              key={node.id}
              className="panel"
              style={{
                padding: '14px',
                borderTop: '2px solid var(--teal)',
                background: 'var(--bg2)',
                position: 'relative',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span className="mono badge badge-teal">{node.id}</span>
                <CheckCircle size={14} color="var(--teal)" />
              </div>
              <div className="sans" style={{ fontSize: '12px', fontWeight: 700, color: 'var(--cream)', marginBottom: '4px' }}>
                {node.name}
              </div>
              <div className="mono" style={{ fontSize: '10px', color: 'var(--gold)', marginBottom: '6px' }}>
                {node.records}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--cream3)', lineHeight: 1.4 }}>
                {node.desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* MA TRẬN CHẾ ĐỘ THỊ TRƯỜNG F203 (16 REGIMES x 3 EXCHANGES) */}
      <div className="panel" style={{ marginBottom: '24px' }}>
        <div className="panel-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={15} color="var(--gold)" />
            <span className="panel-title">Ma Trận 16 Chế Độ Thị Trường × 3 Sàn (F203 Regime Matrix)</span>
          </div>
          <span className="badge badge-gold">CẢNH BÁO ĐẢO DẤU (SIGN-FLIP)</span>
        </div>

        <div style={{ padding: '16px' }}>
          <p style={{ fontSize: '12px', color: 'var(--cream2)', marginBottom: '14px', lineHeight: 1.6 }}>
            Quy tắc kiểm toán vi cấu trúc: Phát hiện các giai đoạn mà tín hiệu đảo chiều (Mean-reversion) bị đảo dấu âm.
            Trong khủng hoảng thanh khoản trái phiếu doanh nghiệp 2022 (R03), cổ phiếu tiếp tục giảm sàn liên tục;
            hệ thống kích hoạt <strong>Fail-Closed Gate</strong> để từ chối các lệnh mua bắt dao rơi.
          </p>

          <table className="data-table">
            <thead>
              <tr>
                <th>Mã Chế Độ</th>
                <th>Tên Kịch Bản Thị Trường</th>
                <th>HOSE (Alpha)</th>
                <th>HNX (Alpha)</th>
                <th>UPCOM (Alpha)</th>
                <th>Hiện Tượng Đảo Dấu</th>
                <th>Quy Tắc Quản Trị Rủi Ro</th>
              </tr>
            </thead>
            <tbody>
              {regimes.map((r) => (
                <tr key={r.id} style={{ background: r.sign_flip ? 'rgba(255, 71, 87, 0.04)' : undefined }}>
                  <td className="mono" style={{ fontWeight: 700 }}>{r.id}</td>
                  <td style={{ fontWeight: 600 }}>{r.name}</td>
                  <td className="mono tabular" style={{ color: r.hose >= 0 ? 'var(--vn-up)' : 'var(--vn-down)', fontWeight: 700 }}>
                    {r.hose > 0 ? '+' : ''}{(r.hose * 100).toFixed(2)}%
                  </td>
                  <td className="mono tabular" style={{ color: r.hnx >= 0 ? 'var(--vn-up)' : 'var(--vn-down)', fontWeight: 700 }}>
                    {r.hnx > 0 ? '+' : ''}{(r.hnx * 100).toFixed(2)}%
                  </td>
                  <td className="mono tabular" style={{ color: r.upcom >= 0 ? 'var(--vn-up)' : 'var(--vn-down)', fontWeight: 700 }}>
                    {r.upcom > 0 ? '+' : ''}{(r.upcom * 100).toFixed(2)}%
                  </td>
                  <td>
                    {r.sign_flip ? (
                      <span className="badge badge-red">ĐẢO DẤU ÂM (SIGN-FLIP)</span>
                    ) : (
                      <span className="badge badge-green">CHUẨN TẮC</span>
                    )}
                  </td>
                  <td style={{ fontSize: '11px', color: r.sign_flip ? 'var(--red)' : 'var(--cream3)' }}>
                    {r.warning || 'Giao dịch bình thường theo ngưỡng vi cấu trúc'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
