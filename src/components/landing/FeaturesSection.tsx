import { Brain, BarChart3, Users, Lightbulb, Shield, Zap } from "lucide-react";

const features = [
  {
    icon: Brain,
    title: "AI That Teaches, Not Tells",
    description: "Students get hints, questions, and step-by-step breakdowns—not copy-paste answers.",
  },
  {
    icon: BarChart3,
    title: "Learning Fingerprints",
    description: "Every hesitation, retry, and breakthrough builds a unique profile of how each student learns.",
  },
  {
    icon: Users,
    title: "Instructor Intelligence",
    description: "Walk into lecture knowing exactly where the class is struggling—before they tell you.",
  },
  {
    icon: Lightbulb,
    title: "Suggested Actions",
    description: "Assign doesn't just show data. It tells instructors what to reteach, reassign, or revisit.",
  },
  {
    icon: Shield,
    title: "Controlled AI Usage",
    description: "Turn AI from a cheating concern into a measurable, transparent learning tool.",
  },
  {
    icon: Zap,
    title: "LMS Integration",
    description: "Embeds directly into Canvas, Blackboard, and more. No separate login, no friction.",
  },
];

const FeaturesSection = () => {
  return (
    <section id="features" className="py-20 bg-secondary/50">
      <div className="container">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <h2 className="text-3xl md:text-4xl tracking-tight mb-4">
            Two sides, one system
          </h2>
          <p className="text-muted-foreground text-lg">
            Students learn better. Instructors teach smarter. Institutions see
            results.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((f) => (
            <div
              key={f.title}
              className="group rounded-xl border bg-card p-6 hover:shadow-lg hover:shadow-primary/5 transition-all duration-300"
            >
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                <f.icon className="w-5 h-5 text-primary" />
              </div>
              <h3 className="text-lg font-serif mb-2">{f.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
