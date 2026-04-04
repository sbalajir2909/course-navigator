import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { auth } from "@/lib/api";

type AuthUser = {
  userId: string;
  role: "student" | "instructor" | "admin";
  firstName: string;
  token: string;
};

type AuthContextType = {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
    role: "student" | "instructor";
    education_level?: string;
  }) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Restore session from localStorage on mount
    const token = localStorage.getItem("assign_token");
    const stored = localStorage.getItem("assign_user");
    if (token && stored) {
      try {
        const parsed = JSON.parse(stored);
        setUser({ ...parsed, token });
      } catch {
        localStorage.removeItem("assign_token");
        localStorage.removeItem("assign_user");
      }
    }
    setIsLoading(false);
  }, []);

  const login = async (email: string, password: string) => {
    const res = await auth.login(email, password);
    const authUser: AuthUser = {
      userId: res.user_id,
      role: res.role as AuthUser["role"],
      firstName: res.first_name,
      token: res.access_token,
    };
    localStorage.setItem("assign_token", res.access_token);
    localStorage.setItem("assign_user", JSON.stringify({ userId: res.user_id, role: res.role, firstName: res.first_name }));
    setUser(authUser);
  };

  const register = async (data: Parameters<typeof auth.register>[0]) => {
    const res = await auth.register(data);
    const authUser: AuthUser = {
      userId: res.user_id,
      role: res.role as AuthUser["role"],
      firstName: res.first_name,
      token: res.access_token,
    };
    localStorage.setItem("assign_token", res.access_token);
    localStorage.setItem("assign_user", JSON.stringify({ userId: res.user_id, role: res.role, firstName: res.first_name }));
    setUser(authUser);
  };

  const logout = () => {
    localStorage.removeItem("assign_token");
    localStorage.removeItem("assign_user");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
