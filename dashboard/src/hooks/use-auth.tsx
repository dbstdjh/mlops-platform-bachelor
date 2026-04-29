import { createContext, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError, setUnauthorizedHandler } from "@/lib/api";
import { clearToken, isTokenExpired, readToken, writeToken } from "@/lib/auth-storage";
import type { User } from "@/types/api";

interface AuthContextValue {
  isBootstrapping: boolean;
  isAuthenticated: boolean;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearToken();
      setUser(null);
      navigate("/login", { replace: true });
    });

    return () => {
      setUnauthorizedHandler(null);
    };
  }, [navigate]);

  useEffect(() => {
    void bootstrapSession();
  }, []);

  async function bootstrapSession() {
    const token = readToken();
    if (!token || isTokenExpired(token)) {
      clearToken();
      setUser(null);
      setIsBootstrapping(false);
      return;
    }

    try {
      const profile = await api.getMe();
      setUser(profile);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        throw error;
      }
      clearToken();
      setUser(null);
    } finally {
      setIsBootstrapping(false);
    }
  }

  async function refreshSession() {
    const profile = await api.getMe();
    setUser(profile);
  }

  async function login(email: string, password: string) {
    const token = await api.login({ email, password });
    writeToken(token.access_token);
    const profile = await api.getMe();
    setUser(profile);
  }

  async function register(email: string, password: string) {
    await api.register({ email, password });
    await login(email, password);
  }

  function logout() {
    clearToken();
    setUser(null);
    navigate("/login", { replace: true });
  }

  return (
    <AuthContext.Provider
      value={{
        isBootstrapping,
        isAuthenticated: user !== null,
        user,
        login,
        register,
        logout,
        refreshSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
