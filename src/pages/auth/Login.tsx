import { useState, useEffect } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";

const API_BASE = "http://localhost:8000";

type Role = "student" | "professor";

const Login = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [role, setRole] = useState<Role>(
    (searchParams.get("role") as Role) || "student"
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [backendDown, setBackendDown] = useState(false);

  // Check backend health on mount
  useEffect(() => {
    fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) })
      .then(r => setBackendDown(!r.ok))
      .catch(() => setBackendDown(true));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (role === "professor") {
      // Professor flow: store email and go to upload/dashboard
      localStorage.setItem("assign_role", "professor");
      localStorage.setItem("assign_email", email);
      setLoading(false);
      navigate("/upload");
      return;
    }

    // Student login flow
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        signal: AbortSignal.timeout(8000),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Login failed. Check your email and password.");
      }
      localStorage.setItem("assign_token", data.token);
      localStorage.setItem("assign_student_id", data.student_id);
      localStorage.setItem("assign_name", data.name);
      localStorage.setItem("assign_email", data.email);
      localStorage.setItem("assign_student_email", data.email);
      localStorage.setItem("assign_role", "student");
      navigate("/student");
    } catch (err: any) {
      if (err.name === "TimeoutError" || err.message?.includes("fetch")) {
        setBackendDown(true);
        setError("Cannot reach the backend server. Make sure uvicorn is running: cd ~/assign-b2b && uvicorn main:app --reload");
      } else {
        setError(err.message || "Login failed. Try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  // Skip login for demo — go straight to student view
  const handleDemoSkip = () => {
    localStorage.setItem("assign_student_id", "demo-student-" + Date.now());
    localStorage.setItem("assign_student_email", "demo@assign.ai");
    localStorage.setItem("assign_name", "Demo Student");
    localStorage.setItem("assign_role", "student");
    navigate("/student");
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="font-serif text-3xl text-primary font-bold">Assign</h1>
          <p className="text-sm text-muted-foreground mt-1">Sign in to your account</p>
        </div>

        {/* Backend down warning */}
        {backendDown && (
          <div className="mb-4 bg-orange-50 border border-orange-200 rounded-xl px-4 py-3 text-sm text-orange-800">
            <p className="font-medium mb-1">Backend server not running</p>
            <p className="text-xs text-orange-600 mb-2">Start it in a terminal:</p>
            <code className="block bg-orange-100 rounded px-2 py-1 text-xs font-mono">cd ~/assign-b2b && uvicorn main:app --reload</code>
            <button
              onClick={handleDemoSkip}
              className="mt-2 w-full text-xs text-orange-700 underline hover:text-orange-900"
            >
              Or continue as demo user (no login required)
            </button>
          </div>
        )}

        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          {/* Role selector tabs */}
          <div className="flex rounded-lg bg-muted p-1 mb-5">
            <button
              type="button"
              onClick={() => { setRole("student"); setError(""); }}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                role === "student"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Student
            </button>
            <button
              type="button"
              onClick={() => { setRole("professor"); setError(""); }}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                role === "professor"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Professor
            </button>
          </div>

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

            {role === "student" && (
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
            )}

            {error && (
              <div className="text-xs text-destructive bg-destructive/10 px-3 py-2 rounded-lg">{error}</div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-60"
            >
              {loading
                ? "Signing in…"
                : role === "professor"
                ? "Continue to Dashboard"
                : "Sign in"}
            </button>
          </form>

          {role === "student" && (
            <div className="mt-4 space-y-2">
              <p className="text-center text-sm text-muted-foreground">
                No account?{" "}
                <Link to="/register" className="text-primary hover:underline font-medium">
                  Create one
                </Link>
              </p>
              <p className="text-center text-xs text-muted-foreground">
                <button onClick={handleDemoSkip} className="text-muted-foreground hover:text-foreground underline">
                  Continue without account
                </button>
              </p>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-muted-foreground mt-6">
          <Link to="/" className="hover:underline">Back to home</Link>
        </p>
      </div>
    </div>
  );
};

export default Login;
