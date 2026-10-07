import React, { createContext, useContext, useEffect, useState } from 'react';
import { type Language, translations, type Translations } from './i18n';

interface LangContextType {
  lang: Language;
  t: Translations;
  toggle: () => void;
  setLang: (lang: Language) => void;
}

const LangContext = createContext<LangContextType | null>(null);

export const LangProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [lang, setLangState] = useState<Language>(() => {
    const saved = localStorage.getItem('vesta-lang');
    return saved === 'en' ? 'en' : 'vi';
  });

  const setLang = (newLang: Language) => {
    setLangState(newLang);
    localStorage.setItem('vesta-lang', newLang);
  };

  const toggle = () => {
    setLang(lang === 'vi' ? 'en' : 'vi');
  };

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value: LangContextType = {
    lang,
    t: translations[lang],
    toggle,
    setLang,
  };

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
};

export const useLang = (): LangContextType => {
  const ctx = useContext(LangContext);
  if (!ctx) {
    throw new Error('useLang must be used within a LangProvider');
  }
  return ctx;
};
