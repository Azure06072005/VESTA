import React, { useEffect, useState } from 'react';
import { Award, Bot, Flame, Send, AlertTriangle, DollarSign } from 'lucide-react';
import { chatAIStrategy, getArenaBots, getArenaReport } from '../api';
import { useLang } from '../LangContext';

export const BotArenaPage: React.FC = () => {
  const { lang, t } = useLang();
  const [report, setReport] = useState<any>(null);
  const [allBots, setAllBots] = useState<any[]>([]);
  const [customRankedBots, setCustomRankedBots] = useState<any[] | null>(null);
  const [customFocusTitle, setCustomFocusTitle] = useState<string | null>(null);
  const [targetAssets, setTargetAssets] = useState<string[]>([]);
  const [filterType, setFilterType] = useState<'all' | 'ai' | 'non_ai'>('all');
  const [activeCapital, setActiveCapital] = useState<number>(10000000.0);
  const [customCapitalInput, setCustomCapitalInput] = useState<string>('10,000,000');
  const [chatInput, setChatInput] = useState<string>(
    lang === 'vi'
      ? 'Tôi muốn đầu tư NVL và PNJ vốn 50 triệu VNĐ, hãy xếp hạng các chiến lược tốt nhất.'
      : 'I want to invest in NVL and PNJ with 50M VND capital, please rank the best strategies.'
  );
  const [chatting, setChatting] = useState<boolean>(false);
  const [chatMessages, setChatMessages] = useState<Array<{ sender: 'user' | 'ai'; text: string; config?: any; modelUsed?: string }>>([
    {
      sender: 'ai',
      text: t.arena.welcome_msg,
    },
  ]);

  const CAPITAL_PRESETS = [
    { label: '10 Triệu (10M)', value: 10000000 },
    { label: '20 Triệu (20M)', value: 20000000 },
    { label: '50 Triệu (50M)', value: 50000000 },
    { label: '100 Triệu (100M)', value: 100000000 },
  ];

  const PROMPT_SUGGESTIONS = [
    { label: '👋 Hello', text: 'Hello' },
    { label: '🏢 NVL & PNJ 50M', text: 'Tôi muốn đầu tư NVL và PNJ vốn 50 triệu VNĐ' },
    { label: '🛡️ Phòng thủ thị trường', text: 'Thị trường có rủi ro đảo chiều, tôi cần chiến lược phòng thủ bảo toàn vốn' },
    { label: '🚀 FPT tăng trưởng', text: 'Tôi muốn giải ngân FPT đón sóng tăng trưởng bứt phá' },
    { label: '❓ Mã không tồn tại', text: 'Tôi muốn mua mã XYZ' },
  ];

  useEffect(() => {
    getArenaReport().then(setReport).catch(console.warn);
    getArenaBots().then((res) => setAllBots(res.bots || [])).catch(console.warn);
  }, []);

  const handleSendChat = async (overrideMsg?: string) => {
    const textToSend = overrideMsg || chatInput;
    if (!textToSend.trim()) return;

    setChatInput('');
    setChatMessages((prev) => [...prev, { sender: 'user', text: textToSend }]);
    setChatting(true);

    try {
      const res = await chatAIStrategy(textToSend, activeCapital, 'medium');

      // Đồng bộ lại số vốn nếu AI bóc tách được vốn từ prompt người dùng
      if (res.bot_config?.initial_cash && res.bot_config.initial_cash !== activeCapital) {
        setActiveCapital(res.bot_config.initial_cash);
        setCustomCapitalInput(res.bot_config.initial_cash.toLocaleString('vi-VN'));
      }

      if (res.custom_ranked_bots && res.custom_ranked_bots.length > 0) {
        setCustomRankedBots(res.custom_ranked_bots);
        setCustomFocusTitle(res.focus_title || `${t.arena.dynamic_ranking_active} ${res.target_assets?.join(', ')}`);
        setTargetAssets(res.target_assets || []);
      }

      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: res.reply || 'Đã tạo cấu hình bot tối ưu theo yêu cầu.',
          config: res.bot_config,
          modelUsed: res.model_used,
        },
      ]);
    } catch (err: any) {
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: `Lỗi kết nối mô hình: ${err.message}`,
        },
      ]);
    } finally {
      setChatting(false);
    }
  };

  const baseTopBots = report?.top_10_champion_bots || [];
  const activeBots = customRankedBots || baseTopBots;
  const filteredTopBots = filterType === 'all'
    ? activeBots
    : filterType === 'ai'
    ? activeBots.filter((b: any) => b.is_ai)
    : activeBots.filter((b: any) => !b.is_ai);

  return (
    <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--cream)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Flame size={20} color="var(--gold)" />
            {t.arena.title}
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
            {t.arena.subtitle}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <span className="badge badge-gold">{t.arena.capital_badge}</span>
          <span className="badge badge-teal">{t.arena.oddlot_badge}</span>
        </div>
      </div>

      {/* METRIC STRIP */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '24px' }}>
        <div className="panel" style={{ padding: '16px' }}>
          <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>{t.arena.total_bots_card}</div>
          <div className="mono tabular" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--cream)', marginTop: '4px' }}>
            {allBots.length > 0 ? allBots.length : (report?.tournament_metadata?.total_bots || 308)} BOTS
          </div>
          <div style={{ fontSize: '11px', color: 'var(--teal)', marginTop: '2px' }}>
            {t.arena.ai_twins_desc}
          </div>
        </div>

        <div className="panel" style={{ padding: '16px' }}>
          <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>{t.arena.initial_cash_card}</div>
          <div className="mono tabular" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--gold)', marginTop: '4px' }}>
            {activeCapital.toLocaleString('vi-VN')} đ
          </div>
          <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
            {t.arena.nav_cap_desc}
          </div>
        </div>

        <div className="panel" style={{ padding: '16px' }}>
          <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>{t.arena.asset_class_card}</div>
          <div className="sans" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--cream)', marginTop: '4px' }}>
            {lang === 'vi' ? 'Đa Tài Sản (Multi-Asset)' : 'Multi-Asset Universe'}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
            {t.arena.multi_asset_desc}
          </div>
        </div>

        <div className="panel" style={{ padding: '16px' }}>
          <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>{t.arena.pbo_card}</div>
          <div className="mono tabular" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--green)', marginTop: '4px' }}>
            {((report?.tournament_metadata?.probability_of_backtest_overfitting_pbo || 0.048) * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: '11px', color: 'var(--green)', marginTop: '2px' }}>
            {t.arena.pbo_desc}
          </div>
        </div>
      </div>

      {/* TWO COLUMNS: LEADERBOARD + AI STRATEGY CHATBOX */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.12fr 0.88fr', gap: '24px' }}>
        {/* Left Column: Champion Bots Leaderboard */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title"><Award size={15} color="var(--gold)" /> {t.arena.leaderboard_title}</span>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                className={`btn-ghost btn-sm ${filterType === 'all' ? 'btn-main' : ''}`}
                onClick={() => setFilterType('all')}
              >
                {t.arena.filter_all}
              </button>
              <button
                className={`btn-ghost btn-sm ${filterType === 'ai' ? 'btn-main' : ''}`}
                onClick={() => setFilterType('ai')}
              >
                {t.arena.filter_ai}
              </button>
              <button
                className={`btn-ghost btn-sm ${filterType === 'non_ai' ? 'btn-main' : ''}`}
                onClick={() => setFilterType('non_ai')}
              >
                {t.arena.filter_non_ai}
              </button>
            </div>
          </div>

          {/* DYNAMIC ASSET-SPECIFIC RANKING BANNER */}
          {customRankedBots && (
            <div style={{
              margin: '12px 12px 0 12px',
              padding: '12px 16px',
              background: 'linear-gradient(135deg, rgba(0, 229, 195, 0.12), rgba(245, 166, 35, 0.08))',
              border: '1px solid rgba(0, 229, 195, 0.4)',
              borderRadius: 'var(--rad)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
            }}>
              <div>
                <div style={{ fontSize: '12px', fontWeight: 800, color: 'var(--teal)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Flame size={14} color="var(--gold)" />
                  {customFocusTitle || `${t.arena.dynamic_ranking_active} ${targetAssets.join(', ')}`}
                </div>
                <div style={{ fontSize: '10px', color: 'var(--cream3)', marginTop: '2px' }}>
                  {t.arena.ranking_source_note}
                </div>
              </div>
              <button
                className="btn-ghost btn-sm"
                style={{ fontSize: '11px', color: 'var(--gold)', borderColor: 'var(--gold)', whiteSpace: 'nowrap' }}
                onClick={() => {
                  setCustomRankedBots(null);
                  setCustomFocusTitle(null);
                  setTargetAssets([]);
                }}
              >
                ↺ {t.arena.reset_overall_ranking}
              </button>
            </div>
          )}

          <div style={{ padding: '12px', maxHeight: '560px', overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t.arena.th_rank}</th>
                  <th>{t.arena.th_bot_id}</th>
                  <th>{t.arena.th_strategy}</th>
                  <th>{t.arena.th_model}</th>
                  <th>{t.arena.th_sharpe}</th>
                  <th>{t.arena.th_return}</th>
                  <th>{t.arena.th_maxdd}</th>
                  <th>{t.arena.th_winrate}</th>
                </tr>
              </thead>
              <tbody>
                {filteredTopBots.map((bot: any) => (
                  <tr key={bot.bot_id} style={{ background: bot.rank === 1 ? 'rgba(0, 229, 195, 0.05)' : undefined }}>
                    <td className="mono" style={{ fontWeight: 800, color: bot.rank <= 3 ? 'var(--gold)' : 'var(--cream)' }}>
                      #{bot.rank}
                    </td>
                    <td className="mono" style={{ fontWeight: 700, color: 'var(--teal)' }}>
                      {bot.bot_id}
                    </td>
                    <td>
                      <div style={{ fontSize: '11px', color: 'var(--cream2)', fontWeight: 600 }}>
                        {bot.strategy_id}
                      </div>
                      {bot.tailored_action && (
                        <div style={{ fontSize: '10px', color: 'var(--teal)', marginTop: '2px', fontWeight: 600 }}>
                          ⚡ {bot.tailored_action}
                        </div>
                      )}
                    </td>
                    <td>
                      {bot.is_ai ? (
                        <span className="badge badge-teal">AI TWIN</span>
                      ) : (
                        <span className="badge" style={{ background: 'var(--bg3)', color: 'var(--cream3)' }}>RULE-BASED</span>
                      )}
                    </td>
                    <td className="mono tabular" style={{ fontWeight: 700, color: 'var(--gold)' }}>
                      {bot.mean_sharpe.toFixed(2)}
                    </td>
                    <td className="mono tabular" style={{ fontWeight: 700, color: 'var(--vn-up)' }}>
                      +{bot.mean_return_pct.toFixed(1)}%
                    </td>
                    <td className="mono tabular" style={{ color: 'var(--vn-down)' }}>
                      -{bot.mean_max_drawdown_pct.toFixed(1)}%
                    </td>
                    <td className="mono tabular" style={{ color: 'var(--green)' }}>
                      {bot.win_rate_pct.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right Column: Local AI Strategy Studio Chatbox */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Bot size={15} color="var(--violet)" />
              <span className="panel-title">{t.arena.studio_title}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span className="badge badge-gold" style={{ fontSize: '10px' }}>
                <DollarSign size={10} style={{ display: 'inline', marginRight: '2px' }} />
                {activeCapital.toLocaleString('vi-VN')} đ
              </span>
              <span className="badge badge-violet">{t.arena.slm_badge}</span>
            </div>
          </div>

          {/* Quick Prompts Bar */}
          <div style={{
            padding: '8px 12px',
            background: 'var(--bg4)',
            borderBottom: '0.5px solid var(--border)',
            display: 'flex',
            gap: '6px',
            overflowX: 'auto',
            whiteSpace: 'nowrap',
          }}>
            {PROMPT_SUGGESTIONS.map((item, idx) => (
              <button
                key={idx}
                type="button"
                className="btn-ghost btn-sm"
                style={{ fontSize: '10px', padding: '3px 8px', borderRadius: '12px' }}
                onClick={() => {
                  setChatInput(item.text);
                  handleSendChat(item.text);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>

          {/* Chat message body */}
          <div style={{ flex: 1, padding: '16px', maxHeight: '430px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {chatMessages.map((msg, i) => {
              const isUnknownWarning =
                msg.text.includes('⚠️ THÔNG BÁO MÃ CHỨNG KHOÁN KHÔNG TỒN TẠI') ||
                msg.config?.risk_flags?.includes('UNKNOWN_SYMBOL_DETECTED');

              return (
                <div
                  key={i}
                  style={{
                    alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '92%',
                    background: msg.sender === 'user'
                      ? 'var(--tealA)'
                      : isUnknownWarning
                      ? 'rgba(245, 166, 35, 0.08)'
                      : 'var(--bg3)',
                    border: msg.sender === 'user'
                      ? '0.5px solid rgba(0, 229, 195, 0.4)'
                      : isUnknownWarning
                      ? '1px solid rgba(245, 166, 35, 0.6)'
                      : '0.5px solid var(--border)',
                    borderRadius: 'var(--rad)',
                    padding: '12px 16px',
                  }}
                >
                  {isUnknownWarning && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: 'var(--gold)', fontWeight: 700, fontSize: '11px' }}>
                      <AlertTriangle size={14} />
                      <span>{lang === 'vi' ? 'CẢNH BÁO MÃ NGOÀI CƠ SỞ DỮ LIỆU' : 'UNKNOWN SYMBOL WARNING'}</span>
                    </div>
                  )}

                  <div style={{ fontSize: '12px', color: 'var(--cream)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                    {msg.text}
                  </div>

                  {/* Generated Bot Config Card */}
                  {msg.config && (
                    <div style={{
                      marginTop: '12px',
                      padding: '12px',
                      background: 'var(--bg4)',
                      borderRadius: 'var(--rad)',
                      borderLeft: isUnknownWarning ? '3px solid var(--gold)' : '3px solid var(--teal)',
                    }}>
                      <div className="mono" style={{ fontSize: '11px', color: 'var(--teal)', fontWeight: 700, marginBottom: '6px' }}>
                        ⚡ {t.arena.generated_config}: {msg.config.bot_id}
                      </div>
                      <div className="mono" style={{ fontSize: '11px', color: 'var(--gold)', fontWeight: 700, marginBottom: '4px' }}>
                        💰 Vốn khởi điểm: {Number(msg.config.initial_cash || activeCapital).toLocaleString('vi-VN')} đ (Trần Odd-lot 25% NAV)
                      </div>
                      <div className="mono" style={{ fontSize: '11px', color: 'var(--cream2)', marginBottom: '3px' }}>
                        {t.arena.target_assets}: <strong>{msg.config.target_assets?.join(', ')}</strong>
                      </div>
                      <div className="mono" style={{ fontSize: '11px', color: 'var(--cream2)', marginBottom: '4px' }}>
                        {t.arena.signal_weights}: Momentum {(msg.config.signal_weights?.momentum || 0) * 100}% | Sentiment {(msg.config.signal_weights?.sentiment || 0) * 100}% | Regime {(msg.config.signal_weights?.regime_gate || 0) * 100}%
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--gold)', marginTop: '4px', fontWeight: 600 }}>
                        {t.arena.sharpe_forecast}: {msg.config.estimated_sharpe} | {t.arena.rec_action}: {msg.config.suggested_action}
                      </div>
                    </div>
                  )}

                  {msg.modelUsed && (
                    <div style={{ marginTop: '6px', fontSize: '10px', color: 'var(--cream3)', fontStyle: 'italic' }}>
                      Engine: {msg.modelUsed}
                    </div>
                  )}
                </div>
              );
            })}
            {chatting && (
              <div style={{ alignSelf: 'flex-start', color: 'var(--teal)', fontSize: '11px', fontStyle: 'italic' }}>
                {t.arena.reasoning_in_progress}
              </div>
            )}
          </div>

          {/* CAPITAL SELECTOR TOOLBAR */}
          <div style={{
            padding: '8px 14px',
            background: 'var(--bg4)',
            borderTop: '0.5px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
            flexWrap: 'wrap',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '11px', color: 'var(--cream3)', fontWeight: 600 }}>
                {lang === 'vi' ? 'Vốn dự kiến:' : 'Budget:'}
              </span>
              {CAPITAL_PRESETS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => {
                    setActiveCapital(p.value);
                    setCustomCapitalInput(p.value.toLocaleString('vi-VN'));
                  }}
                  style={{
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    border: activeCapital === p.value ? '1px solid var(--gold)' : '1px solid var(--border)',
                    background: activeCapital === p.value ? 'rgba(245, 166, 35, 0.15)' : 'var(--bg3)',
                    color: activeCapital === p.value ? 'var(--gold)' : 'var(--cream2)',
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <input
                type="text"
                value={customCapitalInput}
                onChange={(e) => {
                  setCustomCapitalInput(e.target.value);
                  const parsed = parseFloat(e.target.value.replace(/[^0-9]/g, ''));
                  if (!isNaN(parsed) && parsed > 0) {
                    setActiveCapital(parsed);
                  }
                }}
                placeholder={lang === 'vi' ? 'Nhập vốn...' : 'Enter capital...'}
                style={{
                  width: '110px',
                  padding: '2px 6px',
                  fontSize: '11px',
                  borderRadius: '4px',
                  background: 'var(--bg3)',
                  border: '1px solid var(--border)',
                  color: 'var(--gold)',
                  fontWeight: 700,
                  textAlign: 'right',
                }}
              />
              <span style={{ fontSize: '11px', color: 'var(--cream3)' }}>đ</span>
            </div>
          </div>

          {/* Chat input box */}
          <div style={{ padding: '12px 14px', borderTop: '0.5px solid var(--border)', display: 'flex', gap: '8px' }}>
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendChat()}
              placeholder={t.arena.chat_placeholder}
              style={{ flex: 1, fontSize: '12px' }}
              disabled={chatting}
            />
            <button className="btn-main" onClick={() => handleSendChat()} disabled={chatting}>
              <Send size={13} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
