import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Trophy, Flame, Star } from "lucide-react";
import { gamification } from "@/lib/api";
import { events } from "@/lib/events";

// Demo data — used when backend is not connected
const DEMO_LEADERBOARD = [
  { rank: 1, name: "Ananya R.", total_score: 412, streak: 14, badge: "👑" },
  { rank: 2, name: "Lena B.",   total_score: 384, streak: 9,  badge: "⚡" },
  { rank: 3, name: "Yuki S.",   total_score: 341, streak: 7,  badge: "🔥" },
  { rank: 4, name: "Ravi P.",   total_score: 278, streak: 5,  badge: null },
  { rank: 5, name: "Priya M.",  total_score: 231, streak: 4,  badge: null },
  { rank: 6, name: "Marcus L.", total_score: 189, streak: 3,  badge: null },
  { rank: 7, name: "Devon T.",  total_score: 92,  streak: 1,  badge: null },
  { rank: 8, name: "Jordan K.", total_score: 10,  streak: 0,  badge: null },
];

const MY_RANK = 5; // demo: "you" are rank 5

const Leaderboard = () => {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<"all_time" | "weekly">("all_time");
  const [rows, setRows] = useState(DEMO_LEADERBOARD);
  const [streakData, setStreakData] = useState({ current_streak: 4, freeze_tokens_remaining: 2 });

  // In production: swap with real API calls
  // useEffect(() => {
  //   gamification.leaderboard("CLASS_ID", period).then(d => setRows(d.leaderboard));
  //   events.leaderboardViewed({ userId: "USER_ID", classId: "CLASS_ID" });
  // }, [period]);

  const medalColors: Record<number, string> = {
    1: "text-yellow-500",
    2: "text-slate-400",
    3: "text-amber-600",
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <nav className="border-b border-border bg-card px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate("/student")} className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <Trophy className="w-5 h-5 text-primary" />
        <span className="font-serif text-xl text-foreground">Leaderboard</span>
        <span className="text-sm text-muted-foreground">CS 301 — Algorithms</span>
      </nav>

      <div className="max-w-2xl mx-auto px-4 py-6">
        {/* Streak card */}
        <div className="bg-card border border-border rounded-xl p-4 mb-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center">
              <Flame className="w-5 h-5 text-orange-500" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">Your streak</p>
              <p className="text-xs text-muted-foreground">Keep it going!</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-2xl font-serif text-foreground">{streakData.current_streak} days</p>
            <p className="text-xs text-muted-foreground">{streakData.freeze_tokens_remaining} freeze{streakData.freeze_tokens_remaining !== 1 ? "s" : ""} left</p>
          </div>
        </div>

        {/* Period toggle */}
        <div className="flex rounded-lg border border-border overflow-hidden mb-4 w-fit">
          {(["all_time", "weekly"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                period === p ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground"
              }`}
            >
              {p === "all_time" ? "All Time" : "This Week"}
            </button>
          ))}
        </div>

        {/* Leaderboard table */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {rows.map((row) => {
            const isMe = row.rank === MY_RANK;
            return (
              <div
                key={row.rank}
                className={`flex items-center gap-4 px-4 py-3.5 border-b border-border last:border-0 ${
                  isMe ? "bg-primary/5 border-l-2 border-l-primary" : ""
                }`}
              >
                {/* Rank */}
                <div className={`w-8 text-center font-serif text-lg ${medalColors[row.rank] ?? "text-muted-foreground"}`}>
                  {row.rank <= 3 ? ["🥇", "🥈", "🥉"][row.rank - 1] : row.rank}
                </div>

                {/* Avatar */}
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary flex-shrink-0">
                  {row.name.split(" ").map((n) => n[0]).join("")}
                </div>

                {/* Name */}
                <div className="flex-1">
                  <span className={`text-sm font-medium ${isMe ? "text-primary" : "text-foreground"}`}>
                    {row.name}{isMe && " (you)"}
                  </span>
                  {row.streak > 0 && (
                    <span className="ml-2 text-xs text-orange-500">🔥 {row.streak}d</span>
                  )}
                </div>

                {/* Score */}
                <div className="text-right">
                  <p className="text-sm font-medium text-foreground">{row.total_score} pts</p>
                  {row.badge && <p className="text-xs">{row.badge}</p>}
                </div>
              </div>
            );
          })}
        </div>

        {/* Scoring info */}
        <div className="mt-4 bg-muted/50 rounded-xl p-4 text-xs text-muted-foreground space-y-1">
          <p className="font-medium text-foreground text-sm mb-2">How scores are calculated</p>
          <p>🔥 Daily streak (30%) — consistency is king</p>
          <p>📚 Sessions completed (20%) — showing up matters</p>
          <p>🎯 Quiz performance (20%) — knowledge demonstration</p>
          <p>📈 Improvement rate (15%) — growth over time</p>
          <p>💡 Confusion resolved (10%) — working through struggle</p>
        </div>
      </div>
    </div>
  );
};

export default Leaderboard;
