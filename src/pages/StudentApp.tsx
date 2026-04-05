import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Send, Mic, MicOff, Volume2, VolumeX, Trophy, Star, Flame, Upload, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

const ASSIGN_URL = "http://localhost:8000";

type Phase = "diagnostic" | "teaching" | "explain_back" | "feedback" | "advance" | "complete";

interface Message {
  role: "ai" | "user";
  text: string;
  chips?: string[];
  streaming?: boolean;
  verdict?: string;
  mastery?: number;
  scores?: Record<string, number>;
  isMCQ?: boolean;
  mcqOptions?: string[];
  mcqCorrect?: string;
  whatTheyGotRight?: string;
  feedbackCard?: "mastered" | "partial" | "not_yet" | "invalid";
}

interface Module {
  id: string;
  title: string;
  description: string;
  learning_objectives: string[];
  order_index: number;
  estimated_minutes: number;
  faithfulness_verdict: string | null;
  mastery?: number;
  completed?: boolean;
}

interface Assessment {
  id: string;
  question: string;
  question_type: string;
  options: string[] | null;
  correct_answer: string;
  difficulty_tier: string;
}

const STRATEGY_LABELS: Record<string, string> = {
  direct: "📖 Direct explanation",
  analogy: "🔗 Analogy approach",
  example: "🔧 Worked example",
  decompose: "🧩 Breaking it down",
  initial: "📖 Direct explanation",
  simplified: "🔗 Analogy approach",
  worked_example: "🔧 Worked example",
};

const PHASE_LABELS: Record<Phase, string> = {
  diagnostic: "Checking foundation",
  teaching: "Learning",
  explain_back: "Your turn",
  feedback: "Feedback",
  advance: "Well done!",
  complete: "Complete!",
};

const PHASE_COLORS: Record<Phase, string> = {
  diagnostic: "bg-gray-100 text-gray-600",
  teaching: "bg-blue-100 text-blue-700",
  explain_back: "bg-green-100 text-green-700",
  feedback: "bg-yellow-100 text-yellow-700",
  advance: "bg-green-100 text-green-700",
  complete: "bg-primary/10 text-primary",
};

export default function StudentApp() {
  const navigate = useNavigate();

  // Core state — ALL cleared on mount
  const [modules, setModules] = useState<Module[]>([]);
  const [selectedModule, setSelectedModule] = useState<Module | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("diagnostic");
  const [attemptNumber, setAttemptNumber] = useState(1);
  const [teachingStrategy, setTeachingStrategy] = useState("direct");
  const [masteryScore, setMasteryScore] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendDown, setBackendDown] = useState(false);
  const [diagnosticQuestions, setDiagnosticQuestions] = useState<Assessment[]>([]);
  const [diagnosticIndex, setDiagnosticIndex] = useState(0);

  // Voice state
  const [voiceOn, setVoiceOn] = useState(false);
  const [micOn, setMicOn] = useState(false);
  const recognitionRef = useRef<any>(null);

  // Upload state
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [courseTitle, setCourseTitle] = useState("");
  const [professorEmail, setProfessorEmail] = useState("");
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "processing" | "done">("idle");
  const [uploadMessage, setUploadMessage] = useState("");

  const chatEndRef = useRef<HTMLDivElement>(null);

  // ── BUG 1 FIX: Clear all state on mount, fetch fresh ────────
  useEffect(() => {
    // Clear everything — no stale state
    setSelectedModule(null);
    setSessionId(null);
    setMessages([]);
    setPhase("diagnostic");
    setAttemptNumber(1);
    setTeachingStrategy("direct");
    setMasteryScore(0);
    setError(null);
    setDiagnosticQuestions([]);
    setDiagnosticIndex(0);

    // Check backend health
    fetch(`${ASSIGN_URL}/health`)
      .then(r => { if (!r.ok) setBackendDown(true); })
      .catch(() => setBackendDown(true));

    // Fetch fresh modules
    const cid = localStorage.getItem("assign_course_id");
    if (cid) fetchModules(cid);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Helpers ──────────────────────────────────────────────────
  function addAIMessage(text: string, chips: string[] = [], extra?: Partial<Message>) {
    setMessages(prev => [...prev, { role: "ai", text, chips, ...extra }]);
    if (voiceOn) speak(text);
  }

  function addUserMessage(text: string) {
    setMessages(prev => [...prev, { role: "user", text }]);
  }

  async function fetchModules(cid: string) {
    try {
      const res = await fetch(`${ASSIGN_URL}/api/courses/${cid}`);
      if (!res.ok) return;
      const data = await res.json();
      setModules(data.modules || []);
    } catch {}
  }

  // ── Upload flow ──────────────────────────────────────────────
  async function handleUpload() {
    if (!uploadFiles.length || !courseTitle) return;
    setUploadStatus("uploading");
    setUploadMessage("Uploading documents...");

    const formData = new FormData();
    uploadFiles.forEach(f => formData.append("file", f));
    formData.append("course_title", courseTitle);
    formData.append("professor_email", professorEmail || "student@demo.com");

    try {
      const res = await fetch(`${ASSIGN_URL}/api/ingest`, { method: "POST", body: formData });
      const { course_id } = await res.json();
      localStorage.setItem("assign_course_id", course_id);
      localStorage.setItem("assign_student_email", professorEmail || "student@demo.com");

      setUploadStatus("processing");
      const statusMessages = ["Parsing documents...", "Generating modules...", "Running quality checks...", "Almost ready..."];
      let msgIdx = 0;

      const poll = setInterval(async () => {
        setUploadMessage(statusMessages[msgIdx % statusMessages.length]);
        msgIdx++;
        try {
          const s = await fetch(`${ASSIGN_URL}/api/ingest/${course_id}/status`).then(r => r.json());
          if (s.status === "ready" || s.module_count > 0) {
            clearInterval(poll);
            setUploadStatus("done");
            setShowUploadDialog(false);
            setUploadStatus("idle");
            await enrollStudent(course_id);
            fetchModules(course_id);
          }
        } catch {}
      }, 3000);
    } catch {
      setUploadStatus("idle");
      setUploadMessage("Upload failed. Try again.");
    }
  }

  async function enrollStudent(cid: string) {
    if (localStorage.getItem("assign_student_id")) return;
    const email = localStorage.getItem("assign_student_email") || "student@demo.com";
    try {
      const res = await fetch(`${ASSIGN_URL}/api/courses/${cid}/enroll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name: email.split("@")[0] }),
      });
      const data = await res.json();
      if (data.student_id) localStorage.setItem("assign_student_id", data.student_id);
    } catch {}
  }

  // ── Module selection → diagnostic ────────────────────────────
  async function handleSelectModule(mod: Module) {
    // Clear all per-module state
    setSelectedModule(mod);
    setMessages([]);
    setSessionId(null);
    setPhase("diagnostic");
    setAttemptNumber(1);
    setTeachingStrategy("direct");
    setError(null);
    setDiagnosticIndex(0);
    setDiagnosticQuestions([]);

    const courseId = localStorage.getItem("assign_course_id") || "";
    const studentId = localStorage.getItem("assign_student_id") || "";

    // Ensure enrolled
    if (!studentId && courseId) await enrollStudent(courseId);
    const sId = localStorage.getItem("assign_student_id") || "";

    // Start session (runs teach node, gets session_id)
    try {
      const res = await fetch(`${ASSIGN_URL}/api/teach/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ module_id: mod.id, student_id: sId }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSessionId(data.session_id);

      // Fetch diagnostic questions
      const aRes = await fetch(`${ASSIGN_URL}/api/courses/${courseId}/modules/${mod.id}/assessments`);
      const assessments: Assessment[] = aRes.ok ? await aRes.json() : [];
      const recallQs = assessments.filter(a => a.difficulty_tier === "recall").slice(0, 1);

      if (recallQs.length > 0) {
        setDiagnosticQuestions(recallQs);
        setDiagnosticIndex(0);
        showDiagnosticQuestion(recallQs[0], mod);
      } else {
        // No diagnostic — go straight to teaching
        addAIMessage(`Let's dive into **${mod.title}**!`, []);
        setPhase("teaching");
        streamTeaching(data.session_id, "direct");
      }
    } catch (e: any) {
      setError(`Failed to start session: ${e.message}`);
    }
  }

  function showDiagnosticQuestion(q: Assessment, mod: Module) {
    addAIMessage(
      `Before we dive into **${mod.title}**, let me check your foundation:\n\n${q.question}`,
      [],
      { isMCQ: true, mcqOptions: q.options || [], mcqCorrect: q.correct_answer }
    );
  }

  // ── BUG 2 FIX: MCQ click handler ─────────────────────────────
  async function handleMCQAnswer(selectedOption: string, selectedText: string) {
    if (isLoading || !sessionId) return;
    setIsLoading(true);
    addUserMessage(`${selectedOption}) ${selectedText}`);

    // Remove chips from last message
    setMessages(prev => prev.map((m, i) =>
      i === prev.length - 1 ? { ...m, chips: [], isMCQ: false, mcqOptions: [] } : m
    ));

    try {
      const response = await fetch(`${ASSIGN_URL}/api/teach/${sessionId}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ explanation: `Selected: ${selectedOption}) ${selectedText}` }),
      });

      if (!response.ok) {
        const err = await response.json();
        setError(err.detail || "Something went wrong. Please try again.");
        return;
      }

      const data = await response.json();

      // BUG 4 FIX: Update mastery immediately
      const mastery = data.mastery_score ?? data.mastery_probability ?? 0;
      setMasteryScore(Math.round(mastery * 100));

      const verdict = data.verdict;
      const feedback = data.feedback_to_student || data.feedback || "";

      addAIMessage(feedback, []);

      // Always transition to teaching after diagnostic
      setTimeout(() => {
        setPhase("teaching");
        streamTeaching(sessionId!, data.next_strategy || "direct");
      }, 1500);

    } catch {
      setError("Network error. Please check your connection.");
    } finally {
      setIsLoading(false);
    }
  }

  // ── BUG 3 FIX: Streaming with auto-transition ────────────────
  async function streamTeaching(sId: string, strategy: string) {
    setPhase("teaching");
    setIsStreaming(true);
    setTeachingStrategy(strategy);

    // Add empty streaming bubble
    setMessages(prev => [...prev, { role: "ai", text: "", streaming: true }]);

    let fullText = "";
    try {
      const res = await fetch(`${ASSIGN_URL}/api/teach/${sId}/explain?strategy=${strategy}`);
      if (!res.ok) throw new Error("Stream failed");

      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const ev = JSON.parse(line.slice(6));
              if (ev.token) {
                fullText += ev.token;
                setMessages(prev => {
                  const last = prev[prev.length - 1];
                  if (last?.streaming) return [...prev.slice(0, -1), { ...last, text: fullText }];
                  return prev;
                });
              }
              if (ev.done) {
                reader.cancel();
                break;
              }
            } catch {}
          }
        }
      }
    } catch {
      setError("Explanation failed to load. Please try again.");
    }

    // Mark streaming done
    setMessages(prev => prev.map((m, i) =>
      i === prev.length - 1 ? { ...m, streaming: false } : m
    ));
    setIsStreaming(false);

    // BUG 3 FIX: Auto-transition to explain_back when streaming completes
    setPhase("explain_back");
    if (voiceOn && fullText) speak(fullText);
  }

  // ── Submit explanation (BUG 4 FIX: mastery update) ──────────
  async function handleSubmitExplanation() {
    const text = inputText.trim();
    if (!text || isLoading || !sessionId || phase !== "explain_back") return;
    setInputText("");
    setIsLoading(true);
    setPhase("feedback");
    addUserMessage(text);

    try {
      const response = await fetch(`${ASSIGN_URL}/api/teach/${sessionId}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ explanation: text }),
      });

      if (!response.ok) {
        const err = await response.json();
        setError(err.detail || "Submission failed.");
        setPhase("explain_back");
        return;
      }

      const data = await response.json();
      const verdict = data.verdict;
      const mastery = data.mastery_score ?? data.mastery_probability ?? 0;
      const feedback = data.feedback_to_student || data.feedback || "Good effort!";
      const newAttempt = data.attempt_number || attemptNumber;

      // BUG 4 FIX: Update mastery bar immediately
      setMasteryScore(Math.round(mastery * 100));
      setModules(prev => prev.map(m =>
        m.id === selectedModule?.id ? { ...m, mastery: Math.round(mastery * 100) } : m
      ));

      // Show feedback with verdict
      // Handle INVALID_INPUT — no attempt counted, stay in explain_back
      if (verdict === "INVALID_INPUT") {
        setMessages(prev => [...prev, {role: "ai", text: feedback, feedbackCard: "invalid", whatTheyGotRight: ""}]);
        setPhase("explain_back");
        setIsLoading(false);
        return;
      }

      const whatRight = data.what_they_got_right || "";
      const feedbackCardType = verdict === "MASTERED" ? "mastered" : verdict === "PARTIAL" ? "partial" : "not_yet";
      setMessages(prev => [...prev, {
        role: "ai",
        text: feedback,
        feedbackCard: feedbackCardType,
        whatTheyGotRight: whatRight,
        verdict,
      }]);

      if (verdict === "MASTERED" || data.advance) {
        setTimeout(() => advanceToNextModule(), 2000);
      } else if (newAttempt >= 5) {
        addAIMessage("Let's move on and come back to this. Your professor has been notified.", []);
        setTimeout(() => advanceToNextModule(), 2000);
      } else {
        // Reteach with next strategy
        const nextStrategy = data.next_strategy || "analogy";
        setAttemptNumber(newAttempt + 1);
        setTeachingStrategy(nextStrategy);
        setTimeout(() => {
          addAIMessage(`Let me try explaining this differently...`, []);
          setTimeout(() => streamTeaching(sessionId!, nextStrategy), 800);
        }, 2000);
      }
    } catch {
      setError("Network error. Please check your connection.");
      setPhase("explain_back");
    } finally {
      setIsLoading(false);
    }
  }

  async function advanceToNextModule() {
    setModules(prev => prev.map(m =>
      m.id === selectedModule?.id ? { ...m, completed: true, mastery: masteryScore } : m
    ));

    const currentIndex = modules.findIndex(m => m.id === selectedModule?.id);
    const nextModule = modules.find((_, i) => i > currentIndex);

    if (nextModule) {
      setPhase("advance");
      addAIMessage(`Moving to: ${nextModule.title}`, []);
      setTimeout(() => handleSelectModule(nextModule), 1500);
    } else {
      setPhase("complete");
      const mastered = modules.filter(m => m.completed).length + 1;
      addAIMessage(`🎉 You've completed all ${modules.length} modules! Amazing work.`, []);
    }
  }

  // ── Voice ─────────────────────────────────────────────────────
  function speak(text: string) {
    if (!voiceOn) return;
    window.speechSynthesis?.cancel();
    const utt = new SpeechSynthesisUtterance(text.replace(/\*\*/g, "").replace(/[✅❌🟡]/g, ""));
    utt.rate = 1.1;
    const voices = window.speechSynthesis?.getVoices() || [];
    const v = voices.find(v => v.name.includes("Google") && v.lang === "en-US") || voices.find(v => v.lang === "en-US");
    if (v) utt.voice = v;
    window.speechSynthesis?.speak(utt);
  }

  function toggleMic() {
    if (micOn) { recognitionRef.current?.stop(); setMicOn(false); return; }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (e: any) => {
      const t = Array.from(e.results).map((r: any) => r[0].transcript).join("");
      setInputText(t);
    };
    rec.onend = () => setMicOn(false);
    rec.start();
    recognitionRef.current = rec;
    setMicOn(true);
  }

  function faithColor(v: string | null) {
    if (v === "FAITHFUL") return "bg-green-500";
    if (v === "PARTIAL") return "bg-yellow-400";
    if (v === "UNFAITHFUL") return "bg-red-500";
    return "bg-gray-300";
  }

  const courseId = localStorage.getItem("assign_course_id") || "";

  return (
    <div className="flex h-screen bg-background font-sans">
      {/* Sidebar */}
      <aside className="w-44 shrink-0 border-r border-border flex flex-col py-4 px-3 gap-3">
        <button onClick={() => navigate("/")} className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>

        <div>
          <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-0.5">Course</p>
          <p className="text-sm font-semibold text-foreground truncate">
            {modules.length > 0 ? "My Course" : "No course loaded"}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto">
          <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">Topics</p>
          {modules.length === 0 ? (
            <button
              onClick={() => setShowUploadDialog(true)}
              className="w-full text-left text-xs text-primary font-medium py-2 px-2 rounded-lg border border-primary/30 hover:bg-primary/5 flex items-center gap-1.5"
            >
              <Upload className="w-3 h-3" /> Upload Materials
            </button>
          ) : (
            <div className="flex flex-col gap-0.5">
              {modules.map(mod => (
                <button
                  key={mod.id}
                  onClick={() => handleSelectModule(mod)}
                  className={`w-full text-left px-2 py-1.5 rounded-lg text-xs transition-colors flex items-start gap-1.5 ${
                    selectedModule?.id === mod.id
                      ? "bg-primary/10 text-primary font-medium"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${
                    mod.completed ? "bg-green-500" :
                    mod.mastery && mod.mastery > 0 ? "bg-yellow-400" :
                    faithColor(mod.faithfulness_verdict)
                  }`} />
                  <span className="leading-tight">{mod.title}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="flex justify-between items-center mb-1">
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Mastery</p>
            <p className="text-[10px] text-muted-foreground">{masteryScore}%</p>
          </div>
          <Progress value={masteryScore} className="h-1.5" />
        </div>

        <div className="flex flex-col gap-1">
          <button onClick={() => navigate("/student/progress")} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground py-1">
            <Star className="w-3.5 h-3.5" /> My Progress
          </button>
          <button onClick={() => navigate("/student/leaderboard")} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground py-1">
            <Trophy className="w-3.5 h-3.5" /> Leaderboard
          </button>
        </div>

        <div className="rounded-lg bg-orange-50 border border-orange-100 p-2">
          <div className="flex items-center gap-1 text-orange-500 text-xs font-medium mb-0.5">
            <Flame className="w-3 h-3" /> Keep it up!
          </div>
          <p className="text-[10px] text-orange-400">Stay consistent to master this course.</p>
        </div>
      </aside>

      {/* Main chat */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Backend down banner */}
        {backendDown && (
          <div className="bg-red-100 border-b border-red-300 px-4 py-2 text-sm text-red-800 text-center">
            ⚠ Backend not available. Make sure the server is running at localhost:8000.
          </div>
        )}

        {/* Header */}
        <header className="h-12 border-b border-border flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold">A</div>
            <div>
              <p className="text-sm font-medium leading-none">Assign Tutor</p>
              <p className="text-[11px] text-muted-foreground">{selectedModule?.title || "Select a topic"}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Phase indicator */}
            {selectedModule && (
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${PHASE_COLORS[phase]}`}>
                {PHASE_LABELS[phase]}
                {phase === "teaching" && ` — ${attemptNumber}/5`}
              </span>
            )}
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Star className="w-3.5 h-3.5 text-yellow-400" /> {masteryScore}%
            </span>
            <button onClick={() => setVoiceOn(v => !v)} className="text-muted-foreground hover:text-foreground">
              {voiceOn ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>
          </div>
        </header>

        {/* Error banner */}
        {error && (
          <div className="mx-4 mt-2 bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm text-red-700 flex justify-between items-center">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 ml-2">✕</button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
          {messages.length === 0 && !selectedModule && (
            <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center py-20">
              <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                <Upload className="w-6 h-6 text-primary" />
              </div>
              <div>
                <p className="font-semibold text-foreground mb-1">Upload your course materials</p>
                <p className="text-sm text-muted-foreground mb-4">Upload PDFs, slide decks, or notes and Assign will build a personalized learning path.</p>
                <Button onClick={() => setShowUploadDialog(true)} className="bg-primary text-white hover:bg-primary/90">
                  <Upload className="w-4 h-4 mr-2" /> Upload Materials
                </Button>
              </div>
            </div>
          )}

          {messages.length === 0 && selectedModule && (
            <div className="flex items-center justify-center py-10">
              <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex flex-col gap-1.5 ${msg.role === "user" ? "items-end" : "items-start"}`}>
              {/* Strategy tag for teaching phase */}
              {msg.role === "ai" && phase === "teaching" && i === messages.length - 1 && teachingStrategy && (
                <span className="text-[10px] text-muted-foreground ml-1">{STRATEGY_LABELS[teachingStrategy] || teachingStrategy}</span>
              )}

              <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.role === "ai"
                  ? "bg-card border border-border text-foreground"
                  : "bg-primary text-white"
              }`}>
                {/* Feedback card — uses verdictConfig, all text from API */}
              {msg.feedbackCard ? (() => {
                const verdictConfig: Record<string, {bg: string; border: string; titleColor: string; title: string}> = {
                  mastered: {bg: "#DCFCE7", border: "#16A34A", titleColor: "#15803D", title: "✓ Understood!"},
                  partial:  {bg: "#FEF9C3", border: "#D97706", titleColor: "#92400E", title: "Almost there"},
                  not_yet:  {bg: "#FEF2F2", border: "#DC2626", titleColor: "#991B1B", title: "Let's try again"},
                  invalid:  {bg: "#FEF9C3", border: "#D97706", titleColor: "#92400E", title: "Please try again"},
                };
                const cfg = verdictConfig[msg.feedbackCard] || verdictConfig.not_yet;
                return (
                  <div style={{background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 8, padding: 12}}>
                    <div style={{color: cfg.titleColor, fontWeight: 600, marginBottom: 4}}>{cfg.title}</div>
                    {msg.whatTheyGotRight && msg.feedbackCard !== "mastered" && (
                      <div style={{color: cfg.titleColor, opacity: 0.85, fontSize: 13, marginBottom: 6}}>✓ {msg.whatTheyGotRight}</div>
                    )}
                    {msg.feedbackCard === "mastered" && msg.whatTheyGotRight && (
                      <div style={{color: cfg.titleColor, fontSize: 14}}>{msg.whatTheyGotRight}</div>
                    )}
                    {msg.text && msg.feedbackCard !== "mastered" && (
                      <div style={{color: cfg.titleColor, fontSize: 14, marginTop: 4}}>{msg.text}</div>
                    )}
                  </div>
                );
              })() : msg.text.split("**").map((part, pi) =>
                pi % 2 === 1 ? <strong key={pi}>{part}</strong> : <span key={pi}>{part}</span>
              )}
                {msg.streaming && <span className="inline-block w-1.5 h-4 bg-primary/60 ml-1 animate-pulse rounded" />}
              </div>

              {/* MCQ options — BUG 2 FIX */}
              {msg.isMCQ && msg.mcqOptions && msg.mcqOptions.length > 0 && (
                <div className="flex flex-wrap gap-2 max-w-[80%] mt-1">
                  {msg.mcqOptions.map((opt, oi) => {
                    const letter = String.fromCharCode(65 + oi);
                    const text = opt.replace(/^[A-D]\)\s*/, "");
                    return (
                      <button
                        key={oi}
                        onClick={() => handleMCQAnswer(letter, text)}
                        disabled={isLoading}
                        className="text-xs px-3 py-2 rounded-xl border border-border bg-card hover:border-primary hover:bg-primary/5 text-foreground transition-colors disabled:opacity-50 flex items-center gap-1.5"
                      >
                        <span className="font-medium text-primary">{letter}</span>
                        <span>{text}</span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Chips */}
              {msg.chips && msg.chips.length > 0 && (
                <div className="flex flex-wrap gap-1.5 max-w-[80%]">
                  {msg.chips.map(chip => (
                    <button
                      key={chip}
                      disabled={isLoading}
                      className="text-xs px-3 py-1.5 rounded-full border border-primary/30 text-primary bg-primary/5 hover:bg-primary/10 transition-colors disabled:opacity-50"
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>

        {/* Input bar */}
        <footer className="border-t border-border px-4 py-3 flex items-center gap-2 shrink-0">
          {((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition) && (
            <button
              onClick={toggleMic}
              disabled={phase !== "explain_back"}
              className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors shrink-0 ${
                micOn ? "bg-red-500 text-white animate-pulse" : "bg-muted text-muted-foreground hover:text-foreground disabled:opacity-40"
              }`}
            >
              {micOn ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>
          )}
          <input
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSubmitExplanation()}
            placeholder={
              phase === "teaching" ? "Waiting for explanation to complete..." :
              phase === "explain_back" ? "Explain it back in your own words..." :
              phase === "diagnostic" ? "Answer using the options above..." :
              "Select a topic to start learning..."
            }
            disabled={phase !== "explain_back" || isLoading}
            className="flex-1 bg-muted rounded-full px-4 py-2 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-40 disabled:cursor-not-allowed"
          />
          <button
            onClick={handleSubmitExplanation}
            disabled={!inputText.trim() || phase !== "explain_back" || isLoading}
            className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-white disabled:opacity-40 hover:bg-primary/90 transition-colors shrink-0"
          >
            {isLoading ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </footer>

        <div className="px-4 py-1.5 text-[10px] text-muted-foreground flex gap-3 border-t border-border/50">
          <span>Phase: {phase}</span>
          <span>·</span>
          <span>Attempt: {attemptNumber}/5</span>
          <span>·</span>
          <span>Mastery: {masteryScore}%</span>
        </div>
      </main>

      {/* Upload Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Upload Course Materials</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Course Materials</label>
              <div className="border-2 border-dashed border-border rounded-lg p-4 text-center">
                <input
                  type="file"
                  multiple
                  accept=".pdf,.docx,.pptx"
                  onChange={e => setUploadFiles(Array.from(e.target.files || []))}
                  className="hidden"
                  id="file-upload"
                />
                <label htmlFor="file-upload" className="cursor-pointer">
                  <Upload className="w-6 h-6 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">Click to upload PDF, DOCX, PPTX</p>
                </label>
                {uploadFiles.length > 0 && (
                  <div className="mt-3 space-y-1">
                    {uploadFiles.map((f, i) => (
                      <div key={i} className="flex items-center justify-between text-xs bg-muted rounded px-2 py-1">
                        <span className="truncate">{f.name}</span>
                        <button onClick={() => setUploadFiles(prev => prev.filter((_, j) => j !== i))}>
                          <X className="w-3 h-3 text-muted-foreground" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">Course Title</label>
              <Input value={courseTitle} onChange={e => setCourseTitle(e.target.value)} placeholder="e.g. Machine Learning Fundamentals" />
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">Your Email</label>
              <Input value={professorEmail} onChange={e => setProfessorEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            {uploadStatus !== "idle" && (
              <div className="bg-primary/5 border border-primary/20 rounded-lg p-3 text-sm text-primary flex items-center gap-2">
                <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin shrink-0" />
                {uploadMessage}
              </div>
            )}
            <Button
              onClick={handleUpload}
              disabled={!uploadFiles.length || !courseTitle || uploadStatus !== "idle"}
              className="w-full bg-primary text-white hover:bg-primary/90"
            >
              {uploadStatus === "idle" ? "Generate Course" : "Processing..."}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
