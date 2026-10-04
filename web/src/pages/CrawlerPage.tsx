import React, { useEffect, useRef, useState } from 'react';
import { Database, Play, RefreshCw, Square, Terminal, Trash2, Zap } from 'lucide-react';
import type { CrawlParams } from '../api';
import { getLakehouseStatus, startCrawl, stopCrawl, subscribeCrawlLogs, triggerAtomicIngest } from '../api';

export const CrawlerPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [tables, setTables] = useState<any[]>([]);
  const [lastCheck, setLastCheck] = useState<string>('-');
  const [isCrawling, setIsCrawling] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);

  // Form State
  const [mode, setMode] = useState<'latest' | 'category' | 'all'>('latest');
  const [category, setCategory] = useState<string>('ohlcv');
  const [symbols, setSymbols] = useState<string>('all');
  const [bufferFirst, setBufferFirst] = useState<boolean>(true);
  const [delay, setDelay] = useState<number>(0.3);
  const [pages, setPages] = useState<number>(5);

  const terminalRef = useRef<HTMLDivElement>(null);

  const fetchStatus = async () => {
    try {
      const res = await getLakehouseStatus();
      if (res && res.tables) {
        setTables(res.tables);
        setLastCheck(res.timestamp ? res.timestamp.slice(11, 19) : '-');
      }
    } catch (err) {
      console.warn('Could not fetch lakehouse status', err);
    }
  };

  useEffect(() => {
    fetchStatus();
    // Subscribe to SSE crawl logs
    const unsubscribe = subscribeCrawlLogs((line) => {
      setLogs((prev) => [...prev.slice(-300), line]);
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (autoScroll && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleStartCrawl = async () => {
    setLoading(true);
    try {
      const params: CrawlParams = {
        mode,
        category: mode === 'category' ? category : undefined,
        symbols,
        buffer_first: bufferFirst,
        delay,
        pages,
      };
      await startCrawl(params);
      setIsCrawling(true);
      setLogs((prev) => [...prev, `[INFO] Đã gửi lệnh kích hoạt cào (Mode: ${mode.toUpperCase()})`]);
    } catch (err: any) {
      alert(`Lỗi khi khởi chạy cào: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStopCrawl = async () => {
    try {
      await stopCrawl();
      setIsCrawling(false);
      setLogs((prev) => [...prev, `[WARN] Đã phát tín hiệu dừng khẩn cấp cho tiến trình cào.`]);
    } catch (err: any) {
      alert(`Lỗi khi dừng cào: ${err.message}`);
    }
  };

  const handleAtomicIngest = async () => {
    if (!confirm('Bạn có chắc chắn muốn nạp toàn bộ dữ liệu từ buffer vào CSDL chính?')) return;
    try {
      setLogs((prev) => [...prev, `[*] Đang thực thi nạp nguyên tử (Atomic Ingestion)...`]);
      const res = await triggerAtomicIngest();
      setLogs((prev) => [
        ...prev,
        `[OK] Nạp nguyên tử hoàn tất! Bảng đồng bộ: ${res.synced_tables?.join(', ') || 'N/A'}. Tổng dòng: ${res.total_rows || 0}`,
      ]);
      fetchStatus();
    } catch (err: any) {
      alert(`Lỗi khi nạp nguyên tử: ${err.message}`);
    }
  };

  const clearLogs = () => setLogs([]);

  return (
    <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--cream)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Database size={20} color="var(--teal)" />
            Bộ Điều Phối Cào Dữ Liệu Lakehouse (Crawler Pipeline Controller)
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
            Nền tảng kiểm soát cào dữ liệu tự động thay thế giao diện desktop cũ, hỗ trợ buffer phi khóa và nạp nguyên tử
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn-ghost" onClick={fetchStatus}>
            <RefreshCw size={13} />
            Kiểm tra Lakehouse ({lastCheck})
          </button>
          <button className="btn-main" onClick={handleAtomicIngest} style={{ background: 'var(--gold)', color: '#000' }}>
            <Zap size={14} />
            Nạp Nguyên Tử (Atomic Ingest)
          </button>
        </div>
      </div>

      {/* TOP: CRAWLER CONFIGURATION FORM */}
      <div className="panel" style={{ padding: '20px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <span className="panel-title">Cấu Hình Lệnh Cào Dữ Liệu</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            {['latest', 'category', 'all'].map((m) => (
              <button
                key={m}
                onClick={() => setMode(m as any)}
                className={`btn-ghost btn-sm ${mode === m ? 'btn-main' : ''}`}
                style={{ textTransform: 'uppercase' }}
              >
                {m === 'latest' ? '1. Cập Nhật Mới Nhất' : m === 'category' ? '2. Theo Phân Hệ' : '3. Cào Toàn Bộ Lịch Sử'}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', alignItems: 'end' }}>
          {/* Column 1: Category */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
              Phân hệ dữ liệu (Category):
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              disabled={mode !== 'category'}
              style={{ width: '100%' }}
            >
              <option value="ohlcv">OHLCV Giá Hàng Ngày (F002)</option>
              <option value="fundamentals">Báo Cáo Tài Chính BCTC (F005)</option>
              <option value="news_comprehensive">Tin Tức Doanh Nghiệp CafeF (F004)</option>
              <option value="foreign_flow">Dòng Tiền Khối Ngoại (F051)</option>
              <option value="events">Lịch Sự Kiện Quyền & ĐHĐCĐ (F006)</option>
              <option value="macro">Kinh Tế Vĩ Mô & Lãi Suất (F050)</option>
              <option value="reference">Danh Mục Niêm Yết Master Data (F001)</option>
            </select>
          </div>

          {/* Column 2: Symbols scope */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
              Phạm vi cổ phiếu (Symbols):
            </label>
            <select value={symbols} onChange={(e) => setSymbols(e.target.value)} style={{ width: '100%' }}>
              <option value="all">Toàn Bộ Thị Trường (~1,820 mã)</option>
              <option value="vn30">Rổ Chỉ Số VN30 (30 mã Bluechips)</option>
              <option value="hose">Sàn HOSE (~400 mã)</option>
              <option value="hnx">Sàn HNX (~320 mã)</option>
            </select>
          </div>

          {/* Column 3: Buffer & Delay Options */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
              Độ trễ cào & Số trang tin:
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={delay}
                onChange={(e) => setDelay(parseFloat(e.target.value) || 0.3)}
                placeholder="Delay (s)"
                style={{ width: '50%' }}
                title="Độ trễ giữa 2 request (giây)"
              />
              <input
                type="number"
                min="1"
                max="50"
                value={pages}
                onChange={(e) => setPages(parseInt(e.target.value) || 5)}
                placeholder="Số trang"
                style={{ width: '50%' }}
                title="Số trang tin tức"
              />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: 'var(--cream3)', marginTop: '4px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={bufferFirst}
                onChange={(e) => setBufferFirst(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              Buffer phi khóa (Zero-Lock)
            </label>
          </div>

          {/* Column 4: Start / Stop Actions */}
          <div style={{ display: 'flex', gap: '8px' }}>
            {!isCrawling ? (
              <button
                className="btn-main"
                onClick={handleStartCrawl}
                disabled={loading}
                style={{ flex: 1, height: '36px', justifyContent: 'center' }}
              >
                <Play size={14} />
                BẮT ĐẦU CÀO
              </button>
            ) : (
              <button
                className="btn-danger"
                onClick={handleStopCrawl}
                style={{ flex: 1, height: '36px', justifyContent: 'center', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Square size={14} />
                DỪNG TIẾN TRÌNH
              </button>
            )}
          </div>
        </div>
      </div>

      {/* MAIN TWO-COLUMN: TABLE STATUS + FINTECH CONSOLE TERMINAL */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '20px' }}>
        {/* Left Column: Lakehouse Table Status */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Tình Trạng 13 Phân Hệ Lakehouse DuckDB</span>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
              13 Phân Hệ
            </span>
          </div>

          <div style={{ maxHeight: '480px', overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Phân Hệ</th>
                  <th>Số Bản Ghi</th>
                  <th>Số Mã</th>
                  <th>Khoảng Ngày</th>
                  <th>Trạng Thái Độ Trễ</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((t) => {
                  const isGood = t.status?.includes('Tốt') || t.status?.includes('Đã nạp');
                  const isWarning = t.status?.includes('Trễ') || t.status?.includes('Lạc hậu');
                  return (
                    <tr key={t.key}>
                      <td style={{ fontWeight: 600 }}>{t.name}</td>
                      <td className="mono tabular">{t.records ? t.records.toLocaleString('vi-VN') : '0'}</td>
                      <td className="mono tabular">{t.symbols ? t.symbols.toLocaleString('vi-VN') : '-'}</td>
                      <td className="mono" style={{ fontSize: '11px', color: 'var(--cream2)' }}>
                        {t.min_date} ➔ {t.max_date}
                      </td>
                      <td>
                        <span
                          className={`badge ${isGood ? 'badge-green' : isWarning ? 'badge-gold' : 'badge-red'}`}
                          style={{ fontSize: '10px' }}
                        >
                          {t.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right Column: Fintech Live Console Terminal */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Terminal size={14} color="var(--teal)" />
              <span className="panel-title">Console Terminal (SSE Live Stream)</span>
              {isCrawling && <span className="pulse-dot" />}
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                className={`btn-ghost btn-sm ${autoScroll ? 'btn-main' : ''}`}
                onClick={() => setAutoScroll(!autoScroll)}
                style={{ fontSize: '10px', padding: '2px 8px' }}
              >
                Auto-scroll: {autoScroll ? 'ON' : 'OFF'}
              </button>
              <button className="btn-ghost btn-sm" onClick={clearLogs} style={{ padding: '2px 8px' }}>
                <Trash2 size={11} />
              </button>
            </div>
          </div>

          <div ref={terminalRef} className="terminal-window">
            {logs.length === 0 ? (
              <div style={{ color: 'var(--cream3)', fontStyle: 'italic', padding: '20px 0' }}>
                [Sẵn sàng] Không có tiến trình cào nào đang chạy. Nhấn 'BẮT ĐẦU CÀO' để khởi động...
              </div>
            ) : (
              logs.map((line, idx) => {
                let cls = 'info';
                if (line.includes('[OK]') || line.includes('[✓]')) cls = 'success';
                else if (line.includes('[!]') || line.includes('LỖI') || line.includes('Error')) cls = 'error';
                else if (line.includes('[WARN]') || line.includes('[*]')) cls = 'warning';
                return (
                  <div key={idx} className={`log-line ${cls}`}>
                    {line}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
