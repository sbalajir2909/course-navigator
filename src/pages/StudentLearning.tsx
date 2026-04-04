import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowRight, Loader2, AlertTriangle } from "lucide-react";

const tierColors: Record<string, string> = {
  recall: "bg-indigo-100 text-indigo-700",
  application: "bg-amber-100 text-amber-700",
  synthesis: "bg-emerald-100 text-emerald-700",
};

async function ensureStudentId(courseId: string): Promise<string> {
  const existing = localStorage.getItem("assign_student_id");
  if (existing) return existing;

  const data = await api.enroll(courseId, {
    email: "student@demo.com",
    name: "Demo Student",
  });
  localStorage.setItem("assign_student_id", data.student_id);
  localStorage.setItem("assign_student_name", "Demo Student");
  localStorage.setItem("assign_course_id", courseId);
  return data.student_id;
}

const StudentLearning = () => {
  const { courseId, moduleId } = useParams<{ courseId: string; moduleId: string }>();
  const navigate = useNavigate();

  // Learn state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [explanation, setExplanation] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [response, setResponse] = useState("");
  const [feedback, setFeedback] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const [failCount, setFailCount] = useState(0);
  const [prerequisiteHint, setPrerequisiteHint] = useState<string | null>(null);
  const [moduleTitle, setModuleTitle] = useState<string>("");
  const explanationRef = useRef<HTMLDivElement>(null);

  // Quiz state
  const [questions, setQuestions] = useState<any[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [quizResults, setQuizResults] = useState<any>(null);

  // Store courseId in localStorage whenever we have it
  useEffect(() => {
    if (courseId) {
      localStorage.setItem("assign_course_id", courseId);
    }
  }, [courseId]);

  // Fetch module title from course details
  useEffect(() => {
    if (!courseId || !moduleId) return;
    api.courseDetail(courseId).then((course) => {
      const modules = course.modules || [];
      const mod = modules.find((m: any) => m.id === moduleId);
      if (mod?.title) {
        setModuleTitle(mod.title);
      }
    }).catch(() => {});
  }, [courseId, moduleId]);

  useEffect(() => {
    if (!moduleId || !courseId) return;
    let cancelled = false;

    (async () => {
      const studentId = await ensureStudentId(courseId);
      if (cancelled) return;

      const data = await api.teachStart(moduleId, studentId);
      if (cancelled) return;

      setSessionId(data.session_id);
      setStreaming(true);

      // Use fetch + streaming reader for proper SSE parsing
      try {
        const resp = await fetch(`http://localhost:8000/api/teach/${data.session_id}/explain`);
        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          if (cancelled) break;
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const payload = line.slice(6);
              if (payload === '[DONE]') {
                setStreaming(false);
                return;
              }
              try {
                const event = JSON.parse(payload);
                if (event.token) {
                  setExplanation((prev) => prev + event.token);
                }
                if (event.done) {
                  setStreaming(false);
                  return;
                }
              } catch {}
            }
          }
        }
        setStreaming(false);
      } catch {
        setStreaming(false);
      }
    })();

    return () => { cancelled = true; };
  }, [moduleId, courseId]);

  useEffect(() => {
    if (explanationRef.current) {
      explanationRef.current.scrollTop = explanationRef.current.scrollHeight;
    }
  }, [explanation]);

  // Check for prerequisite recommendation when student fails twice
  useEffect(() => {
    if (failCount >= 2 && courseId) {
      // Look up prerequisite from learning path data in localStorage
      const pathData = localStorage.getItem(`assign_learning_path_${courseId}`);
      if (pathData) {
        try {
          const path = JSON.parse(pathData);
          const currentIdx = path.findIndex((m: any) => m.id === moduleId);
          if (currentIdx > 0) {
            const prereq = path[currentIdx - 1];
            if (prereq && !prereq.skip) {
              setPrerequisiteHint(prereq.title);
            }
          }
        } catch {}
      }
    }
  }, [failCount, courseId, moduleId]);

  const handleSubmitResponse = async () => {
    if (!sessionId || !response.trim()) return;
    setSubmitting(true);
    try {
      const data = await api.teachSubmit(sessionId, response);
      setFeedback(data);
      if (data.mastery < 50) {
        setFailCount((c) => c + 1);
      }
    } catch {}
    setSubmitting(false);
  };

  const handleRetry = () => {
    setFeedback(null);
    setResponse("");
  };

  const loadQuiz = async () => {
    if (!moduleId || !courseId) return;
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
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(`/course/${courseId}`)}>
            ← Back to Course
          </Button>
          <h1 className="text-2xl font-bold text-foreground">{moduleTitle || "Loading module…"}</h1>
        </div>

        {/* Prerequisite recommendation banner */}
        {prerequisiteHint && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800">
                This topic seems challenging. We recommend completing <strong>{prerequisiteHint}</strong> first before continuing.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2 border-amber-300 text-amber-700 hover:bg-amber-100"
                onClick={() => navigate(`/course/${courseId}/learn`)}
              >
                Go to Learning Path
              </Button>
            </div>
          </div>
        )}

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

            {/* Post-stream prompt */}
            {!streaming && explanation && !feedback && (
              <div className="bg-primary/5 border border-primary/20 rounded-lg p-4">
                <p className="text-sm font-medium text-primary">
                  Now explain this concept in your own words to demonstrate your understanding.
                </p>
              </div>
            )}

            {/* Student response */}
            {!feedback ? (
              <div className="space-y-3">
                <Textarea
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                  placeholder="Type your explanation here…"
                  className="min-h-[120px]"
                />
                <Button onClick={handleSubmitResponse} disabled={submitting || !response.trim() || streaming}>
                  {submitting ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Submitting…</> : "Submit My Explanation"}
                </Button>
              </div>
            ) : (
              <div className="bg-card border rounded-lg p-6 space-y-4">
                <h3 className="font-semibold text-foreground">Feedback</h3>
                <p className="text-sm text-muted-foreground">{feedback.feedback}</p>

                {/* Score breakdown */}
                {feedback.scores && (
                  <div className="space-y-2">
                    {Object.entries(feedback.scores).map(([key, val]) => (
                      <div key={key} className="flex justify-between text-xs text-muted-foreground">
                        <span className="capitalize">{key.replace(/_/g, ' ')}</span>
                        <span className="font-medium">{String(val)}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Mastery progress bar */}
                <div className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-foreground">Mastery Score</span>
                    <span className="font-semibold text-primary">{feedback.mastery}%</span>
                  </div>
                  <Progress value={feedback.mastery} className="h-2.5" />
                </div>

                <div className="flex gap-2">
                  {feedback.advance ? (
                    <Button onClick={() => navigate(`/course/${courseId}/learn`)}>
                      Next Module <ArrowRight className="h-4 w-4 ml-1.5" />
                    </Button>
                  ) : (
                    <Button variant="outline" onClick={handleRetry}>
                      Try Again
                    </Button>
                  )}
                </div>
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
