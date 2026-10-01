"use client";

import { useCallback, useEffect, useState } from "react";

import {
  DEFAULT_STATE,
  PersonalInvestmentState,
  STORAGE_KEY,
} from "@/lib/personal-investment";

function loadState(): PersonalInvestmentState {
  if (typeof window === "undefined") return DEFAULT_STATE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    const saved = JSON.parse(raw) as Partial<PersonalInvestmentState>;
    return {
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
    };
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
  }, []);

  useEffect(() => {
    if (ready) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [ready, state]);

  const reset = useCallback(() => setState(DEFAULT_STATE), []);

  return { state, setState, ready, reset };
}
