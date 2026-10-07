import React, { useEffect, useRef, useState } from 'react';
import { Database, Play, RefreshCw, Square, Terminal, Trash2, Zap } from 'lucide-react';
import type { CrawlParams } from '../api';
import { getLakehouseStatus, startCrawl, stopCrawl, subscribeCrawlLogs, triggerAtomicIngest } from '../api';
import { useLang } from '../LangContext';

export const CrawlerPage: React.FC = () => {
  const { lang, t } = useLang();
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
      setLogs((prev) => [...prev, `[INFO] ${lang === 'vi' ? 'Đã gửi lệnh kích hoạt thu thập' : 'Dispatched crawler command'} (Mode: ${mode.toUpperCase()})`]);
    } catch (err: any) {
      alert(`${t.common.error}: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStopCrawl = async () => {
    try {
      await stopCrawl();
      setIsCrawling(false);
      setLogs((prev) => [...prev, `[WARN] ${lang === 'vi' ? 'Đã phát tín hiệu dừng khẩn cấp cho tiến trình.' : 'Emergency halt signal sent to crawler.'}`]);
    } catch (err: any) {
      alert(`${t.common.error}: ${err.message}`);
    }
  };

  const handleAtomicIngest = async () => {
    const confirmMsg = lang === 'vi' 
      ? 'Bạn có chắc chắn muốn nạp toàn bộ dữ liệu từ buffer vào CSDL chính?' 
      : 'Are you sure you want to promote buffer tables to core lakehouse?';
    if (!confirm(confirmMsg)) return;
    try {
      setLogs((prev) => [...prev, `[*] ${lang === 'vi' ? 'Đang thực thi nạp nguyên tử (Atomic Ingestion)...' : 'Executing atomic core promotion...'}`]);
      const res = await triggerAtomicIngest();
      setLogs((prev) => [
        ...prev,
        `[OK] ${lang === 'vi' ? 'Nạp nguyên tử hoàn tất! Bảng:' : 'Atomic promotion complete! Tables:'} ${res.synced_tables?.join(', ') || 'N/A'}. Rows: ${res.total_rows || 0}`,
      ]);
      fetchStatus();
    } catch (err: any) {
      alert(`${t.common.error}: ${err.message}`);
    }
  };

  const clearLogs = () => setLogs([]);

  const categoryOptions = [
    { val: 'ohlcv', label: lang === 'vi' ? 'OHLCV Giá Hàng Ngày & Phút' : 'Daily & 1-Minute OHLCV' },
    { val: 'fundamentals', label: lang === 'vi' ? 'Báo Cáo Tài Chính & Chỉ Số' : 'Financial Statements & Ratios' },
    { val: 'news_comprehensive', label: lang === 'vi' ? 'Tin Tức Doanh Nghiệp CafeF' : 'CafeF Corporate News Stream' },
    { val: 'foreign_flow', label: lang === 'vi' ? 'Dòng Tiền Khối Ngoại' : 'Foreign Institutional Flow' },
    { val: 'events', label: lang === 'vi' ? 'Lịch Sự Kiện Quyền & ĐHĐCĐ' : 'Corporate Events & Dividends' },
    { val: 'macro', label: lang === 'vi' ? 'Kinh Tế Vĩ Mô & Lãi Suất' : 'Macroeconomics & Interest Rates' },
    { val: 'reference', label: lang === 'vi' ? 'Danh Mục Niêm Yết Master' : 'Master Reference Universe' },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--cream)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Database size={20} color="var(--teal)" />
            {t.crawler.title}
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
            {t.crawler.subtitle}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn-ghost" onClick={fetchStatus}>
            <RefreshCw size={13} />
            {t.crawler.check_status} ({lastCheck})
          </button>
          <button className="btn-main" onClick={handleAtomicIngest} style={{ background: 'var(--gold)', color: '#000' }}>
            <Zap size={14} />
            {t.crawler.atomic_ingest}
          </button>
        </div>
      </div>

      {/* TOP: CRAWLER CONFIGURATION FORM */}
      <div className="panel" style={{ padding: '20px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <span className="panel-title">{t.crawler.config_title}</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setMode('latest')}
              className={`btn-ghost btn-sm ${mode === 'latest' ? 'btn-main' : ''}`}
            >
              {t.crawler.mode_latest}
            </button>
            <button
              onClick={() => setMode('category')}
              className={`btn-ghost btn-sm ${mode === 'category' ? 'btn-main' : ''}`}
            >
              {t.crawler.mode_category}
            </button>
            <button
              onClick={() => setMode('all')}
              className={`btn-ghost btn-sm ${mode === 'all' ? 'btn-main' : ''}`}
            >
              {t.crawler.mode_all}
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', alignItems: 'end' }}>
          {/* Column 1: Category */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
              {t.crawler.category_label}
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              disabled={mode !== 'category'}
              style={{ width: '100%' }}
            >
              {categoryOptions.map((opt) => (
                <option key={opt.val} value={opt.val}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Column 2: Symbols scope */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
              {t.crawler.scope_label}
            </label>
            <select value={symbols} onChange={(e) => setSymbols(e.target.value)} style={{ width: '100%' }}>
              <option value="all">{t.crawler.scope_all}</option>
              <option value="vn30">{t.crawler.scope_vn30}</option>
              <option value="hose">{t.crawler.scope_hose}</option>
              <option value="hnx">{t.crawler.scope_hnx}</option>
            </select>
          </div>

          {/* Column 3: Buffer & Delay Options */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--cream3)', marginBottom: '6px' }}>
              {t.crawler.delay_label}
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
              />
              <input
                type="number"
                min="1"
                max="50"
                value={pages}
                onChange={(e) => setPages(parseInt(e.target.value) || 5)}
                placeholder="Pages"
                style={{ width: '50%' }}
              />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: 'var(--cream3)', marginTop: '4px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={bufferFirst}
                onChange={(e) => setBufferFirst(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              {t.crawler.buffer_label}
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
                {t.crawler.start_btn}
              </button>
            ) : (
              <button
                className="btn-danger"
                onClick={handleStopCrawl}
                style={{ flex: 1, height: '36px', justifyContent: 'center', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Square size={14} />
                {t.crawler.stop_btn}
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
            <span className="panel-title">{t.crawler.lakehouse_status_title}</span>
            <span className="mono" style={{ fontSize: '11px', color: 'var(--cream3)' }}>
              13 Subsystems
            </span>
          </div>

          <div style={{ maxHeight: '480px', overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t.crawler.th_category}</th>
                  <th>{t.crawler.th_records}</th>
                  <th>{t.crawler.th_symbols}</th>
                  <th>{t.crawler.th_date_range}</th>
                  <th>{t.crawler.th_status}</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((tbl) => {
                  const isGood = tbl.status?.includes('Tốt') || tbl.status?.includes('Đã nạp') || tbl.status?.includes('Good');
                  const isWarning = tbl.status?.includes('Trễ') || tbl.status?.includes('Lạc hậu') || tbl.status?.includes('Lag');
                  return (
                    <tr key={tbl.key}>
                      <td style={{ fontWeight: 600 }}>{tbl.name}</td>
                      <td className="mono tabular">{tbl.records ? tbl.records.toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US') : '0'}</td>
                      <td className="mono tabular">{tbl.symbols ? tbl.symbols.toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-US') : '-'}</td>
                      <td className="mono" style={{ fontSize: '11px', color: 'var(--cream2)' }}>
                        {tbl.min_date} ➔ {tbl.max_date}
                      </td>
                      <td>
                        <span
                          className={`badge ${isGood ? 'badge-green' : isWarning ? 'badge-gold' : 'badge-red'}`}
                          style={{ fontSize: '10px' }}
                        >
                          {tbl.status}
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
              <span className="panel-title">{t.crawler.terminal_title}</span>
              {isCrawling && <span className="pulse-dot" />}
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                className={`btn-ghost btn-sm ${autoScroll ? 'btn-main' : ''}`}
                onClick={() => setAutoScroll(!autoScroll)}
                style={{ fontSize: '10px', padding: '2px 8px' }}
              >
                {t.crawler.auto_scroll}: {autoScroll ? 'ON' : 'OFF'}
              </button>
              <button className="btn-ghost btn-sm" onClick={clearLogs} style={{ padding: '2px 8px' }}>
                <Trash2 size={11} />
              </button>
            </div>
          </div>

          <div ref={terminalRef} className="terminal-window">
            {logs.length === 0 ? (
              <div style={{ color: 'var(--cream3)', fontStyle: 'italic', padding: '20px 0' }}>
                {t.crawler.terminal_ready}
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
