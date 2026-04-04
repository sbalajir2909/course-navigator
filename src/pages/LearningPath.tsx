import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { CheckCircle, BookOpen, SkipForward, ArrowRight, Loader2 } from "lucide-react";

interface PathModule {
  id: string;
  title: string;
  skip: boolean;
  percentage: number;
  order: number;
}

const LearningPath = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const [modules, setModules] = useState<PathModule[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!courseId) return;
    localStorage.setItem("assign_course_id", courseId);

    (async () => {
      try {
        // Load graph data for module ordering
        const graphData = await api.courseGraph(courseId);
        const nodes = graphData.nodes || [];
        const edges = graphData.edges || [];

        // Load diagnostic scores from localStorage
        const scoresRaw = localStorage.getItem(`assign_diagnostic_scores_${courseId}`);
        const scores: Record<string, { skip: boolean; percentage: number }> = {};
        if (scoresRaw) {
          try {
            const parsed = JSON.parse(scoresRaw);
            for (const s of parsed) {
              scores[s.id] = { skip: s.skip, percentage: s.percentage };
            }
          } catch {}
        }

        // Build prerequisite order using topological sort
        const inDegree: Record<string, number> = {};
        const adj: Record<string, string[]> = {};
        for (const node of nodes) {
          inDegree[node.id] = 0;
          adj[node.id] = [];
        }
        for (const edge of edges) {
          adj[edge.source] = adj[edge.source] || [];
          adj[edge.source].push(edge.target);
          inDegree[edge.target] = (inDegree[edge.target] || 0) + 1;
        }

        const queue: string[] = [];
        for (const id of Object.keys(inDegree)) {
          if (inDegree[id] === 0) queue.push(id);
        }
        const sorted: string[] = [];
        while (queue.length > 0) {
          const cur = queue.shift()!;
          sorted.push(cur);
          for (const next of adj[cur] || []) {
            inDegree[next]--;
            if (inDegree[next] === 0) queue.push(next);
          }
        }
        // Add any nodes not reached by topo sort
        for (const node of nodes) {
          if (!sorted.includes(node.id)) sorted.push(node.id);
        }

        const nodeMap: Record<string, any> = {};
        for (const n of nodes) nodeMap[n.id] = n;

        const pathModules: PathModule[] = sorted.map((id, i) => {
          const node = nodeMap[id];
          const title = node?.data?.label || node?.title || id;
          const score = scores[id];
          return {
            id,
            title,
            skip: score?.skip ?? false,
            percentage: score?.percentage ?? 0,
            order: i,
          };
        });

        setModules(pathModules);

        // Store learning path for use by the recommendation banner
        localStorage.setItem(
          `assign_learning_path_${courseId}`,
          JSON.stringify(pathModules)
        );
      } catch {}
      setLoading(false);
    })();
  }, [courseId]);

  const firstNeeded = modules.find((m) => !m.skip);
  const skippable = modules.filter((m) => m.skip).length;
  const toLearn = modules.filter((m) => !m.skip).length;

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-secondary/30 gap-4">
        <Loader2 className="h-8 w-8 text-primary animate-spin" />
        <p className="text-muted-foreground">Building your learning path…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-secondary/30">
      <div className="max-w-2xl mx-auto py-8 px-4 space-y-8">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-foreground">Your Learning Path</h1>
          <p className="text-sm text-muted-foreground">
            Based on your diagnostic results, here's your personalized learning plan.
          </p>
        </div>

        {/* Summary */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-card border rounded-lg p-4 text-center">
            <p className="text-2xl font-bold text-emerald-600">{skippable}</p>
            <p className="text-xs text-muted-foreground mt-1">Modules you can skip</p>
          </div>
          <div className="bg-card border rounded-lg p-4 text-center">
            <p className="text-2xl font-bold text-primary">{toLearn}</p>
            <p className="text-xs text-muted-foreground mt-1">Modules to learn</p>
          </div>
        </div>

        {/* Module list */}
        <div className="space-y-2">
          {modules.map((mod, i) => (
            <div
              key={mod.id}
              className={`flex items-center gap-4 p-4 rounded-lg border ${
                mod.skip
                  ? "bg-emerald-50/50 border-emerald-200"
                  : "bg-card"
              }`}
            >
              <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold bg-secondary text-foreground">
                {i + 1}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className={`text-sm font-medium truncate ${mod.skip ? "text-muted-foreground" : "text-foreground"}`}>
                    {mod.title}
                  </p>
                  {mod.skip ? (
                    <Badge className="bg-emerald-100 text-emerald-700 flex-shrink-0">
                      <SkipForward className="h-3 w-3 mr-1" /> Can Skip
                    </Badge>
                  ) : (
                    <Badge className="bg-primary/10 text-primary flex-shrink-0">
                      <BookOpen className="h-3 w-3 mr-1" /> To Learn
                    </Badge>
                  )}
                </div>
                <Progress value={mod.percentage} className="h-1.5 mt-2" />
              </div>
              <span className="text-xs text-muted-foreground flex-shrink-0">
                {mod.percentage}%
              </span>
            </div>
          ))}
        </div>

        {/* Start Learning button */}
        <Button
          className="w-full"
          size="lg"
          onClick={() => {
            if (firstNeeded) {
              navigate(`/course/${courseId}/learn/${firstNeeded.id}`);
            } else {
              navigate(`/course/${courseId}/learn`);
            }
          }}
        >
          {firstNeeded ? (
            <>Start Learning: {firstNeeded.title} <ArrowRight className="h-4 w-4 ml-2" /></>
          ) : (
            <>Review All Modules <CheckCircle className="h-4 w-4 ml-2" /></>
          )}
        </Button>

        <Button
          variant="outline"
          className="w-full"
          onClick={() => navigate(`/course/${courseId}/learn`)}
        >
          View All Modules
        </Button>
      </div>
    </div>
  );
};

export default LearningPath;
