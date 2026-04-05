import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "react-router-dom";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X, Share2, Download } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

/* ---------- Types ---------- */

interface GraphNodeData {
  label: string;
  order_index: number;
  estimated_minutes?: number;
  faithfulness_verdict: "FAITHFUL" | "PARTIAL" | "UNFAITHFUL" | null;
}

interface GraphNode {
  id: string;
  data: GraphNodeData;
  position: { x: number; y: number };
  type: string;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  animated: boolean;
}

interface CourseModule {
  id: string;
  title: string;
  description: string;
  learning_objectives: string[];
  estimated_minutes?: number;
  faithfulness_verdict?: string;
}

interface CourseDetail {
  id: string;
  title: string;
  modules: CourseModule[];
}

/* ---------- Faithfulness config ---------- */

const faithConfig: Record<string, { color: string; label: string }> = {
  FAITHFUL: { color: "bg-green-500 text-white", label: "Faithful" },
  PARTIAL: { color: "bg-yellow-400 text-black", label: "Partial" },
  UNFAITHFUL: { color: "bg-red-500 text-white", label: "Unfaithful" },
};

const DEFAULT_FAITH = { color: "bg-gray-400 text-white", label: "Unknown" };

function getFaith(verdict: string | null | undefined) {
  if (!verdict) return DEFAULT_FAITH;
  return faithConfig[verdict.toUpperCase()] ?? DEFAULT_FAITH;
}

/* ---------- Custom Node ---------- */

function ModuleNode({ data }: { data: { label: string; graphData: GraphNodeData } }) {
  const d = data.graphData;
  const faith = getFaith(d.faithfulness_verdict);

  return (
    <div className="bg-white rounded-xl border border-border px-4 py-3 shadow-sm min-w-[180px] max-w-[220px]">
      <Handle type="target" position={Position.Top} className="!bg-primary" />
      <p className="text-sm font-semibold text-foreground leading-tight mb-1.5">{data.label}</p>
      <div className="flex items-center gap-2">
        <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${faith.color}`}>
          {faith.label}
        </span>
        {d.estimated_minutes != null && (
          <span className="text-[10px] text-muted-foreground">{d.estimated_minutes} min</span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-primary" />
    </div>
  );
}

const nodeTypes = { module: ModuleNode, default: ModuleNode };

/* ---------- Inner component (needs ReactFlowProvider ancestor) ---------- */

function CourseGraphInner() {
  const { id } = useParams<{ id: string }>();
  const { toast } = useToast();
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedModule, setSelectedModule] = useState<CourseModule | null>(null);
  const [courseDetail, setCourseDetail] = useState<CourseDetail | null>(null);
  const nodesReady = useRef(false);

  /* Fetch graph data from /api/courses/:id/graph */
  useEffect(() => {
    if (!id) return;
    api
      .courseGraph(id)
      .then((data: { nodes: GraphNode[]; edges: GraphEdge[] }) => {
        const flowNodes: Node[] = (data.nodes ?? []).map((n, i) => ({
          id: n.id,
          position:
            n.position && (n.position.x !== 0 || n.position.y !== 0)
              ? n.position
              : { x: (i % 3) * 300, y: Math.floor(i / 3) * 200 },
          data: { label: n.data.label, graphData: n.data },
          type: "module",
        }));
        const flowEdges: Edge[] = (data.edges ?? []).map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          animated: e.animated ?? true,
          type: "smoothstep",
          label: "prerequisite",
          labelStyle: { fontSize: 10, fill: "#6366f1" },
          style: { stroke: "hsl(var(--primary))" },
        }));
        setNodes(flowNodes);
        setEdges(flowEdges);
        nodesReady.current = true;
      })
      .catch((err) => {
        console.error("Failed to load course graph:", err);
        toast({ title: "Error loading graph", description: "Could not fetch course data.", variant: "destructive" });
      });
  }, [id]);

  /* Fetch full course details for the side panel */
  useEffect(() => {
    if (!id) return;
    api
      .courseDetail(id)
      .then((data: CourseDetail) => {
        setCourseDetail(data);
      })
      .catch((err) => {
        console.error("Failed to load course detail:", err);
      });
  }, [id]);

  /* Fit view once nodes are rendered */
  useEffect(() => {
    if (nodesReady.current && nodes.length > 0) {
      setTimeout(() => fitView({ padding: 0.2 }), 100);
      nodesReady.current = false;
    }
  }, [nodes, fitView]);

  /* Click a node -> open side panel with full module info */
  const onNodeClick = useCallback(
    (_: any, node: Node) => {
      const graphData = (node.data as any).graphData as GraphNodeData;
      // Try to find the full module from courseDetail, fallback to graph data
      const fullModule = courseDetail?.modules?.find((m) => m.id === node.id);
      if (fullModule) {
        setSelectedModule(fullModule);
      } else {
        // Fallback: use what we have from the graph node
        setSelectedModule({
          id: node.id,
          title: graphData.label,
          description: "",
          learning_objectives: [],
          estimated_minutes: graphData.estimated_minutes,
          faithfulness_verdict: graphData.faithfulness_verdict ?? undefined,
        });
      }
    },
    [courseDetail],
  );

  const shareLink = () => {
    const url = `${window.location.origin}/join/${id}`;
    navigator.clipboard.writeText(url);
    toast({ title: "Link copied!", description: url });
  };

  const exportLMS = async () => {
    if (!id) return;
    try {
      const res = await api.dashboardExport(id);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `course-${id}-export.json`;
      a.click();
    } catch (err) {
      console.error("Export failed:", err);
      toast({ title: "Export failed", variant: "destructive" });
    }
  };

  return (
    <div className="h-screen flex bg-background">
      <div className="flex-1 relative" style={{ height: "100vh" }}>
        <div className="absolute top-4 left-4 z-10 flex gap-2">
          <Button size="sm" variant="outline" onClick={shareLink}>
            <Share2 className="h-4 w-4 mr-1.5" /> Share Course Link
          </Button>
          <Button size="sm" variant="outline" onClick={exportLMS}>
            <Download className="h-4 w-4 mr-1.5" /> Export to LMS
          </Button>
        </div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>

      {selectedModule && (
        <div className="w-96 border-l bg-card p-6 overflow-y-auto space-y-4">
          <div className="flex items-start justify-between">
            <h2 className="text-lg font-semibold text-foreground">{selectedModule.title}</h2>
            <button onClick={() => setSelectedModule(null)}>
              <X className="h-5 w-5 text-muted-foreground" />
            </button>
          </div>
          <Badge className={getFaith(selectedModule.faithfulness_verdict).color}>
            {getFaith(selectedModule.faithfulness_verdict).label}
          </Badge>
          {selectedModule.estimated_minutes != null && (
            <p className="text-sm text-muted-foreground">{selectedModule.estimated_minutes} min estimated</p>
          )}
          {selectedModule.description && (
            <p className="text-sm text-muted-foreground">{selectedModule.description}</p>
          )}
          {selectedModule.learning_objectives?.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-foreground mb-2">Learning Objectives</h3>
              <ul className="list-disc pl-4 text-sm text-muted-foreground space-y-1">
                {selectedModule.learning_objectives.map((obj, i) => (
                  <li key={i}>{obj}</li>
                ))}
              </ul>
            </div>
          )}
          <Button className="w-full" onClick={() => window.open(`/course/${id}/learn/${selectedModule.id}`, "_blank")}>
            View Assessments
          </Button>
        </div>
      )}
    </div>
  );
}

/* ---------- Wrapper with provider ---------- */

const CourseGraph = () => (
  <ReactFlowProvider>
    <CourseGraphInner />
  </ReactFlowProvider>
);

export default CourseGraph;
