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

interface ModuleData {
  id: string;
  title: string;
  description: string;
  learning_objectives: string[];
  faithfulness: "faithful" | "partial" | "unfaithful" | "FAITHFUL" | "PARTIAL" | "UNFAITHFUL";
  prerequisites: string[];
  estimated_minutes?: number;
}

const faithConfig: Record<string, { color: string; label: string }> = {
  faithful: { color: "bg-green-500 text-white", label: "Faithful" },
  FAITHFUL: { color: "bg-green-500 text-white", label: "Faithful" },
  partial: { color: "bg-yellow-400 text-black", label: "Partial" },
  PARTIAL: { color: "bg-yellow-400 text-black", label: "Partial" },
  unfaithful: { color: "bg-red-500 text-white", label: "Unfaithful" },
  UNFAITHFUL: { color: "bg-red-500 text-white", label: "Unfaithful" },
};

function ModuleNode({ data }: { data: { label: string; module: ModuleData } }) {
  const m = data.module;
  const faith = faithConfig[m.faithfulness] || faithConfig.faithful;

  return (
    <div className="bg-white rounded-xl border border-border px-4 py-3 shadow-sm min-w-[180px] max-w-[220px]">
      <Handle type="target" position={Position.Top} className="!bg-primary" />
      <p className="text-sm font-semibold text-foreground leading-tight mb-1.5">{m.title}</p>
      <div className="flex items-center gap-2">
        <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${faith.color}`}>
          {faith.label}
        </span>
        {m.estimated_minutes != null && (
          <span className="text-[10px] text-muted-foreground">{m.estimated_minutes} min</span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-primary" />
    </div>
  );
}

const nodeTypes = { module: ModuleNode };

function CourseGraphInner() {
  const { id } = useParams<{ id: string }>();
  const { toast } = useToast();
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedModule, setSelectedModule] = useState<ModuleData | null>(null);
  const nodesReady = useRef(false);

  useEffect(() => {
    if (!id) return;
    api.courseGraph(id).then((data: { modules: ModuleData[]; edges: { source: string; target: string }[] }) => {
      const flowNodes: Node[] = data.modules.map((m, i) => ({
        id: m.id,
        position: { x: (i % 3) * 300, y: Math.floor(i / 3) * 180 },
        data: { label: m.title, module: m },
        type: "module",
      }));
      const flowEdges: Edge[] = data.edges.map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        animated: true,
        style: { stroke: "hsl(var(--primary))" },
      }));
      setNodes(flowNodes);
      setEdges(flowEdges);
      nodesReady.current = true;
    }).catch(() => {});
  }, [id]);

  useEffect(() => {
    if (nodesReady.current && nodes.length > 0) {
      setTimeout(() => fitView({ padding: 0.2 }), 100);
      nodesReady.current = false;
    }
  }, [nodes, fitView]);

  const onNodeClick = useCallback((_: any, node: Node) => {
    setSelectedModule((node.data as any).module);
  }, []);

  const shareLink = () => {
    const url = `${window.location.origin}/join/${id}`;
    navigator.clipboard.writeText(url);
    toast({ title: "Link copied!", description: url });
  };

  const exportLMS = async () => {
    if (!id) return;
    const res = await api.dashboardExport(id);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `course-${id}-export.json`;
    a.click();
  };

  return (
    <div className="h-screen flex bg-background">
      <div className="flex-1 relative">
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
          <Badge className={faithConfig[selectedModule.faithfulness]?.color}>
            {faithConfig[selectedModule.faithfulness]?.label}
          </Badge>
          <p className="text-sm text-muted-foreground">{selectedModule.description}</p>
          <div>
            <h3 className="text-sm font-semibold text-foreground mb-2">Learning Objectives</h3>
            <ul className="list-disc pl-4 text-sm text-muted-foreground space-y-1">
              {selectedModule.learning_objectives?.map((obj, i) => (
                <li key={i}>{obj}</li>
              ))}
            </ul>
          </div>
          <Button className="w-full" onClick={() => window.open(`/learn/${selectedModule.id}`, "_blank")}>
            View Assessments
          </Button>
        </div>
      )}
    </div>
  );
}

const CourseGraph = () => (
  <ReactFlowProvider>
    <CourseGraphInner />
  </ReactFlowProvider>
);

export default CourseGraph;
