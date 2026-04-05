import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Users, TrendingUp, CheckCircle, Download, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Stats {
  enrollment_count: number;
  avg_mastery: number;
  completion_rate: number;
}

interface HeatmapData {
  modules: string[];
  students: string[];
  scores: number[][];
}

interface Intervention {
  student_name: string;
  stuck_modules: string[];
}

interface StruggleRow {
  student_name: string;
  module_title: string;
  attempts: number;
  last_score: number;
}

const getHeatColor = (v: number) => {
  if (v >= 80) return "bg-emerald-500";
  if (v >= 60) return "bg-emerald-300";
  if (v >= 40) return "bg-yellow-400";
  if (v >= 20) return "bg-orange-400";
  return "bg-red-500";
};

const ProfessorDashboard = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const [stats, setStats] = useState<Stats | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [struggles, setStruggles] = useState<StruggleRow[]>([]);

  useEffect(() => {
    if (!courseId) return;
    api.dashboardStats(courseId).then(setStats).catch(() => {});
    api.dashboardHeatmap(courseId).then(setHeatmap).catch(() => {});
    api.dashboardInterventions(courseId).then((d) => setInterventions(d.interventions || [])).catch(() => {});
    api.dashboardStruggles(courseId).then((d) => setStruggles(d.struggles || [])).catch(() => {});
  }, [courseId]);

  const handleExport = async () => {
    if (!courseId) return;
    const res = await api.dashboardExport(courseId);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `course-${courseId}-canvas-export.json`;
    a.click();
  };

  const statCards = [
    { label: "Enrolled Students", value: stats?.enrollment_count ?? "—", icon: Users, color: "text-primary" },
    { label: "Avg Mastery", value: stats ? `${stats.avg_mastery}%` : "—", icon: TrendingUp, color: "text-success" },
    { label: "Completion Rate", value: stats ? `${stats.completion_rate}%` : "—", icon: CheckCircle, color: "text-warning" },
  ];

  return (
    <div className="min-h-screen bg-secondary/30">
      <div className="max-w-6xl mx-auto py-8 px-4 space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-foreground">Professor Dashboard</h1>
          <Button variant="outline" onClick={handleExport}>
            <Download className="h-4 w-4 mr-1.5" /> Export to Canvas
          </Button>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {statCards.map((s) => (
            <div key={s.label} className="bg-card border rounded-lg p-5 flex items-center gap-4">
              <div className={`p-2.5 rounded-lg bg-secondary ${s.color}`}>
                <s.icon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{s.value}</p>
                <p className="text-xs text-muted-foreground">{s.label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Heatmap */}
        {heatmap && (
          <div className="bg-card border rounded-lg p-5 space-y-3 overflow-x-auto">
            <h2 className="font-semibold text-foreground">Mastery Heatmap</h2>
            <div className="inline-block">
              <div className="flex gap-1 mb-1">
                <div className="w-24" />
                {heatmap.students.map((s) => (
                  <div key={s} className="w-10 text-[10px] text-muted-foreground truncate text-center">{s}</div>
                ))}
              </div>
              {heatmap.modules.map((mod, ri) => (
                <div key={mod} className="flex gap-1 mb-1 items-center">
                  <div className="w-24 text-xs text-foreground truncate">{mod}</div>
                  {heatmap.scores[ri]?.map((score, ci) => (
                    <div
                      key={ci}
                      className={`w-10 h-8 rounded-sm ${getHeatColor(score)} flex items-center justify-center text-[10px] font-medium text-primary-foreground`}
                      title={`${heatmap.students[ci]}: ${score}%`}
                    >
                      {score}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Student Struggles */}
        {heatmap && (
          <div className="bg-card border rounded-lg p-5 space-y-3">
            <h2 className="font-semibold text-foreground">Student Struggles</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Student</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Module</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Attempts</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Last Score</th>
                  </tr>
                </thead>
                <tbody>
                  {struggles.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-4 text-center text-muted-foreground">
                        No struggle data available yet.
                      </td>
                    </tr>
                  ) : (
                    struggles.map((s, i) => (
                      <tr
                        key={i}
                        className={`border-b ${
                          s.attempts > 2
                            ? "bg-red-50"
                            : s.attempts > 1
                            ? "bg-yellow-50"
                            : ""
                        }`}
                      >
                        <td className="py-2 px-3 text-foreground">{s.student_name}</td>
                        <td className="py-2 px-3 text-foreground">{s.module_title}</td>
                        <td className="py-2 px-3">
                          <span
                            className={`inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium ${
                              s.attempts > 2
                                ? "bg-red-100 text-red-700"
                                : s.attempts > 1
                                ? "bg-yellow-100 text-yellow-700"
                                : "bg-gray-100 text-gray-700"
                            }`}
                          >
                            {s.attempts}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-foreground">{s.last_score}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Interventions */}
        {interventions.length > 0 && (
          <div className="space-y-3">
            <h2 className="font-semibold text-foreground flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-danger" /> Students Needing Intervention
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {interventions.map((inv, i) => (
                <div key={i} className="bg-card border border-danger/20 rounded-lg p-4 space-y-1">
                  <p className="font-medium text-foreground">{inv.student_name}</p>
                  <p className="text-xs text-muted-foreground">
                    Stuck on: {inv.stuck_modules.join(", ")}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProfessorDashboard;
