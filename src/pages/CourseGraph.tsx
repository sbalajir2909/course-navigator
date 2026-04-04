import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
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
  faithfulness: "faithful" | "partial" | "unfaithful";
  prerequisites: string[];
}

const faithColors: Record<string, string> = {
  faithful: "bg-success text-primary-foreground",
  partial: "bg-warning text-foreground",
  unfaithful: "bg-danger text-primary-foreground",
};

const CourseGraph = () => {
  const { id } = useParams<{ id: string }>();
  const { toast } = useToast();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedModule, setSelectedModule] = useState<ModuleData | null>(null);

  useEffect(() => {
    if (!id) return;
    api.courseGraph(id).then((data: { modules: ModuleData[]; edges: { source: string; target: string }[] }) => {
      const flowNodes: Node[] = data.modules.map((m, i) => ({
        id: m.id,
        position: { x: (i % 3) * 280, y: Math.floor(i / 3) * 160 },
        data: { label: m.title, module: m },
        type: "default",
        style: {
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: "12px",
          padding: "12px 16px",
          fontSize: "13px",
          fontWeight: 500,
          boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
        },
      }));
      const flowEdges: Edge[] = data.edges.map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        animated: true,
        style: { stroke: "#6366f1" },
      }));
      setNodes(flowNodes);
      setEdges(flowEdges);
    }).catch(() => {});
  }, [id]);

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
          <Badge className={faithColors[selectedModule.faithfulness]}>
            {selectedModule.faithfulness}
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
};

export default CourseGraph;
