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
    localStorage.setItem("assign_course_id", courseId);

    // Fetch graph to get module list, and optionally student progress
    const studentId = localStorage.getItem("assign_student_id");

    Promise.all([
      api.courseGraph(courseId),
      studentId
        ? api.studentProgress(courseId, studentId).catch(() => null)
        : Promise.resolve(null),
    ]).then(([graphData, progressData]) => {
      // The graph API returns { nodes, edges } - extract modules from nodes
      const nodes = graphData.nodes || graphData.modules || [];
      const progressMap: Record<string, { completed: boolean; mastery: number }> =
        {};
      if (progressData?.modules) {
        for (const pm of progressData.modules) {
          progressMap[pm.id] = {
            completed: pm.completed ?? false,
            mastery: pm.mastery ?? 0,
          };
        }
      }

      // Build edge map to determine prerequisites
      const edges = graphData.edges || [];
      const prerequisites: Record<string, string[]> = {};
      for (const edge of edges) {
        if (!prerequisites[edge.target]) prerequisites[edge.target] = [];
        prerequisites[edge.target].push(edge.source);
      }

      const mods: Module[] = nodes.map((n: any, i: number) => {
        const nodeId = n.id;
        const title = n.data?.label || n.title || `Module ${i + 1}`;
        const prog = progressMap[nodeId];

        // A module is unlocked if it has no prerequisites, or all prerequisites are completed
        const prereqs = prerequisites[nodeId] || [];
        const allPrereqsDone =
          prereqs.length === 0 ||
          prereqs.every((pid: string) => progressMap[pid]?.completed);

        return {
          id: nodeId,
          title,
          completed: prog?.completed ?? false,
          unlocked: n.unlocked ?? allPrereqsDone ?? i === 0,
          mastery: prog?.mastery ?? 0,
        };
      });

      // Ensure at least the first module is unlocked
      if (mods.length > 0 && !mods.some((m) => m.unlocked)) {
        mods[0].unlocked = true;
      }

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
              onClick={() => mod.unlocked && navigate(`/course/${courseId}/learn/${mod.id}`)}
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
