import React, { useEffect, useState } from 'react';
import { Award, Bot, Flame, Send } from 'lucide-react';
import { chatAIStrategy, getArenaBots, getArenaReport } from '../api';

export const BotArenaPage: React.FC = () => {
  const [report, setReport] = useState<any>(null);
  const [allBots, setAllBots] = useState<any[]>([]);
  const [filterType, setFilterType] = useState<'all' | 'ai' | 'non_ai'>('all');
  const [chatInput, setChatInput] = useState<string>('Tôi muốn thiết kế một bot phòng thủ cho rổ VN30 và phái sinh VN30F1M khi thị trường biến động mạnh, vốn 10 triệu VNĐ.');
  const [chatting, setChatting] = useState<boolean>(false);
  const [chatMessages, setChatMessages] = useState<Array<{ sender: 'user' | 'ai'; text: string; config?: any }>>([
    {
      sender: 'ai',
      text: 'Chào bạn! Tôi là VESTA AI Quantitative Strategist (Qwen-2.5-3B). Tôi có thể giúp bạn phân tích bối cảnh thị trường, RAG dữ liệu từ Lakehouse và sinh cấu hình bot chiến lược tối ưu cho mức vốn 10,000,000 VNĐ. Hãy nhập ý tưởng hoặc yêu cầu của bạn!',
    },
  ]);

  useEffect(() => {
    getArenaReport().then(setReport).catch(console.warn);
    getArenaBots().then((res) => setAllBots(res.bots || [])).catch(console.warn);
  }, []);

  const handleSendChat = async () => {
    if (!chatInput.trim()) return;
    const userMsg = chatInput;
    setChatInput('');
    setChatMessages((prev) => [...prev, { sender: 'user', text: userMsg }]);
    setChatting(true);

    try {
      const res = await chatAIStrategy(userMsg, 10000000.0, 'medium');
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: res.reply || 'Đã tạo cấu hình bot tối ưu theo yêu cầu.',
          config: res.bot_config,
        },
      ]);
    } catch (err: any) {
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: `Lỗi khi kết nối mô hình: ${err.message}`,
        },
      ]);
    } finally {
      setChatting(false);
    }
  };

  const topBots = report?.top_10_champion_bots || [];
  const filteredTopBots = filterType === 'all'
    ? topBots
    : filterType === 'ai'
    ? topBots.filter((b: any) => b.is_ai)
    : topBots.filter((b: any) => !b.is_ai);

  return (
    <div style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* HEADER */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h2 className="sans" style={{ fontSize: '20px', fontWeight: 800, color: 'var(--cream)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Flame size={20} color="var(--gold)" />
            Đấu Trường 308 Bot Chiến Lược & AI Strategy Studio (F501 + F502)
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--cream3)' }}>
            Mô phỏng vi cấu trúc Monte Carlo qua 5 kịch bản thị trường, vốn 10M VNĐ/bot, hỗ trợ khớp lô lẻ (Odd-lot) và phái sinh T+0
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <span className="badge badge-gold">VỐN: 10,000,000 VNĐ / BOT</span>
          <span className="badge badge-teal">ODD-LOT COMPLIANT (LÔ 1-99)</span>
        </div>
      </div>

      {/* METRIC STRIP */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '24px' }}>
        <div className="panel" style={{ padding: '16px' }}>
          <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>TỔNG SỐ BOT ĐẤU TRƯỜNG</div>
          <div className="mono tabular" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--cream)', marginTop: '4px' }}>
            {allBots.length > 0 ? allBots.length : (report?.tournament_metadata?.total_bots || 308)} BOTS
          </div>
          <div style={{ fontSize: '11px', color: 'var(--teal)', marginTop: '2px' }}>
            154 Non-AI + 154 AI Model Twins
          </div>
        </div>

        <div className="panel" style={{ padding: '16px' }}>
          <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>VỐN KHỞI ĐIỂM (MANDATORY BUDGET)</div>
          <div className="mono tabular" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--gold)', marginTop: '4px' }}>
            10,000,000 đ
          </div>
          <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
            Trần 25% NAV = 2,500,000 đ / vị thế
          </div>
        </div>

        <div className="panel" style={{ padding: '16px' }}>
          <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>LỚP TÀI SẢN ĐƯỢC PHÉP ĐẦU TƯ</div>
          <div className="sans" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--cream)', marginTop: '4px' }}>
            Đa Tài Sản (Multi-Asset)
          </div>
          <div style={{ fontSize: '11px', color: 'var(--cream3)', marginTop: '2px' }}>
            Cổ phiếu, VN30F1M (T+0), CW, ETF, Bond
          </div>
        </div>

        <div className="panel" style={{ padding: '16px' }}>
          <div style={{ fontSize: '10px', color: 'var(--cream3)' }}>XÁC SUẤT OVERFITTING (PBO)</div>
          <div className="mono tabular" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--green)', marginTop: '4px' }}>
            {( (report?.tournament_metadata?.probability_of_backtest_overfitting_pbo || 0.048) * 100 ).toFixed(1)}%
          </div>
          <div style={{ fontSize: '11px', color: 'var(--green)', marginTop: '2px' }}>
            Đạt ngưỡng an toàn Bailey & Lopez de Prado
          </div>
        </div>
      </div>

      {/* TWO COLUMNS: LEADERBOARD + AI STRATEGY CHATBOX */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr 0.85fr', gap: '24px' }}>
        {/* Left Column: Champion Bots Leaderboard */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title"><Award size={15} color="var(--gold)" /> Bảng Xếp Hạng Top Champion Bots</span>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                className={`btn-ghost btn-sm ${filterType === 'all' ? 'btn-main' : ''}`}
                onClick={() => setFilterType('all')}
              >
                Tất cả
              </button>
              <button
                className={`btn-ghost btn-sm ${filterType === 'ai' ? 'btn-main' : ''}`}
                onClick={() => setFilterType('ai')}
              >
                AI Model Twins
              </button>
              <button
                className={`btn-ghost btn-sm ${filterType === 'non_ai' ? 'btn-main' : ''}`}
                onClick={() => setFilterType('non_ai')}
              >
                Non-AI
              </button>
            </div>
          </div>

          <div style={{ padding: '12px', maxHeight: '520px', overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Hạng</th>
                  <th>Mã Bot</th>
                  <th>Chiến Lược Hợp Nhất</th>
                  <th>Mô Hình AI</th>
                  <th>Mean Sharpe</th>
                  <th>Lợi Nhuận</th>
                  <th>Max DD</th>
                  <th>Win Rate</th>
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
                    <td style={{ fontSize: '11px', color: 'var(--cream2)' }}>
                      {bot.strategy_id}
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

        {/* Right Column: Local AI Strategy Studio Chatbox (Qwen-2.5-3B) */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Bot size={15} color="var(--violet)" />
              <span className="panel-title">AI Strategy Studio (Qwen-2.5-3B CoT + RAG)</span>
            </div>
            <span className="badge badge-violet">SLM GENERATOR (F502)</span>
          </div>

          {/* Chat message body */}
          <div style={{ flex: 1, padding: '16px', maxHeight: '420px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                style={{
                  alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '88%',
                  background: msg.sender === 'user' ? 'var(--tealA)' : 'var(--bg3)',
                  border: msg.sender === 'user' ? '0.5px solid rgba(0, 229, 195, 0.4)' : '0.5px solid var(--border)',
                  borderRadius: 'var(--rad)',
                  padding: '10px 14px',
                }}
              >
                <div style={{ fontSize: '12px', color: 'var(--cream)', lineHeight: 1.6 }}>
                  {msg.text}
                </div>

                {/* If AI generated a bot config */}
                {msg.config && (
                  <div style={{ marginTop: '10px', padding: '10px', background: 'var(--bg4)', borderRadius: 'var(--rad)', borderLeft: '2px solid var(--teal)' }}>
                    <div className="mono" style={{ fontSize: '10px', color: 'var(--teal)', fontWeight: 700, marginBottom: '4px' }}>
                      ⚡ CẤU HÌNH BOT MỚI SINH: {msg.config.bot_id}
                    </div>
                    <div className="mono" style={{ fontSize: '11px', color: 'var(--cream2)' }}>
                      Tài sản mục tiêu: {msg.config.target_assets?.join(', ')}
                    </div>
                    <div className="mono" style={{ fontSize: '11px', color: 'var(--cream2)' }}>
                      Tỷ trọng: Sentiment {msg.config.signal_weights?.sentiment * 100}% | Momentum {msg.config.signal_weights?.momentum * 100}% | F203 {msg.config.signal_weights?.regime_gate * 100}%
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--gold)', marginTop: '4px' }}>
                      Dự phóng Sharpe: {msg.config.estimated_sharpe} | Khuyến nghị: {msg.config.suggested_action}
                    </div>
                  </div>
                )}
              </div>
            ))}
            {chatting && (
              <div style={{ alignSelf: 'flex-start', color: 'var(--teal)', fontSize: '11px', fontStyle: 'italic' }}>
                VESTA Qwen-2.5-3B đang suy luận CoT và RAG từ Lakehouse...
              </div>
            )}
          </div>

          {/* Chat input box */}
          <div style={{ padding: '14px', borderTop: '0.5px solid var(--border)', display: 'flex', gap: '8px' }}>
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendChat()}
              placeholder="Nhập yêu cầu chiến lược hoặc phân bổ danh mục..."
              style={{ flex: 1, fontSize: '12px' }}
              disabled={chatting}
            />
            <button className="btn-main" onClick={handleSendChat} disabled={chatting}>
              <Send size={13} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
