import React from 'react';
import { Activity, BarChart2, Database, Flame, Languages, ShieldAlert } from 'lucide-react';
import { useLang } from '../LangContext';

export type NavTab = 'overview' | 'dashboard' | 'crawler' | 'preprocessing' | 'arena';

interface NavbarProps {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  systemHealthy?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ activeTab, setActiveTab, systemHealthy = true }) => {
  const { lang, t, toggle } = useLang();

  const tabs = [
    { id: 'overview' as NavTab, label: t.nav.overview, icon: <Activity size={14} /> },
    { id: 'dashboard' as NavTab, label: t.nav.dashboard, icon: <BarChart2 size={14} /> },
    { id: 'crawler' as NavTab, label: t.nav.crawler, icon: <Database size={14} /> },
    { id: 'preprocessing' as NavTab, label: t.nav.preprocessing, icon: <ShieldAlert size={14} /> },
    { id: 'arena' as NavTab, label: t.nav.arena, icon: <Flame size={14} /> },
  ];

  return (
    <header style={{
      background: 'var(--bg)',
      borderBottom: '0.5px solid var(--border)',
      padding: '0 24px',
      height: '56px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 100,
    }}>
      {/* Brand & Pulse Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }} onClick={() => setActiveTab('overview')}>
          <span className="pulse-dot" style={{ background: systemHealthy ? 'var(--teal)' : 'var(--red)' }} />
          <span className="sans" style={{ fontSize: '15px', fontWeight: 800, letterSpacing: '0.04em', color: 'var(--cream)' }}>
            VESTA <span style={{ color: 'var(--teal)', fontWeight: 400 }}>QUANT</span>
          </span>
        </div>
        <span className="mono" style={{ fontSize: '10px', color: 'var(--cream3)', borderLeft: '0.5px solid var(--border2)', paddingLeft: '12px' }}>
          SLM × LAM v2.0
        </span>
      </div>

      {/* Nav Navigation Links */}
      <nav style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '7px 14px',
                borderRadius: 'var(--rad)',
                background: isActive ? 'var(--tealA)' : 'transparent',
                color: isActive ? 'var(--teal)' : 'var(--cream2)',
                border: isActive ? '0.5px solid rgba(0, 229, 195, 0.4)' : '0.5px solid transparent',
                fontSize: '12px',
                fontWeight: isActive ? 700 : 500,
                transition: 'var(--transition)',
              }}
              onMouseEnter={(e) => {
                if (!isActive) (e.currentTarget as HTMLElement).style.color = 'var(--cream)';
              }}
              onMouseLeave={(e) => {
                if (!isActive) (e.currentTarget as HTMLElement).style.color = 'var(--cream2)';
              }}
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Right Controls: Language Switcher */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={toggle}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '5px 12px',
            background: 'var(--bg2)',
            border: '0.5px solid var(--border)',
            borderRadius: 'var(--rad)',
            cursor: 'pointer',
            color: 'var(--cream)',
            fontSize: '11px',
            fontWeight: 700,
            transition: 'var(--transition)',
          }}
          title={lang === 'vi' ? 'Switch to English' : 'Chuyển sang Tiếng Việt'}
        >
          <Languages size={14} color="var(--gold)" />
          <span className="mono" style={{ color: 'var(--gold)', letterSpacing: '0.05em' }}>{lang.toUpperCase()}</span>
        </button>
      </div>
    </header>
  );
};
