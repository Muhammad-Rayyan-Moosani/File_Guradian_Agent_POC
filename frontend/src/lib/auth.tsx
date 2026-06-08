import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "./api";

/**
 * Shared login state for the whole app.
 *
 * Login is opt-in on the server: if no admin credentials are configured, the
 * backend reports authEnabled=false and everyone is treated as signed in, so
 * the app behaves exactly as it did before this feature existed.
 */
interface AuthState {
  loading: boolean;
  authEnabled: boolean;
  authenticated: boolean;
  username?: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState<string | null>(null);

  // Ask the backend on first load whether login is required and if we're in.
  const refresh = useCallback(async () => {
    try {
      const status = await api.me();
      setAuthEnabled(status.authEnabled);
      setAuthenticated(status.authenticated);
      setUsername(status.username ?? null);
    } catch {
      // If even /api/me fails, assume we need to log in to be safe.
      setAuthEnabled(true);
      setAuthenticated(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // If any API call comes back 401 (e.g. the session expired), drop to login.
  useEffect(() => {
    function handleUnauthorized() {
      setAuthEnabled(true);
      setAuthenticated(false);
    }
    window.addEventListener("fg:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("fg:unauthorized", handleUnauthorized);
  }, []);

  const login = useCallback(async (user: string, password: string) => {
    const status = await api.login(user, password);
    setAuthEnabled(status.authEnabled);
    setAuthenticated(status.authenticated);
    setUsername(status.username ?? null);
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setAuthenticated(false);
    setUsername(null);
  }, []);

  const value: AuthState = {
    loading,
    authEnabled,
    authenticated,
    username,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Read the shared login state. Must be used inside <AuthProvider>.
 */
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
