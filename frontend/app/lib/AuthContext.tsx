"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { fetchCurrentUser, UserResponse } from "./api";

/* ── Types ──────────────────────────────────────────────────────────── */
interface AuthState {
  user: UserResponse | null;
  token: string | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  /** Persist a JWT and the associated user profile. */
  login: (token: string, user: UserResponse) => void;
  /** Clear the session. */
  logout: () => void;
}

/* ── Context ────────────────────────────────────────────────────────── */
const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "agrosphere_token";

/* ── Provider ───────────────────────────────────────────────────────── */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: null,
    isLoading: true,
  });

  /* Hydrate from localStorage on first mount */
  useEffect(() => {
    const stored = typeof window !== "undefined"
      ? localStorage.getItem(TOKEN_KEY)
      : null;

    if (!stored) {
      setState({ user: null, token: null, isLoading: false });
      return;
    }

    fetchCurrentUser(stored)
      .then((user) => setState({ user, token: stored, isLoading: false }))
      .catch(() => {
        // Token invalid / expired — clear it silently
        localStorage.removeItem(TOKEN_KEY);
        setState({ user: null, token: null, isLoading: false });
      });
  }, []);

  const login = useCallback((token: string, user: UserResponse) => {
    localStorage.setItem(TOKEN_KEY, token);
    setState({ user, token, isLoading: false });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setState({ user: null, token: null, isLoading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/* ── Raw context export (consumed by useAuth) ───────────────────────── */
export { AuthContext };
