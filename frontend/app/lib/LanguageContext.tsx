"use client";

import { createContext, useCallback, useEffect, useMemo, useState } from "react";

export type LanguageCode = "en" | "ta";

interface LanguageState {
  language: LanguageCode;
  isLoading: boolean;
}

interface LanguageContextValue extends LanguageState {
  setLanguage: (lang: LanguageCode) => void;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

const LANGUAGE_KEY = "agrosphere_language";

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<LanguageState>({ language: "en", isLoading: true });

  useEffect(() => {
    const stored =
      typeof window !== "undefined" ? (localStorage.getItem(LANGUAGE_KEY) as LanguageCode | null) : null;

    if (stored === "en" || stored === "ta") {
      setState({ language: stored, isLoading: false });
      return;
    }

    setState({ language: "en", isLoading: false });
  }, []);

  const setLanguage = useCallback((lang: LanguageCode) => {
    setState((prev) => ({ ...prev, language: lang }));
    localStorage.setItem(LANGUAGE_KEY, lang);
  }, []);

  const value = useMemo(
    () => ({
      language: state.language,
      isLoading: state.isLoading,
      setLanguage,
    }),
    [state.language, state.isLoading, setLanguage]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export { LanguageContext };

