import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";

const Login = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      const stored = localStorage.getItem("assign_user");
      const user = stored ? JSON.parse(stored) : null;
      navigate(user?.role === "instructor" ? "/instructor" : "/student");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleDemo = (role: "student" | "instructor") => {
    localStorage.setItem("assign_token", "demo-token");
    localStorage.setItem("assign_user", JSON.stringify({ userId: "demo", role, firstName: "Demo" }));
    navigate(role === "instructor" ? "/instructor" : "/student");
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="font-serif text-3xl text-primary font-bold">Assign</h1>
          <p className="text-sm text-muted-foreground mt-1">Sign in to your account</p>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@university.edu"
                className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-60"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="text-center text-sm text-muted-foreground mt-4">
            No account?{" "}
            <Link to="/register" className="text-primary hover:underline font-medium">
              Create one
            </Link>
          </p>

          <div className="mt-5 pt-5 border-t border-border">
            <p className="text-center text-xs text-muted-foreground mb-3">Or jump straight in →</p>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => handleDemo("student")}
                className="py-2 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-colors"
              >
                Demo as Student
              </button>
              <button
                onClick={() => handleDemo("instructor")}
                className="py-2 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-colors"
              >
                Demo as Instructor
              </button>
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-6">
          <Link to="/" className="hover:underline">← Back to home</Link>
        </p>
      </div>
    </div>
  );
};

export default Login;
