import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { UserSession } from "../types";

type AuthContextValue = {
  session: UserSession | null;
  login: (session: UserSession) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function storedSession(): UserSession | null {
  const raw = localStorage.getItem("freight-session");
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as UserSession;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<UserSession | null>(storedSession);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      login: (nextSession) => {
        localStorage.setItem("freight-session", JSON.stringify(nextSession));
        setSession(nextSession);
      },
      logout: () => {
        localStorage.removeItem("freight-session");
        setSession(null);
      },
    }),
    [session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
