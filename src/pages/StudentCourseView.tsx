import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Lock, Check, ChevronRight, BookOpen } from "lucide-react";
import { Progress } from "@/components/ui/progress";

interface Module {
  id: string;
  title: string;
  completed: boolean;
  unlocked: boolean;
  mastery: number;
}

const StudentCourseView = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const [modules, setModules] = useState<Module[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!courseId) return;
    api.courseGraph(courseId).then((data: any) => {
      const studentId = localStorage.getItem("assign_student_id");
      const mods: Module[] = (data.modules || []).map((m: any, i: number) => ({
        id: m.id,
        title: m.title,
        completed: m.completed ?? false,
        unlocked: m.unlocked ?? i === 0,
        mastery: m.mastery ?? 0,
      }));
      setModules(mods);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [courseId]);

  const completed = modules.filter((m) => m.completed).length;
  const avgMastery = modules.length ? Math.round(modules.reduce((s, m) => s + m.mastery, 0) / modules.length) : 0;

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-muted-foreground">Loading course…</div>;
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-80 bg-navy text-sidebar-foreground flex flex-col">
        <div className="p-6 border-b border-sidebar-border">
          <h1 className="text-lg font-bold">Assign</h1>
          <p className="text-xs text-sidebar-accent-foreground/60 mt-1">Your Learning Journey</p>
        </div>
        <div className="p-4 border-b border-sidebar-border space-y-2">
          <div className="flex justify-between text-sm">
            <span>Progress</span>
            <span>{completed}/{modules.length} modules</span>
          </div>
          <Progress value={modules.length ? (completed / modules.length) * 100 : 0} className="h-2" />
          <p className="text-xs text-sidebar-accent-foreground/60">Overall Mastery: {avgMastery}%</p>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {modules.map((mod, i) => (
            <button
              key={mod.id}
              onClick={() => mod.unlocked && navigate(`/learn/${mod.id}`)}
              disabled={!mod.unlocked}
              className={`w-full flex items-center gap-3 px-4 py-3 text-left text-sm transition-colors ${
                mod.unlocked ? "hover:bg-sidebar-accent cursor-pointer" : "opacity-50 cursor-not-allowed"
              }`}
            >
              <div className="flex-shrink-0">
                {mod.completed ? (
                  <Check className="h-4 w-4 text-success" />
                ) : mod.unlocked ? (
                  <BookOpen className="h-4 w-4 text-primary" />
                ) : (
                  <Lock className="h-4 w-4" />
                )}
              </div>
              <span className="flex-1 truncate">{`${i + 1}. ${mod.title}`}</span>
              {mod.unlocked && <ChevronRight className="h-4 w-4 opacity-50" />}
            </button>
          ))}
        </nav>
      </aside>

      {/* Main */}
      <main className="flex-1 flex items-center justify-center bg-secondary/30">
        <div className="text-center space-y-3">
          <BookOpen className="h-12 w-12 mx-auto text-muted-foreground" />
          <h2 className="text-xl font-semibold text-foreground">Select a module to begin</h2>
          <p className="text-sm text-muted-foreground">Choose a module from the sidebar to start learning.</p>
        </div>
      </main>
    </div>
  );
};

export default StudentCourseView;
