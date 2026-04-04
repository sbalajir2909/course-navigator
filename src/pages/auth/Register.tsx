import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";

const Register = () => {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    role: "student" as "student" | "instructor",
    education_level: "undergraduate",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const update = (field: string, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(form);
      navigate(form.role === "instructor" ? "/instructor" : "/student");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed. Try again.");
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
    <div className="min-h-screen bg-background flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="font-serif text-3xl text-primary font-bold">Assign</h1>
          <p className="text-sm text-muted-foreground mt-1">Create your account</p>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          {/* Role toggle */}
          <div className="flex rounded-lg border border-border overflow-hidden mb-5">
            {(["student", "instructor"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => update("role", r)}
                className={`flex-1 py-2 text-sm font-medium transition-colors capitalize ${
                  form.role === r
                    ? "bg-primary text-primary-foreground"
                    : "bg-card text-muted-foreground hover:text-foreground"
                }`}
              >
                {r}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">First name</label>
                <input
                  value={form.first_name}
                  onChange={(e) => update("first_name", e.target.value)}
                  required
                  placeholder="Alex"
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Last name</label>
                <input
                  value={form.last_name}
                  onChange={(e) => update("last_name", e.target.value)}
                  required
                  placeholder="Smith"
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => update("email", e.target.value)}
                required
                placeholder="you@university.edu"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-foreground mb-1">Password</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => update("password", e.target.value)}
                required
                minLength={8}
                placeholder="8+ characters"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>

            {form.role === "student" && (
              <div>
                <label className="block text-xs font-medium text-foreground mb-1">Level</label>
                <select
                  value={form.education_level}
                  onChange={(e) => update("education_level", e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                >
                  <option value="high_school">High School</option>
                  <option value="undergraduate">Undergraduate</option>
                  <option value="graduate">Graduate</option>
                </select>
              </div>
            )}

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-60 mt-1"
            >
              {loading ? "Creating account…" : "Create account"}
            </button>
          </form>

          <p className="text-center text-sm text-muted-foreground mt-4">
            Already have an account?{" "}
            <Link to="/login" className="text-primary hover:underline font-medium">
              Sign in
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
      </div>
    </div>
  );
};

export default Register;
