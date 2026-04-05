import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Send, Mic, MicOff, Volume2, VolumeX, Trophy, Star, Flame, Upload, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

const ASSIGN_URL = "http://localhost:8000";

interface Message {
  role: "ai" | "user";
  text: string;
  chips?: string[];
  streaming?: boolean;
  mastery?: number;
  feedback?: string;
  scores?: Record<string, number>;
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

const STRATEGIES = ["initial", "simplified", "analogy", "worked_example"];

export default function StudentApp() {
  const navigate = useNavigate();
  const [modules, setModules] = useState<Module[]>([]);
  const [selectedModule, setSelectedModule] = useState<Module | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [strategyIndex, setStrategyIndex] = useState(0);
  const [isStreaming, setIsStreaming] = useState(false);
  const [overallMastery, setOverallMastery] = useState(0);
  const [voiceOn, setVoiceOn] = useState(true);
  const [micOn, setMicOn] = useState(false);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [courseTitle, setCourseTitle] = useState("");
  const [professorEmail, setProfessorEmail] = useState("");
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "processing" | "done">("idle");
  const [uploadMessage, setUploadMessage] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  const courseId = localStorage.getItem("assign_course_id") || "";
  const studentId = localStorage.getItem("assign_student_id") || "";
  const studentEmail = localStorage.getItem("assign_student_email") || "student@demo.com";

  // Load modules on mount
  useEffect(() => {
    if (courseId) loadModules();
  }, [courseId]);

  // Scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadModules() {
    try {
      const res = await fetch(`${ASSIGN_URL}/api/courses/${courseId}`);
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
      setUploadMessage("Generating course structure...");

      // Poll status
      const messages = ["Parsing documents...", "Generating modules...", "Running quality checks...", "Almost ready..."];
      let msgIdx = 0;
      const poll = setInterval(async () => {
        setUploadMessage(messages[msgIdx % messages.length]);
        msgIdx++;
        try {
          const s = await fetch(`${ASSIGN_URL}/api/ingest/${course_id}/status`).then(r => r.json());
          if (s.status === "ready") {
            clearInterval(poll);
            setUploadStatus("done");
            setShowUploadDialog(false);
            setUploadStatus("idle");
            // Enroll student
            await enrollStudent(course_id);
            loadModulesForCourse(course_id);
          }
        } catch {}
      }, 3000);
    } catch {
      setUploadStatus("idle");
      setUploadMessage("Upload failed. Try again.");
    }
  }

  async function loadModulesForCourse(cid: string) {
    const res = await fetch(`${ASSIGN_URL}/api/courses/${cid}`);
    const data = await res.json();
    setModules(data.modules || []);
  }

  async function enrollStudent(cid: string) {
    if (localStorage.getItem("assign_student_id")) return;
    const email = localStorage.getItem("assign_student_email") || "student@demo.com";
    const res = await fetch(`${ASSIGN_URL}/api/courses/${cid}/enroll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, name: email.split("@")[0] }),
    });
    const data = await res.json();
    if (data.student_id) localStorage.setItem("assign_student_id", data.student_id);
  }

  // ── Module selection → prereq check → teach ─────────────────
  async function handleSelectModule(mod: Module) {
    setSelectedModule(mod);
    setMessages([]);
    setStrategyIndex(0);
    setSessionId(null);

    // Ensure enrolled
    if (!studentId && courseId) await enrollStudent(courseId);

    // Prerequisite check
    try {
      const assessments: Assessment[] = await fetch(
        `${ASSIGN_URL}/api/courses/${courseId}/modules/${mod.id}/assessments`
      ).then(r => r.json());
      const recallQs = assessments.filter(a => a.difficulty_tier === "recall").slice(0, 2);

      if (recallQs.length > 0) {
        addAIMessage(
          `Before we dive into **${mod.title}**, let me check your foundation with ${recallQs.length} quick question${recallQs.length > 1 ? "s" : ""}:`,
          []
        );
        await runPrereqQuiz(recallQs, mod);
      } else {
        startTeaching(mod, "initial");
      }
    } catch {
      startTeaching(mod, "initial");
    }
  }

  async function runPrereqQuiz(questions: Assessment[], mod: Module) {
    let correct = 0;
    for (const q of questions) {
      const chips = q.options || ["True", "False"];
      const answer = await askQuizQuestion(q.question, chips);
      if (answer === q.correct_answer || q.correct_answer.startsWith(answer.charAt(0))) correct++;
    }
    if (correct >= 1) {
      addAIMessage("Great foundation! Let's build on that. 🎯", []);
      setTimeout(() => startTeaching(mod, "initial"), 600);
    } else {
      addAIMessage("Let's start from the fundamentals — I'll make this clear. 💡", []);
      setTimeout(() => startTeaching(mod, "simplified"), 600);
    }
  }

  function askQuizQuestion(question: string, chips: string[]): Promise<string> {
    return new Promise(resolve => {
      addAIMessage(question, chips, (answer) => resolve(answer));
    });
  }

  function addAIMessage(text: string, chips: string[] = [], onChip?: (c: string) => void) {
    const msg: Message & { onChip?: (c: string) => void } = {
      role: "ai", text, chips,
    };
    setMessages(prev => [...prev, msg]);
    if (voiceOn) speak(text);
  }

  // ── Teaching loop ────────────────────────────────────────────
  async function startTeaching(mod: Module, strategy: string) {
    const sId = localStorage.getItem("assign_student_id") || "";
    if (!sId || !mod.id) return;

    try {
      const { session_id } = await fetch(`${ASSIGN_URL}/api/teach/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ module_id: mod.id, student_id: sId }),
      }).then(r => r.json());
      setSessionId(session_id);
      await streamTeaching(session_id, strategy);
    } catch (e) {
      addAIMessage("Having trouble connecting. Please try again.", []);
    }
  }

  async function streamTeaching(sId: string, strategy: string) {
    setIsStreaming(true);
    // Add empty streaming bubble
    setMessages(prev => [...prev, { role: "ai", text: "", streaming: true }]);

    let fullText = "";
    try {
      const res = await fetch(`${ASSIGN_URL}/api/teach/${sId}/explain?strategy=${strategy}`);
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
              if (ev.done) break;
            } catch {}
          }
        }
      }
    } catch {}

    // Mark streaming done, add chips
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last?.streaming) {
        return [...prev.slice(0, -1), {
          ...last, streaming: false,
          chips: ["I understand ✓", "Give me a hint 💡", "Show an example 📝", "I don't know 🤷"]
        }];
      }
      return prev;
    });
    setIsStreaming(false);
    if (voiceOn && fullText) speak(fullText);
  }

  async function handleChip(chip: string) {
    // Remove chips from last message
    setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, chips: [] } : m));
    setMessages(prev => [...prev, { role: "user", text: chip }]);

    if (chip.startsWith("I understand")) {
      // Ask for a real explanation instead of auto-submitting
      setMessages(prev => prev.map((m, i) => i === prev.length - 1 ? { ...m, chips: [] } : m));
      setMessages(prev => [...prev, { role: "user", text: chip }]);
      setMessages(prev => [...prev, { role: "ai", text: "Great! Now explain it in your own words so I can confirm you've got it. What is the core concept here and why does it matter?", chips: [] }]);
      return; // Do NOT auto-submit — wait for real explanation
      await submitExplanation("I understand this concept well and can explain it.");
    } else if (chip.startsWith("Give me a hint")) {
      setStrategyIndex(1);
      if (selectedModule) startTeaching(selectedModule, "simplified");
    } else if (chip.startsWith("Show an example")) {
      setStrategyIndex(2);
      if (selectedModule) startTeaching(selectedModule, "worked_example");
    } else if (chip.startsWith("I don't know")) {
      setStrategyIndex(3);
      if (selectedModule) startTeaching(selectedModule, "analogy");
    }
  }

  async function submitExplanation(text: string) {
    if (!sessionId) return;
    try {
      const result = await fetch(`${ASSIGN_URL}/api/teach/${sessionId}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ explanation: text }),
      }).then(r => r.json());

      const mastery = Math.round((result.mastery_probability || 0) * 100);
      const overall = Math.round((result.overall_score || 0) * 100);
      const feedback = result.feedback || "Keep it up!";

      setMessages(prev => [...prev, {
        role: "ai",
        text: feedback + (result.grade_letter ? "\n\nGrade: " + result.grade_letter + " — " + (result.learning_verdict || "") : "") + (result.correct_points?.length ? "\n✓ " + result.correct_points.join("\n✓ ") : "") + (result.incorrect_points?.length ? "\n✗ " + result.incorrect_points.join("\n✗ ") : "") + (result.missing_points?.length ? "\n⚠ Missing: " + result.missing_points.join("\n⚠ Missing: ") : ""),
        mastery,
        scores: result.scores,
      }]);

      if (result.advance) {
        setModules(prev => prev.map(m =>
          m.id === selectedModule?.id ? { ...m, mastery: 100, completed: true } : m
        ));
        setOverallMastery(prev => Math.min(100, prev + Math.round(100 / modules.length)));
        setTimeout(() => addAIMessage("✓ Module complete! Great work. 🎉 Select the next module when you're ready.", []), 500);
      } else if (overall < 30) {
        const nextStrategy = STRATEGIES[Math.min(strategyIndex + 1, STRATEGIES.length - 1)];
        setStrategyIndex(s => Math.min(s + 1, STRATEGIES.length - 1));
        if (strategyIndex >= 3) {
          addAIMessage("This is a tough concept — I've flagged this for your instructor. You can move to the next module and come back to this. 📌", []);
        } else {
          setTimeout(() => {
            addAIMessage("Let me try a different approach... 🔄", []);
            setTimeout(() => selectedModule && startTeaching(selectedModule, nextStrategy), 600);
          }, 500);
        }
      } else {
        setTimeout(() => addAIMessage("Good effort! Want to try explaining again or move on?",
          ["Try again 🔄", "Next module →"]), 500);
      }
    } catch {
      addAIMessage("Couldn't submit. Try again.", []);
    }
  }

  async function handleSend() {
    const text = inputText.trim();
    if (!text || isStreaming) return;
    setInputText("");
    setMessages(prev => [...prev, { role: "user", text }]);

    if (!sessionId && selectedModule) {
      await startTeaching(selectedModule, STRATEGIES[strategyIndex]);
    } else {
      await submitExplanation(text);
    }
  }

  // ── Voice ────────────────────────────────────────────────────
  function speak(text: string) {
    if (!voiceOn) return;
    window.speechSynthesis?.cancel();
    const utt = new SpeechSynthesisUtterance(text.replace(/\*\*/g, ""));
    utt.rate = 1.1;
    const voices = window.speechSynthesis?.getVoices() || [];
    const v = voices.find(v => v.name.includes("Google") && v.lang === "en-US") || voices.find(v => v.lang === "en-US");
    if (v) utt.voice = v;
    window.speechSynthesis?.speak(utt);
  }

  function toggleMic() {
    if (micOn) {
      recognitionRef.current?.stop();
      setMicOn(false);
      return;
    }
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
    rec.onend = () => {
      setMicOn(false);
      if (inputText.trim()) handleSend();
    };
    rec.start();
    recognitionRef.current = rec;
    setMicOn(true);
  }

  // ── Faithfulness color ────────────────────────────────────────
  function faithColor(v: string | null) {
    if (v === "FAITHFUL") return "bg-green-500";
    if (v === "PARTIAL") return "bg-yellow-400";
    if (v === "UNFAITHFUL") return "bg-red-500";
    return "bg-gray-300";
  }

  // ── Render ────────────────────────────────────────────────────
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
                  <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${faithColor(mod.faithfulness_verdict)}`} />
                  <span className="leading-tight">{mod.title}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="flex justify-between items-center mb-1">
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Mastery</p>
            <p className="text-[10px] text-muted-foreground">{overallMastery}%</p>
          </div>
          <Progress value={overallMastery} className="h-1.5" />
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
            <Flame className="w-3 h-3" /> 4 day streak!
          </div>
          <p className="text-[10px] text-orange-400">Come back tomorrow to keep it going.</p>
        </div>
      </aside>

      {/* Main chat */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-12 border-b border-border flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold">A</div>
            <div>
              <p className="text-sm font-medium leading-none">Assign Tutor</p>
              <p className="text-[11px] text-muted-foreground">{selectedModule?.title || "Select a topic"}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Star className="w-3.5 h-3.5 text-yellow-400" /> {overallMastery}%
            </span>
            <button onClick={() => setVoiceOn(v => !v)} className="text-muted-foreground hover:text-foreground">
              {voiceOn ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
          {messages.length === 0 && !selectedModule && (
            <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center">
              <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                <Upload className="w-6 h-6 text-primary" />
              </div>
              <div>
                <p className="font-semibold text-foreground mb-1">Upload your course materials</p>
                <p className="text-sm text-muted-foreground mb-4">Upload PDFs, slide decks, or notes and Assign will build you a personalized learning path.</p>
                <Button onClick={() => setShowUploadDialog(true)} className="bg-primary text-white hover:bg-primary/90">
                  <Upload className="w-4 h-4 mr-2" /> Upload Materials
                </Button>
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex flex-col gap-1 ${msg.role === "user" ? "items-end" : "items-start"}`}>
              <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.role === "ai"
                  ? "bg-card border border-border text-foreground"
                  : "bg-primary text-white"
              }`}>
                {msg.text}
                {msg.streaming && <span className="inline-block w-1.5 h-4 bg-primary/60 ml-1 animate-pulse rounded" />}
              </div>

              {/* Mastery feedback */}
              {msg.mastery !== undefined && (
                <div className="max-w-[75%] bg-muted rounded-xl px-4 py-2 text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Mastery</span>
                    <span className={`font-bold ${msg.mastery >= 70 ? "text-green-600" : msg.mastery >= 40 ? "text-yellow-600" : "text-red-600"}`}>
                      {msg.mastery}%
                    </span>
                  </div>
                  <div className={`h-1.5 rounded-full w-full bg-muted-foreground/20`}>
                    <div
                      className={`h-full rounded-full transition-all ${msg.mastery >= 70 ? "bg-green-500" : msg.mastery >= 40 ? "bg-yellow-400" : "bg-red-500"}`}
                      style={{ width: `${msg.mastery}%` }}
                    />
                  </div>
                  {msg.scores && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {Object.entries(msg.scores).map(([k, v]) => (
                        <span key={k} className="bg-background border border-border rounded px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {k.replace(/_/g, " ")}: {Math.round((v as number) * 100)}%
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Chips */}
              {msg.chips && msg.chips.length > 0 && (
                <div className="flex flex-wrap gap-1.5 max-w-[75%]">
                  {msg.chips.map(chip => (
                    <button
                      key={chip}
                      onClick={() => handleChip(chip)}
                      disabled={isStreaming}
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
          {(window as any).SpeechRecognition || (window as any).webkitSpeechRecognition ? (
            <button
              onClick={toggleMic}
              className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors shrink-0 ${
                micOn ? "bg-red-500 text-white animate-pulse" : "bg-muted text-muted-foreground hover:text-foreground"
              }`}
            >
              {micOn ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>
          ) : null}
          <input
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder={selectedModule ? "Explain it back in your own words..." : "Select a topic to start learning..."}
            disabled={!selectedModule || isStreaming}
            className="flex-1 bg-muted rounded-full px-4 py-2 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!inputText.trim() || isStreaming || !selectedModule}
            className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-white disabled:opacity-40 hover:bg-primary/90 transition-colors shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </footer>

        {/* Session stats footer */}
        <div className="px-4 py-1.5 text-[10px] text-muted-foreground flex gap-3 border-t border-border/50">
          <span>Session: 0 min</span>
          <span>·</span>
          <span>Modules touched: {messages.filter(m => m.role === "user").length}</span>
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
