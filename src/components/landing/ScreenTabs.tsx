import { useState } from "react";
import { MessageSquare, LayoutDashboard, GraduationCap } from "lucide-react";

const tabs = [
  {
    id: "student",
    label: "Student View",
    icon: GraduationCap,
    description: "A personal AI tutor embedded in coursework. Guides thinking with hints and breakdowns—not answers.",
    mockup: (
      <div className="bg-card rounded-xl border p-6 space-y-4">
        <div className="flex items-center gap-3 pb-4 border-b">
          <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
            <GraduationCap className="w-4 h-4 text-primary" />
          </div>
          <div>
            <div className="text-sm font-medium">CS 201 — Data Structures</div>
            <div className="text-xs text-muted-foreground">Session 3 of 8</div>
          </div>
          <div className="ml-auto flex gap-1">
            {[1,2,3,4,5,6,7,8].map(i => (
              <div key={i} className={`w-6 h-1.5 rounded-full ${i <= 3 ? 'bg-primary' : 'bg-muted'}`} />
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-full bg-primary/10 flex-shrink-0 flex items-center justify-center text-xs text-primary font-medium">AI</div>
            <div className="bg-secondary rounded-lg rounded-tl-none px-4 py-3 text-sm max-w-[80%]">
              Think about what happens when you insert an element into a full array. What needs to happen to the existing data?
            </div>
          </div>
          <div className="flex gap-3 justify-end">
            <div className="bg-primary text-primary-foreground rounded-lg rounded-tr-none px-4 py-3 text-sm max-w-[80%]">
              It needs to be copied to a bigger array?
            </div>
          </div>
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-full bg-primary/10 flex-shrink-0 flex items-center justify-center text-xs text-primary font-medium">AI</div>
            <div className="bg-secondary rounded-lg rounded-tl-none px-4 py-3 text-sm max-w-[80%]">
              Exactly! Now, what's the time complexity of that copy operation?
            </div>
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          {["Give me a hint", "Break it down", "Show an example"].map(chip => (
            <button key={chip} className="px-3 py-1.5 rounded-full border text-xs font-medium text-muted-foreground hover:border-primary hover:text-primary transition-colors">
              {chip}
            </button>
          ))}
        </div>
      </div>
    ),
  },
  {
    id: "instructor",
    label: "Instructor Dashboard",
    icon: LayoutDashboard,
    description: "Real-time visibility into class-wide learning patterns. Know where students struggle before they tell you.",
    mockup: (
      <div className="bg-card rounded-xl border p-6 space-y-5">
        <div className="flex items-center justify-between pb-4 border-b">
          <div>
            <div className="font-serif text-lg">Class Overview</div>
            <div className="text-xs text-muted-foreground">CS 201 · 87 students · Week 6</div>
          </div>
          <div className="flex gap-2">
            <div className="px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">Live</div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Active Now", value: "34", trend: "↑ 12%" },
            { label: "Avg. Mastery", value: "72%", trend: "↑ 5%" },
            { label: "At-Risk", value: "8", trend: "↓ 3" },
          ].map(m => (
            <div key={m.label} className="rounded-lg bg-secondary/50 p-3">
              <div className="text-xs text-muted-foreground">{m.label}</div>
              <div className="text-xl font-serif mt-1">{m.value}</div>
              <div className="text-xs text-primary mt-0.5">{m.trend}</div>
            </div>
          ))}
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium">Topic Difficulty Map</div>
          {[
            { topic: "Recursion", pct: 45, color: "bg-destructive" },
            { topic: "Linked Lists", pct: 72, color: "bg-primary" },
            { topic: "Arrays", pct: 89, color: "bg-primary" },
          ].map(t => (
            <div key={t.topic} className="flex items-center gap-3">
              <span className="text-xs w-24 text-muted-foreground">{t.topic}</span>
              <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                <div className={`h-full rounded-full ${t.color}`} style={{ width: `${t.pct}%` }} />
              </div>
              <span className="text-xs font-medium w-8 text-right">{t.pct}%</span>
            </div>
          ))}
        </div>

        <div className="rounded-lg border border-warning/30 bg-warning/5 p-3">
          <div className="text-xs font-medium text-warning flex items-center gap-1.5">
            💡 Suggested Action
          </div>
          <div className="text-sm mt-1">
            <strong>Reteach recursion</strong> — 55% of students are stuck on base case identification. Consider a worked example in Wednesday's lecture.
          </div>
        </div>
      </div>
    ),
  },
  {
    id: "institution",
    label: "Institution View",
    icon: MessageSquare,
    description: "Measurable outcomes at scale. See how Assign improves retention, performance, and teaching efficiency across departments.",
    mockup: (
      <div className="bg-card rounded-xl border p-6 space-y-5">
        <div className="flex items-center justify-between pb-4 border-b">
          <div>
            <div className="font-serif text-lg">Institutional Impact</div>
            <div className="text-xs text-muted-foreground">Fall 2025 · All departments</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {[
            { label: "Student Retention", value: "+12%", sub: "vs. previous year" },
            { label: "Course Pass Rate", value: "91%", sub: "up from 79%" },
            { label: "Instructor Hours Saved", value: "340h", sub: "across 28 courses" },
            { label: "Student Satisfaction", value: "4.6/5", sub: "end-of-term survey" },
          ].map(m => (
            <div key={m.label} className="rounded-lg bg-secondary/50 p-4">
              <div className="text-xs text-muted-foreground">{m.label}</div>
              <div className="text-2xl font-serif text-primary mt-1">{m.value}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{m.sub}</div>
            </div>
          ))}
        </div>

        <div className="rounded-lg border p-3 space-y-2">
          <div className="text-sm font-medium">Feedback Loop Health</div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-primary" /> Students active
            </span>
            <span>→</span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-primary/60" /> Insights generated
            </span>
            <span>→</span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-primary/30" /> Actions taken
            </span>
          </div>
          <div className="flex gap-1 h-8 items-end">
            {[40,55,62,70,68,75,82,88,85,90,94,92].map((v,i) => (
              <div key={i} className="flex-1 bg-primary/20 rounded-t" style={{ height: `${v}%` }}>
                <div className="w-full bg-primary rounded-t" style={{ height: `${Math.min(v, 80)}%` }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    ),
  },
];

const ScreenTabs = () => {
  const [active, setActive] = useState("student");
  const current = tabs.find((t) => t.id === active)!;

  return (
    <section id="screens" className="py-20">
      <div className="container">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <h2 className="text-3xl md:text-4xl tracking-tight mb-4">
            See it in action
          </h2>
          <p className="text-muted-foreground text-lg">
            Three perspectives, one connected system.
          </p>
        </div>

        <div className="flex justify-center gap-2 mb-10">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActive(tab.id)}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-medium transition-all ${
                active === tab.id
                  ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                  : "bg-secondary text-muted-foreground hover:text-foreground"
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        <div className="grid lg:grid-cols-2 gap-12 items-center max-w-5xl mx-auto">
          <div className="space-y-4">
            <h3 className="text-2xl font-serif">{current.label}</h3>
            <p className="text-muted-foreground leading-relaxed">
              {current.description}
            </p>
          </div>
          <div>{current.mockup}</div>
        </div>
      </div>
    </section>
  );
};

export default ScreenTabs;
