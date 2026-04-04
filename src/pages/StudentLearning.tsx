import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ArrowRight, Loader2, AlertTriangle, Send } from "lucide-react";

/* ---------- Types ---------- */

interface ChatMessage {
  id: string;
  role: "ai" | "student";
  content: string;
  streaming?: boolean;
}

type Phase = "loading" | "prereq" | "teaching" | "respond" | "feedback" | "give_up";

/* ---------- Constants ---------- */

const RETRY_STRATEGIES = ["simplified", "analogy", "worked_example"] as const;
const MAX_RETRIES = 3;

/* ---------- Helpers ---------- */

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

let msgCounter = 0;
function nextId() {
  return `msg-${++msgCounter}`;
}

function masteryBarColor(pct: number): string {
  if (pct < 40) return "bg-red-500";
  if (pct <= 70) return "bg-yellow-500";
  return "bg-emerald-500";
}

function formatDimensionLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ---------- Component ---------- */

const StudentLearning = () => {
  const { courseId, moduleId } = useParams<{ courseId: string; moduleId: string }>();
  const navigate = useNavigate();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [phase, setPhase] = useState<Phase>("loading");
  const [moduleTitle, setModuleTitle] = useState("");
  const [response, setResponse] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [failCount, setFailCount] = useState(0);
  const [retryCount, setRetryCount] = useState(0);
  const [prerequisiteHint, setPrerequisiteHint] = useState<string | null>(null);
  const [useSimplified, setUseSimplified] = useState(false);
  const [masteryPct, setMasteryPct] = useState<number | null>(null);

  // Prereq quiz state
  const [prereqQuestions, setPrereqQuestions] = useState<any[]>([]);
  const [prereqAnswers, setPrereqAnswers] = useState<Record<string, string>>({});
  const [prereqDone, setPrereqDone] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, prereqQuestions, prereqDone]);

  // Store courseId
  useEffect(() => {
    if (courseId) localStorage.setItem("assign_course_id", courseId);
  }, [courseId]);

  // Append helper
  const addMessage = (role: "ai" | "student", content: string, streaming = false): string => {
    const id = nextId();
    setMessages((prev) => [...prev, { id, role, content, streaming }]);
    return id;
  };

  const updateMessage = (id: string, updater: (msg: ChatMessage) => ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? updater(m) : m)));
  };

  // Phase 1: Load module title + prereq questions
  useEffect(() => {
    if (!courseId || !moduleId) return;

    (async () => {
      // Fetch module title
      try {
        const course = await api.courseDetail(courseId);
        const modules = course.modules || [];
        const mod = modules.find((m: any) => m.id === moduleId);
        if (mod?.title) setModuleTitle(mod.title);
      } catch {}

      // Fetch assessments for prereq check
      try {
        const data = await api.moduleAssessments(courseId, moduleId);
        const questions = data.questions || [];
        // Get recall-tier multiple choice questions for prereq
        const recallMC = questions.filter(
          (q: any) => q.tier === "recall" && q.type === "multiple_choice"
        );
        const prereqs = recallMC.slice(0, 2);

        if (prereqs.length >= 2) {
          // Show prereq check
          addMessage(
            "ai",
            `Before we dive in, let me check your foundation. **${
              moduleTitle || "This module"
            }** builds on a few key concepts. Answer these 2 questions:`
          );
          setPrereqQuestions(prereqs);
          setPhase("prereq");
        } else {
          // Skip prereq, go straight to teaching
          setPhase("teaching");
          startTeaching(false);
        }
      } catch {
        // Can't load assessments, skip prereq
        setPhase("teaching");
        startTeaching(false);
      }
    })();
  }, [courseId, moduleId]);

  // Update the prereq intro message once moduleTitle is available
  useEffect(() => {
    if (moduleTitle && phase === "prereq" && messages.length === 1) {
      updateMessage(messages[0].id, (m) => ({
        ...m,
        content: `Before we dive in, let me check your foundation. **${moduleTitle}** builds on a few key concepts. Answer these 2 questions:`,
      }));
    }
  }, [moduleTitle]);

  const handlePrereqAnswer = (questionId: string, answer: string) => {
    setPrereqAnswers((prev) => ({ ...prev, [questionId]: answer }));
  };

  const submitPrereqCheck = () => {
    let correct = 0;
    prereqQuestions.forEach((q: any) => {
      if (prereqAnswers[q.id] === q.correct_answer) correct++;
    });

    // Show student's answers as a message
    const answerSummary = prereqQuestions
      .map((q: any, i: number) => `Q${i + 1}: ${prereqAnswers[q.id] || "(no answer)"}`)
      .join("\n");
    addMessage("student", answerSummary);

    setPrereqDone(true);

    if (correct >= 1) {
      addMessage("ai", "Great foundation! Let's build on that.");
      setTimeout(() => {
        setPhase("teaching");
        startTeaching(false);
      }, 800);
    } else {
      addMessage(
        "ai",
        "Let's make sure the fundamentals are solid first. I'll explain this in a simpler way."
      );
      setUseSimplified(true);
      setTimeout(() => {
        setPhase("teaching");
        startTeaching(true);
      }, 800);
    }
  };

  // Start the teaching stream
  const startTeaching = async (simplified: boolean, strategy?: string) => {
    if (!moduleId || !courseId) return;

    const studentId = await ensureStudentId(courseId);
    const data = await api.teachStart(moduleId, studentId);
    setSessionId(data.session_id);

    const streamMsgId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: streamMsgId, role: "ai", content: "", streaming: true },
    ]);

    // Determine query param for strategy
    const strategyParam = strategy || (simplified ? "simplified" : "");
    const qs = strategyParam ? `?strategy=${strategyParam}` : "";

    try {
      const resp = await fetch(
        `http://localhost:8000/api/teach/${data.session_id}/explain${qs}`
      );
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const payload = line.slice(6);
            if (payload === "[DONE]") {
              updateMessage(streamMsgId, (m) => ({ ...m, streaming: false }));
              setPhase("respond");
              addMessage(
                "ai",
                "Now explain this concept in your own words to demonstrate your understanding."
              );
              return;
            }
            try {
              const event = JSON.parse(payload);
              if (event.token) {
                updateMessage(streamMsgId, (m) => ({
                  ...m,
                  content: m.content + event.token,
                }));
              }
              if (event.done) {
                updateMessage(streamMsgId, (m) => ({ ...m, streaming: false }));
                setPhase("respond");
                addMessage(
                  "ai",
                  "Now explain this concept in your own words to demonstrate your understanding."
                );
                return;
              }
            } catch {}
          }
        }
      }
      updateMessage(streamMsgId, (m) => ({ ...m, streaming: false }));
      setPhase("respond");
      addMessage(
        "ai",
        "Now explain this concept in your own words to demonstrate your understanding."
      );
    } catch {
      updateMessage(streamMsgId, (m) => ({
        ...m,
        content: m.content || "Failed to load explanation.",
        streaming: false,
      }));
      setPhase("respond");
    }
  };

  // Adaptive re-teach: trigger a new session with a different strategy
  const triggerAdaptiveReteach = async (currentRetry: number) => {
    if (!moduleId || !courseId) return;

    if (currentRetry >= MAX_RETRIES) {
      // Give up after max retries
      addMessage(
        "ai",
        "No worries! This is a tough concept. I've flagged this for your professor. Let's move on."
      );
      setPhase("give_up");
      return;
    }

    const strategyIndex = Math.min(currentRetry, RETRY_STRATEGIES.length - 1);
    const strategy = RETRY_STRATEGIES[strategyIndex];

    addMessage("ai", "Let me try a different approach...");

    // Brief pause for UX
    await new Promise((r) => setTimeout(r, 600));

    setPhase("teaching");
    await startTeaching(false, strategy);
  };

  // Submit student explanation
  const handleSubmitResponse = async () => {
    if (!sessionId || !response.trim()) return;
    setSubmitting(true);
    addMessage("student", response);
    const text = response;
    setResponse("");

    try {
      const data = await api.teachSubmit(sessionId, text);

      const masteryPctValue = Math.round(data.mastery_probability * 100);
      const overallPctValue = Math.round(data.overall_score * 100);
      setMasteryPct(masteryPctValue);

      // Build feedback message with prominent feedback text
      let feedbackText = data.feedback || "";

      // Add dimension score pills
      if (data.scores) {
        const pills = Object.entries(data.scores)
          .map(([k, v]) => `${formatDimensionLabel(k)}: ${Math.round((v as number) * 100)}%`)
          .join(" | ");
        feedbackText += `\n\n${pills}`;
      }

      feedbackText += `\n\n**Overall Score: ${overallPctValue}%**`;
      feedbackText += `\n**Mastery: ${masteryPctValue}%**`;

      addMessage("ai", feedbackText);

      if (data.advance) {
        addMessage("ai", "Module complete! Move to next module.");
        setPhase("feedback");
      } else {
        const newFailCount = failCount + 1;
        setFailCount(newFailCount);

        // Detect low score: adaptive re-teach
        if (data.overall_score < 0.3) {
          const newRetryCount = retryCount + 1;
          setRetryCount(newRetryCount);
          setSubmitting(false);
          await triggerAdaptiveReteach(newRetryCount);
          return;
        } else {
          addMessage("ai", "Try explaining again — you can refine your understanding.");
          setPhase("respond");
        }
      }
    } catch {
      addMessage("ai", "Something went wrong. Please try again.");
      setPhase("respond");
    }
    setSubmitting(false);
  };

  // Check for prerequisite recommendation when student fails twice
  useEffect(() => {
    if (failCount >= 2 && courseId) {
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmitResponse();
    }
  };

  const allPrereqAnswered = prereqQuestions.every((q: any) => prereqAnswers[q.id]);

  return (
    <div className="flex flex-col h-screen bg-secondary/30">
      {/* Header */}
      <div className="border-b bg-card px-4 py-3 flex items-center gap-3 shrink-0">
        <Button variant="ghost" size="sm" onClick={() => navigate(`/course/${courseId}/learn`)}>
          ← Back
        </Button>
        <h1 className="text-lg font-bold text-foreground truncate">
          {moduleTitle || "Loading module…"}
        </h1>
      </div>

      {/* Mastery progress bar */}
      {masteryPct !== null && (
        <div className="px-4 py-2 bg-card border-b shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Mastery Progress</span>
              <span>{masteryPct}%</span>
            </div>
            <div className="w-full h-2 bg-secondary rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${masteryBarColor(masteryPct)}`}
                style={{ width: `${masteryPct}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Prerequisite warning banner */}
      {prerequisiteHint && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-3 flex items-center gap-3 shrink-0">
          <AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0" />
          <p className="text-sm text-amber-800">
            Struggling? Try completing <strong>{prerequisiteHint}</strong> first.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto border-amber-300 text-amber-700 hover:bg-amber-100"
            onClick={() => navigate(`/course/${courseId}/learn`)}
          >
            Go to Learning Path
          </Button>
        </div>
      )}

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "student" ? "justify-end" : "justify-start"}`}
          >
            {msg.role === "ai" && (
              <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-sm font-bold mr-3 shrink-0 mt-0.5">
                A
              </div>
            )}
            <div
              className={`max-w-[70%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === "ai"
                  ? "bg-white border border-border text-foreground shadow-sm"
                  : "bg-indigo-600 text-white"
              }`}
            >
              {msg.content
                ? msg.content.split(/(\*\*.*?\*\*)/).map((part, i) =>
                    part.startsWith("**") && part.endsWith("**") ? (
                      <strong key={i}>{part.slice(2, -2)}</strong>
                    ) : (
                      <span key={i}>{part}</span>
                    )
                  )
                : msg.streaming && (
                    <span className="text-muted-foreground animate-pulse">Thinking…</span>
                  )}
              {msg.streaming && msg.content && (
                <span className="inline-block w-1.5 h-4 bg-indigo-500 animate-pulse ml-0.5 align-text-bottom" />
              )}
            </div>
          </div>
        ))}

        {/* Prereq quiz inline (shown as part of chat) */}
        {phase === "prereq" && !prereqDone && prereqQuestions.length > 0 && (
          <div className="flex justify-start">
            <div className="w-8 h-8 mr-3 shrink-0" />
            <div className="max-w-[70%] space-y-4">
              {prereqQuestions.map((q: any, qi: number) => (
                <div key={q.id} className="bg-white border rounded-xl p-4 shadow-sm space-y-2">
                  <p className="text-sm font-medium text-foreground">
                    Q{qi + 1}. {q.question}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {q.options?.map((opt: string, oi: number) => {
                      const letter = String.fromCharCode(65 + oi);
                      const selected = prereqAnswers[q.id] === opt;
                      return (
                        <button
                          key={oi}
                          onClick={() => handlePrereqAnswer(q.id, opt)}
                          className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                            selected
                              ? "bg-indigo-600 text-white border-indigo-600"
                              : "bg-white text-foreground border-border hover:border-indigo-400"
                          }`}
                        >
                          {letter}. {opt}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
              <Button
                onClick={submitPrereqCheck}
                disabled={!allPrereqAnswered}
                size="sm"
                className="mt-2"
              >
                Check Answers
              </Button>
            </div>
          </div>
        )}

        {/* Module complete action */}
        {phase === "feedback" && (
          <div className="flex justify-center">
            <Button
              onClick={() => navigate(`/course/${courseId}/learn`)}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              Next Module <ArrowRight className="h-4 w-4 ml-1.5" />
            </Button>
          </div>
        )}

        {/* Give up / max retries reached */}
        {phase === "give_up" && (
          <div className="flex justify-center">
            <Button
              onClick={() => navigate(`/course/${courseId}/learn`)}
              className="bg-indigo-600 hover:bg-indigo-700"
            >
              Next Module <ArrowRight className="h-4 w-4 ml-1.5" />
            </Button>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Bottom input bar */}
      {(phase === "respond" || phase === "teaching") && (
        <div className="border-t bg-card px-4 py-3 shrink-0">
          <div className="max-w-3xl mx-auto flex items-end gap-3">
            <Textarea
              ref={textareaRef}
              value={response}
              onChange={(e) => setResponse(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Explain it back in your own words…"
              className="min-h-[44px] max-h-[120px] resize-none flex-1"
              rows={1}
              disabled={phase === "teaching" || submitting}
            />
            <Button
              onClick={handleSubmitResponse}
              disabled={submitting || !response.trim() || phase === "teaching"}
              size="icon"
              className="h-11 w-11 shrink-0"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default StudentLearning;
