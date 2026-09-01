/** Auth context: token lifecycle, current user, and role helpers. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "./api";
import type { TokenResponse, User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  isAdmin: boolean;
  isClient: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  // Restore the session on mount. The token lives in localStorage but the user
  // is re-fetched rather than cached: a role or tenancy change on the server
  // must take effect immediately, not at token expiry.
  useEffect(() => {
    setUnauthorizedHandler(logout);

    const token = tokenStore.get();
    if (!token) {
      setLoading(false);
      return;
    }

    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));

    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.post<TokenResponse>(
      "/auth/login",
      { email, password },
      { skipAuthRedirect: true },
    );
    tokenStore.set(response.access_token);
    setUser(response.user);
    return response.user;
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      isAdmin: user?.role === "COMPANY_ADMIN" || user?.role === "COMPANY_OPERATOR",
      isClient: user?.role === "CLIENT",
      login,
      logout,
    }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

/** Where a user lands after login, based on role. */
export function homeRouteFor(user: User | null): string {
  if (!user) return "/login";
  return user.role === "CLIENT" ? "/client" : "/company";
}
