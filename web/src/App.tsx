import React, { useState } from 'react';
import { Navbar } from './components/Navbar';
import type { NavTab } from './components/Navbar';
import { TickerStrip } from './components/TickerStrip';
import { OverviewPage } from './pages/OverviewPage';
import { DashboardPage } from './pages/DashboardPage';
import { CrawlerPage } from './pages/CrawlerPage';
import { PreprocessingPage } from './pages/PreprocessingPage';
import { FeedbackPage } from './pages/FeedbackPage';
import { BotArenaPage } from './pages/BotArenaPage';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>('overview');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', background: 'var(--bg)' }}>
      {/* Top Navbar */}
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Marquee Financial Ticker */}
      <TickerStrip />

      {/* Page Body */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {activeTab === 'overview' && <OverviewPage setActiveTab={setActiveTab} />}
        {activeTab === 'dashboard' && <DashboardPage />}
        {activeTab === 'crawler' && <CrawlerPage />}
        {activeTab === 'preprocessing' && <PreprocessingPage />}
        {activeTab === 'feedback' && <FeedbackPage />}
        {activeTab === 'arena' && <BotArenaPage />}
      </main>

      {/* Footer (Kế thừa từ Anhkiet.dev / kietfolio footer) */}
      <footer style={{
        borderTop: '0.5px solid var(--border)',
        padding: '16px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '11px',
        color: 'var(--cream3)',
        background: 'var(--bg)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>© 2026 Tran Anh Kiet — VESTA Quant Labs</span>
          <span>•</span>
          <span className="mono">Autonomous Trading Systems (SLM × LAM)</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="pulse-dot" style={{ width: '5px', height: '5px' }} />
          <span>Ho Chi Minh City, Vietnam</span>
          <span>•</span>
          <span className="mono" style={{ color: 'var(--teal)' }}>DuckDB Native :8899</span>
        </div>
      </footer>
    </div>
  );
};

export default App;
