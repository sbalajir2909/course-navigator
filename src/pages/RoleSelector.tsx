import { useNavigate } from "react-router-dom";
import { GraduationCap, BarChart3 } from "lucide-react";

const roles = [
  {
    title: "I'm a Student",
    description: "Access your AI tutor, track progress, and master concepts at your own pace.",
    icon: GraduationCap,
    path: "/login?role=student",
  },
  {
    title: "I'm an Instructor",
    description: "See how your students are learning, spot struggles early, and teach smarter.",
    icon: BarChart3,
    path: "/login?role=professor",
  },
];

const RoleSelector = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4">
      <h1 className="text-4xl md:text-5xl font-serif text-foreground mb-3">Welcome to Assign</h1>
      <p className="text-muted-foreground text-lg mb-12 text-center max-w-md">
        Choose your role to get started
      </p>
      <div className="flex flex-col sm:flex-row gap-6">
        {roles.map((role) => (
          <button
            key={role.path}
            onClick={() => navigate(role.path)}
            className="group w-72 rounded-xl border border-border bg-card p-8 text-left transition-all duration-200 hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
          >
            <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-5 group-hover:bg-primary/20 transition-colors">
              <role.icon className="w-6 h-6 text-primary" />
            </div>
            <h2 className="text-xl font-serif text-foreground mb-2">{role.title}</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">{role.description}</p>
          </button>
        ))}
      </div>
    </div>
  );
};

export default RoleSelector;
