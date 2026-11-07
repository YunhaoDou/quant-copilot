"use client";

import { useCallback, useEffect, useState } from "react";
import { migrateCompanies } from "@/lib/company-store";

import {
  DEFAULT_STATE,
  PersonalInvestmentState,
  STORAGE_KEY,
} from "@/lib/personal-investment";

function loadState(): PersonalInvestmentState {
  if (typeof window === "undefined") return DEFAULT_STATE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return migrateCompanies(DEFAULT_STATE);
    const saved = JSON.parse(raw) as Partial<PersonalInvestmentState>;
    return migrateCompanies({
      ...DEFAULT_STATE,
      ...saved,
      profile: {
        ...DEFAULT_STATE.profile,
        ...saved.profile,
        allocations: {
          ...DEFAULT_STATE.profile.allocations,
          ...saved.profile?.allocations,
        },
      },
      holdings: saved.holdings ?? [],
      watchlist: saved.watchlist ?? [],
      research: saved.research ?? [],
      journal: saved.journal ?? [],
      marketEnvironment: {
        ...DEFAULT_STATE.marketEnvironment,
        ...saved.marketEnvironment,
      },
      marketThemes: saved.marketThemes ?? [],
    });
  } catch {
    return DEFAULT_STATE;
  }
}

export function usePersonalInvestment() {
  const [state, setState] = useState<PersonalInvestmentState>(DEFAULT_STATE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setState(loadState());
    setReady(true);
    const sync = (event: StorageEvent) => { if (event.key === STORAGE_KEY && event.newValue) setState(loadState()); };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  useEffect(() => {
    if (ready) {
      const value = JSON.stringify(state);
      if (window.localStorage.getItem(STORAGE_KEY) !== value) window.localStorage.setItem(STORAGE_KEY, value);
    }
  }, [ready, state]);

  const reset = useCallback(() => setState(migrateCompanies(DEFAULT_STATE)), []);

  return { state, setState, ready, reset };
}
