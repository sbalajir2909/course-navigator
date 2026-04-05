import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Loader2, Brain } from "lucide-react";

interface DiagnosticQuestion {
  id: string;
  question: string;
  type: string;
  options?: string[];
  correct_answer?: string;
  tier?: string;
  moduleId: string;
  moduleTitle: string;
}

interface ModuleScore {
  id: string;
  title: string;
  score: number;
  total: number;
  percentage: number;
  skip: boolean;
}

const DiagnosticQuiz = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [questions, setQuestions] = useState<DiagnosticQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [finished, setFinished] = useState(false);
  const [moduleScores, setModuleScores] = useState<ModuleScore[]>([]);

  useEffect(() => {
    if (!courseId) return;
    localStorage.setItem("assign_course_id", courseId);

    (async () => {
      try {
        const graphData = await api.courseGraph(courseId);
        const nodes = graphData.nodes || [];

        // Fetch recall-tier assessments for each module (3-5 questions each)
        const allQuestions: DiagnosticQuestion[] = [];
        for (const node of nodes) {
          try {
            const assessData = await api.moduleAssessments(courseId, node.id);
            const qs = assessData.questions || [];
            // Prefer recall-tier questions, fallback to any questions
            const recallQs = qs.filter((q: any) => q.tier === "recall");
            const selectedQs = recallQs.length > 0 ? recallQs : qs;
            const picked = selectedQs.slice(0, 5).map((q: any) => ({
              ...q,
              moduleId: node.id,
              moduleTitle: node.data?.label || node.title || node.id,
            }));
            allQuestions.push(...picked);
          } catch {
            // Module may not have assessments yet
          }
        }

        setQuestions(allQuestions);
      } catch {
        // If we can't load diagnostic data, skip to learning path
        navigate(`/course/${courseId}/path`);
      }
      setLoading(false);
    })();
  }, [courseId, navigate]);

  const handleAnswer = (questionId: string, answer: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: answer }));
  };

  const handleNext = () => {
    if (currentIdx < questions.length - 1) {
      setCurrentIdx(currentIdx + 1);
    } else {
      scoreDiagnostic();
    }
  };

  const scoreDiagnostic = () => {
    // Group questions by module and score them
    const moduleMap: Record<string, { title: string; correct: number; total: number }> = {};

    for (const q of questions) {
      if (!moduleMap[q.moduleId]) {
        moduleMap[q.moduleId] = { title: q.moduleTitle, correct: 0, total: 0 };
      }
      moduleMap[q.moduleId].total++;
      if (q.type === "multiple_choice" && answers[q.id] === q.correct_answer) {
        moduleMap[q.moduleId].correct++;
      }
    }

    const scores: ModuleScore[] = Object.entries(moduleMap).map(([id, data]) => ({
      id,
      title: data.title,
      score: data.correct,
      total: data.total,
      percentage: data.total > 0 ? Math.round((data.correct / data.total) * 100) : 0,
      skip: data.total > 0 ? (data.correct / data.total) >= 0.7 : false,
    }));

    setModuleScores(scores);
    setFinished(true);

    // Store learning path in localStorage for use by LearningPath page
    localStorage.setItem(`assign_diagnostic_scores_${courseId}`, JSON.stringify(scores));
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-secondary/30 gap-4">
        <Loader2 className="h-8 w-8 text-primary animate-spin" />
        <p className="text-muted-foreground">Preparing diagnostic questions…</p>
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-secondary/30 gap-4">
        <Brain className="h-12 w-12 text-muted-foreground" />
        <p className="text-muted-foreground">No diagnostic questions available.</p>
        <Button onClick={() => navigate(`/course/${courseId}/learn`)}>
          Start Learning
        </Button>
      </div>
    );
  }

  if (finished) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-secondary/30">
        <div className="w-full max-w-lg bg-card rounded-xl shadow-lg border p-8 space-y-6">
          <div className="text-center space-y-2">
            <Brain className="h-10 w-10 mx-auto text-primary" />
            <h1 className="text-2xl font-bold text-foreground">Diagnostic Complete</h1>
            <p className="text-sm text-muted-foreground">Here's what we found about your knowledge.</p>
          </div>

          <div className="space-y-3">
            {moduleScores.map((ms) => (
              <div key={ms.id} className="flex items-center gap-3 p-3 rounded-lg border">
                <div className="flex-1">
                  <p className="text-sm font-medium text-foreground">{ms.title}</p>
                  <Progress value={ms.percentage} className="h-2 mt-1" />
                </div>
                <div className="text-right">
                  <span className="text-sm font-semibold text-foreground">{ms.percentage}%</span>
                  {ms.skip ? (
                    <Badge className="ml-2 bg-emerald-100 text-emerald-700">Can Skip</Badge>
                  ) : (
                    <Badge className="ml-2 bg-amber-100 text-amber-700">Needs Review</Badge>
                  )}
                </div>
              </div>
            ))}
          </div>

          <Button className="w-full" onClick={() => navigate(`/course/${courseId}/path`)}>
            View Your Learning Path
          </Button>
        </div>
      </div>
    );
  }

  const q = questions[currentIdx];

  return (
    <div className="min-h-screen flex items-center justify-center bg-secondary/30">
      <div className="w-full max-w-lg bg-card rounded-xl shadow-lg border p-8 space-y-6">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-bold text-foreground">Diagnostic Quiz</h1>
            <span className="text-sm text-muted-foreground">
              {currentIdx + 1} / {questions.length}
            </span>
          </div>
          <Progress value={((currentIdx + 1) / questions.length) * 100} className="h-2" />
          <p className="text-xs text-muted-foreground">Module: {q.moduleTitle}</p>
        </div>

        <div className="space-y-4">
          <p className="text-sm font-medium text-foreground">{q.question}</p>

          {q.type === "multiple_choice" && q.options ? (
            <div className="space-y-2">
              {q.options.map((opt, j) => (
                <label
                  key={j}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    answers[q.id] === opt
                      ? "border-primary bg-primary/5"
                      : "hover:border-primary/50"
                  }`}
                >
                  <input
                    type="radio"
                    name={q.id}
                    value={opt}
                    checked={answers[q.id] === opt}
                    onChange={() => handleAnswer(q.id, opt)}
                    className="accent-primary"
                  />
                  <span className="text-sm text-foreground">{opt}</span>
                </label>
              ))}
            </div>
          ) : (
            <textarea
              className="w-full border rounded-lg p-3 text-sm min-h-[80px] focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Type your answer…"
              value={answers[q.id] || ""}
              onChange={(e) => handleAnswer(q.id, e.target.value)}
            />
          )}
        </div>

        <Button
          className="w-full"
          onClick={handleNext}
          disabled={!answers[q.id]}
        >
          {currentIdx < questions.length - 1 ? "Next Question" : "Finish Diagnostic"}
        </Button>
      </div>
    </div>
  );
};

export default DiagnosticQuiz;
