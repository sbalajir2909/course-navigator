import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Flame, Star, BookOpen, CheckCircle } from "lucide-react";

// Demo data — replace with API calls in production
const TOPICS = [
  { name: "Recursion",          progress: 72, sessions: 7,  quizScore: 80, status: "in_progress" },
  { name: "Big-O Notation",     progress: 90, sessions: 9,  quizScore: 94, status: "mastered"    },
  { name: "Sorting Algorithms", progress: 55, sessions: 4,  quizScore: 65, status: "in_progress" },
  { name: "Dynamic Programming",progress: 30, sessions: 2,  quizScore: 40, status: "in_progress" },
  { name: "Graph Traversal",    progress: 10, sessions: 1,  quizScore: 0,  status: "not_started"  },
];

const BADGES = [
  { id: "first_session",  label: "First Step",   icon: "🌱", earned: true  },
  { id: "streak_3",       label: "On a Roll",    icon: "🔥", earned: true  },
  { id: "streak_7",       label: "Week Warrior", icon: "⚡", earned: false },
  { id: "quiz_ace",       label: "Quiz Ace",     icon: "🎯", earned: false },
  { id: "course_complete",label: "Complete",     icon: "🎓", earned: false },
];

const progressColor = (p: number) =>
  p >= 80 ? "bg-primary" : p >= 50 ? "bg-warning" : "bg-destructive";

const Progress = () => {
  const navigate = useNavigate();
  const streak = 4;
  const totalSessions = TOPICS.reduce((a, t) => a + t.sessions, 0);
  const masteredCount = TOPICS.filter((t) => t.status === "mastered").length;
  const overallProgress = Math.round(TOPICS.reduce((a, t) => a + t.progress, 0) / TOPICS.length);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <nav className="border-b border-border bg-card px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate("/student")} className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <Star className="w-5 h-5 text-primary" />
        <span className="font-serif text-xl text-foreground">My Progress</span>
        <span className="text-sm text-muted-foreground">CS 301 — Algorithms</span>
      </nav>

      <div className="max-w-2xl mx-auto px-4 py-6 space-y-5">
        {/* Summary cards */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-card border border-border rounded-xl p-4 text-center">
            <div className="text-2xl font-serif text-primary">{streak}</div>
            <div className="text-xs text-muted-foreground mt-1">Day streak 🔥</div>
          </div>
          <div className="bg-card border border-border rounded-xl p-4 text-center">
            <div className="text-2xl font-serif text-foreground">{totalSessions}</div>
            <div className="text-xs text-muted-foreground mt-1">Sessions</div>
          </div>
          <div className="bg-card border border-border rounded-xl p-4 text-center">
            <div className="text-2xl font-serif text-foreground">{masteredCount}/{TOPICS.length}</div>
            <div className="text-xs text-muted-foreground mt-1">Mastered</div>
          </div>
        </div>

        {/* Overall progress */}
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-serif text-lg text-foreground">Course Progress</h2>
            <span className="text-sm font-medium text-primary">{overallProgress}%</span>
          </div>
          <div className="h-2.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-700"
              style={{ width: `${overallProgress}%` }}
            />
          </div>
        </div>

        {/* Topic breakdown */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-border">
            <h2 className="font-serif text-lg text-foreground">Topics</h2>
          </div>
          {TOPICS.map((t) => (
            <div key={t.name} className="px-5 py-4 border-b border-border last:border-0">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {t.status === "mastered" && <CheckCircle className="w-4 h-4 text-primary" />}
                  {t.status === "in_progress" && <BookOpen className="w-4 h-4 text-warning" />}
                  {t.status === "not_started" && <div className="w-4 h-4 rounded-full border-2 border-border" />}
                  <span className="text-sm font-medium text-foreground">{t.name}</span>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>{t.sessions} sessions</span>
                  {t.quizScore > 0 && <span>Quiz: {t.quizScore}%</span>}
                  <span className="font-medium text-foreground">{t.progress}%</span>
                </div>
              </div>
              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${progressColor(t.progress)}`}
                  style={{ width: `${t.progress}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Badges */}
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="font-serif text-lg text-foreground mb-4">Badges</h2>
          <div className="grid grid-cols-5 gap-3">
            {BADGES.map((b) => (
              <div
                key={b.id}
                className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border text-center transition-opacity ${
                  b.earned
                    ? "border-primary/30 bg-primary/5"
                    : "border-border opacity-40 grayscale"
                }`}
              >
                <span className="text-2xl">{b.icon}</span>
                <span className="text-xs text-foreground leading-tight">{b.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Progress;
