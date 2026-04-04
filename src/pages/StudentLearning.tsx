import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowRight, Loader2 } from "lucide-react";

const tierColors: Record<string, string> = {
  recall: "bg-indigo-100 text-indigo-700",
  application: "bg-amber-100 text-amber-700",
  synthesis: "bg-emerald-100 text-emerald-700",
};

const StudentLearning = () => {
  const { moduleId } = useParams<{ moduleId: string }>();
  const navigate = useNavigate();

  // Learn state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [explanation, setExplanation] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [response, setResponse] = useState("");
  const [feedback, setFeedback] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const explanationRef = useRef<HTMLDivElement>(null);

  // Quiz state
  const [questions, setQuestions] = useState<any[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [quizResults, setQuizResults] = useState<any>(null);

  useEffect(() => {
    if (!moduleId) return;
    const studentId = localStorage.getItem("assign_student_id") || "anon";
    api.teachStart(moduleId, studentId).then((data) => {
      setSessionId(data.session_id);
      // Start SSE
      const es = api.teachExplainSSE(data.session_id);
      setStreaming(true);
      es.onmessage = (e) => {
        if (e.data === "[DONE]") {
          es.close();
          setStreaming(false);
          return;
        }
        setExplanation((prev) => prev + e.data);
      };
      es.onerror = () => {
        es.close();
        setStreaming(false);
      };
    });
  }, [moduleId]);

  useEffect(() => {
    if (explanationRef.current) {
      explanationRef.current.scrollTop = explanationRef.current.scrollHeight;
    }
  }, [explanation]);

  const handleSubmitResponse = async () => {
    if (!sessionId || !response.trim()) return;
    setSubmitting(true);
    try {
      const data = await api.teachSubmit(sessionId, response);
      setFeedback(data);
    } catch {}
    setSubmitting(false);
  };

  const loadQuiz = async () => {
    if (!moduleId) return;
    // Extract courseId from URL or use a placeholder
    const courseId = localStorage.getItem("assign_course_id") || "default";
    try {
      const data = await api.moduleAssessments(courseId, moduleId);
      setQuestions(data.questions || []);
    } catch {}
  };

  const scoreQuiz = () => {
    let correct = 0;
    questions.forEach((q: any) => {
      if (q.type === "multiple_choice" && answers[q.id] === q.correct_answer) correct++;
    });
    setQuizResults({ correct, total: questions.length });
  };

  return (
    <div className="min-h-screen bg-secondary/30">
      <div className="max-w-3xl mx-auto py-8 px-4 space-y-6">
        <h1 className="text-2xl font-bold text-foreground">Module: {moduleId}</h1>

        <Tabs defaultValue="learn" className="space-y-4">
          <TabsList>
            <TabsTrigger value="learn">Learn</TabsTrigger>
            <TabsTrigger value="quiz" onClick={loadQuiz}>Quiz</TabsTrigger>
          </TabsList>

          <TabsContent value="learn" className="space-y-6">
            {/* Streamed explanation */}
            <div
              ref={explanationRef}
              className="bg-card border rounded-lg p-6 min-h-[200px] max-h-[400px] overflow-y-auto text-sm text-foreground whitespace-pre-wrap leading-relaxed"
            >
              {explanation || (streaming && <span className="text-muted-foreground animate-pulse-slow">Loading explanation…</span>)}
              {streaming && <span className="inline-block w-1.5 h-4 bg-primary animate-pulse ml-0.5 align-text-bottom" />}
            </div>

            {/* Student response */}
            {!feedback ? (
              <div className="space-y-3">
                <Textarea
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                  placeholder="Explain this concept in your own words…"
                  className="min-h-[120px]"
                />
                <Button onClick={handleSubmitResponse} disabled={submitting || !response.trim()}>
                  {submitting ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Submitting…</> : "Submit"}
                </Button>
              </div>
            ) : (
              <div className="bg-card border rounded-lg p-6 space-y-4">
                <h3 className="font-semibold text-foreground">Feedback</h3>
                <p className="text-sm text-muted-foreground">{feedback.feedback}</p>
                <div className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-foreground">Mastery Score</span>
                    <span className="font-semibold text-primary">{feedback.mastery}%</span>
                  </div>
                  <Progress value={feedback.mastery} className="h-2.5" />
                </div>
                {feedback.advance && (
                  <Button onClick={() => navigate(-1)}>
                    Next Module <ArrowRight className="h-4 w-4 ml-1.5" />
                  </Button>
                )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="quiz" className="space-y-6">
            {questions.length === 0 ? (
              <p className="text-muted-foreground text-sm">No quiz questions available.</p>
            ) : (
              <>
                {questions.map((q: any, i: number) => (
                  <div key={q.id} className="bg-card border rounded-lg p-5 space-y-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">Q{i + 1}. {q.question}</span>
                      {q.tier && <Badge className={tierColors[q.tier] || "bg-muted"}>{q.tier}</Badge>}
                    </div>
                    {q.type === "multiple_choice" ? (
                      <div className="space-y-2">
                        {q.options?.map((opt: string, j: number) => (
                          <label key={j} className="flex items-center gap-2 text-sm cursor-pointer">
                            <input
                              type="radio"
                              name={q.id}
                              value={opt}
                              onChange={() => setAnswers((a) => ({ ...a, [q.id]: opt }))}
                              className="accent-primary"
                            />
                            <span className="text-foreground">{opt}</span>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <Textarea
                        placeholder="Type your answer…"
                        value={answers[q.id] || ""}
                        onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                      />
                    )}
                  </div>
                ))}
                <Button onClick={scoreQuiz}>Submit Quiz</Button>
                {quizResults && (
                  <div className="bg-card border rounded-lg p-4 text-sm text-foreground">
                    Score: {quizResults.correct}/{quizResults.total} correct
                  </div>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default StudentLearning;
