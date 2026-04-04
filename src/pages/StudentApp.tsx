import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Send, Menu, X, Trophy, Star, Flame, Mic, MicOff, Volume2, VolumeX } from "lucide-react";
import { assign, streamExplanation } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface Message {
  role: "ai" | "user";
  text: string;
  chips?: string[];
}

interface CourseModule {
  module_id: string;
  title: string;
  progress?: number;
}

const CHIPS = [
  "I understand \u2713",
  "Give me a hint \ud83d\udca1",
  "Show an example \ud83d\udcdd",
  "I don't know \ud83e\udd37",
];

const progressColor = (p: number) =>
  p >= 60 ? "bg-primary" : p >= 30 ? "bg-warning" : "bg-destructive";

const StudentApp = () => {
  const navigate = useNavigate();

  // Course / module state
  const [courseId, setCourseId] = useState<string | null>(() => localStorage.getItem("studentCourseId"));
  const [modules, setModules] = useState<CourseModule[]>([]);
  const [activeModule, setActiveModule] = useState<CourseModule | null>(null);
  const [courseName, setCourseName] = useState("My Course");

  // Session state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mastery, setMastery] = useState(0);

  // Chat state
  const [chatsByModule, setChatsByModule] = useState<Record<string, Message[]>>({});
  const [input, setInput] = useState("");
  const [stats, setStats] = useState({ minutes: 0, questions: 0, concepts: 0 });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  // Join dialog
  const [joinDialogOpen, setJoinDialogOpen] = useState(false);
  const [joinCourseId, setJoinCourseId] = useState("");

  // Voice state
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const messages = activeModule ? (chatsByModule[activeModule.module_id] || []) : [];

  // Timer
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setStats((s) => ({ ...s, minutes: s.minutes + 1 }));
    }, 60000);
    return () => clearInterval(timerRef.current);
  }, []);

  // Scroll to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streaming]);

  // Load course modules
  useEffect(() => {
    if (!courseId) return;
    assign.getCourse(courseId).then((course) => {
      setCourseName(course.title || course.name || "My Course");
    }).catch(() => {});
    assign.getCourseGraph(courseId).then((graph) => {
      const mods: CourseModule[] = (graph.nodes || []).map((n: { id: string; data?: { label?: string } }) => ({
        module_id: n.id,
        title: n.data?.label || n.id,
        progress: 0,
      }));
      setModules(mods);
      if (mods.length > 0 && !activeModule) {
        setActiveModule(mods[0]);
      }
    }).catch(() => {});
  }, [courseId]);

  // Start session when module changes
  useEffect(() => {
    if (!activeModule) return;
    const studentId = localStorage.getItem("studentId") || "demo-student";
    setSessionId(null);
    setMastery(0);
    assign.startSession(activeModule.module_id, studentId).then((res) => {
      setSessionId(res.session_id);
      // Stream initial explanation
      setStreaming(true);
      let fullText = "";
      streamExplanation(
        res.session_id,
        "initial",
        (token) => {
          fullText += token;
          setChatsByModule((prev) => {
            const msgs = prev[activeModule.module_id] || [];
            const last = msgs[msgs.length - 1];
            if (last && last.role === "ai" && !last.chips) {
              return { ...prev, [activeModule.module_id]: [...msgs.slice(0, -1), { ...last, text: fullText }] };
            }
            return { ...prev, [activeModule.module_id]: [...msgs, { role: "ai", text: fullText }] };
          });
        },
        () => {
          setStreaming(false);
          setChatsByModule((prev) => {
            const msgs = prev[activeModule.module_id] || [];
            const last = msgs[msgs.length - 1];
            if (last && last.role === "ai") {
              return { ...prev, [activeModule.module_id]: [...msgs.slice(0, -1), { ...last, chips: CHIPS }] };
            }
            return prev;
          });
          if (ttsEnabled && fullText) speak(fullText);
        }
      ).catch(() => {
        setStreaming(false);
        addMessage(activeModule.module_id, {
          role: "ai",
          text: `Let's learn about **${activeModule.title}**. What do you already know about this topic?`,
          chips: CHIPS,
        });
      });
    }).catch(() => {
      addMessage(activeModule.module_id, {
        role: "ai",
        text: `Let's learn about **${activeModule.title}**. What do you already know about this topic?`,
        chips: CHIPS,
      });
    });
  }, [activeModule?.module_id]);

  const addMessage = useCallback((moduleId: string, msg: Message) => {
    setChatsByModule((prev) => ({
      ...prev,
      [moduleId]: [...(prev[moduleId] || []), msg],
    }));
  }, []);

  // Voice: TTS
  const speak = (text: string) => {
    if (!ttsEnabled || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.replace(/[*#_`]/g, ""));
    utterance.rate = 1.0;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
  };

  // Voice: STT
  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }
    const SpeechRecognition = (window as unknown as { SpeechRecognition?: typeof window.SpeechRecognition; webkitSpeechRecognition?: typeof window.SpeechRecognition }).SpeechRecognition || (window as unknown as { webkitSpeechRecognition?: typeof window.SpeechRecognition }).webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) setInput(transcript);
    };
    recognition.onend = () => setIsListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  };

  const handleChip = (chip: string) => {
    if (!activeModule || !sessionId) return;
    addMessage(activeModule.module_id, { role: "user", text: chip });
    setStats((s) => ({ ...s, questions: s.questions + 1 }));

    if (chip.startsWith("I understand")) {
      // Submit understanding
      assign.submitExplanation(sessionId, "I understand this concept.").then((res) => {
        const score = res.mastery ?? res.score ?? mastery + 15;
        setMastery(Math.min(100, score));
        addMessage(activeModule.module_id, {
          role: "ai",
          text: `Great! Your mastery is now at ${Math.min(100, score)}%. ${score >= 80 ? "You're doing amazing!" : "Keep going!"}`,
          chips: score >= 80 ? [] : CHIPS,
        });
      }).catch(() => {
        setMastery((m) => Math.min(100, m + 10));
        addMessage(activeModule.module_id, { role: "ai", text: "Nice work! Let's keep going.", chips: CHIPS });
      });
    } else if (chip.startsWith("Give me a hint")) {
      setStreaming(true);
      let fullText = "";
      streamExplanation(sessionId, "simplified", (token) => {
        fullText += token;
        setChatsByModule((prev) => {
          const msgs = prev[activeModule.module_id] || [];
          const last = msgs[msgs.length - 1];
          if (last && last.role === "ai" && !last.chips) {
            return { ...prev, [activeModule.module_id]: [...msgs.slice(0, -1), { ...last, text: fullText }] };
          }
          return { ...prev, [activeModule.module_id]: [...msgs, { role: "ai", text: fullText }] };
        });
      }, () => {
        setStreaming(false);
        setChatsByModule((prev) => {
          const msgs = prev[activeModule.module_id] || [];
          const last = msgs[msgs.length - 1];
          if (last && last.role === "ai") {
            return { ...prev, [activeModule.module_id]: [...msgs.slice(0, -1), { ...last, chips: CHIPS }] };
          }
          return prev;
        });
        if (ttsEnabled && fullText) speak(fullText);
      }).catch(() => {
        setStreaming(false);
        addMessage(activeModule.module_id, { role: "ai", text: "Here's a simpler way to think about it...", chips: CHIPS });
      });
    } else if (chip.startsWith("Show an example")) {
      setStreaming(true);
      let fullText = "";
      streamExplanation(sessionId, "worked_example", (token) => {
        fullText += token;
        setChatsByModule((prev) => {
          const msgs = prev[activeModule.module_id] || [];
          const last = msgs[msgs.length - 1];
          if (last && last.role === "ai" && !last.chips) {
            return { ...prev, [activeModule.module_id]: [...msgs.slice(0, -1), { ...last, text: fullText }] };
          }
          return { ...prev, [activeModule.module_id]: [...msgs, { role: "ai", text: fullText }] };
        });
      }, () => {
        setStreaming(false);
        setChatsByModule((prev) => {
          const msgs = prev[activeModule.module_id] || [];
          const last = msgs[msgs.length - 1];
          if (last && last.role === "ai") {
            return { ...prev, [activeModule.module_id]: [...msgs.slice(0, -1), { ...last, chips: CHIPS }] };
          }
          return prev;
        });
        if (ttsEnabled && fullText) speak(fullText);
      }).catch(() => {
        setStreaming(false);
        addMessage(activeModule.module_id, { role: "ai", text: "Let me walk through an example...", chips: CHIPS });
      });
    } else {
      // "I don't know"
      setStreaming(true);
      let fullText = "";
      streamExplanation(sessionId, "analogy", (token) => {
        fullText += token;
        setChatsByModule((prev) => {
          const msgs = prev[activeModule.module_id] || [];
          const last = msgs[msgs.length - 1];
          if (last && last.role === "ai" && !last.chips) {
            return { ...prev, [activeModule.module_id]: [...msgs.slice(0, -1), { ...last, text: fullText }] };
          }
          return { ...prev, [activeModule.module_id]: [...msgs, { role: "ai", text: fullText }] };
        });
      }, () => {
        setStreaming(false);
        setChatsByModule((prev) => {
          const msgs = prev[activeModule.module_id] || [];
          const last = msgs[msgs.length - 1];
          if (last && last.role === "ai") {
            return { ...prev, [activeModule.module_id]: [...msgs.slice(0, -1), { ...last, chips: CHIPS }] };
          }
          return prev;
        });
        if (ttsEnabled && fullText) speak(fullText);
      }).catch(() => {
        setStreaming(false);
        addMessage(activeModule.module_id, { role: "ai", text: "No worries! Let me explain this differently...", chips: CHIPS });
      });
    }
  };

  const handleSend = () => {
    if (!input.trim() || !activeModule || !sessionId) return;
    const text = input.trim();
    setInput("");
    addMessage(activeModule.module_id, { role: "user", text });
    setStats((s) => ({ ...s, questions: s.questions + 1 }));

    assign.submitExplanation(sessionId, text).then((res) => {
      const score = res.mastery ?? res.score ?? mastery;
      setMastery(Math.min(100, score));
      const aiText = res.feedback || res.message || "Good thinking — keep going!";
      addMessage(activeModule.module_id, { role: "ai", text: aiText, chips: CHIPS });
      if (ttsEnabled) speak(aiText);
    }).catch(() => {
      addMessage(activeModule.module_id, { role: "ai", text: "Good thinking — keep going!", chips: CHIPS });
    });
  };

  const handleJoinCourse = () => {
    if (!joinCourseId.trim()) return;
    setCourseId(joinCourseId.trim());
    localStorage.setItem("studentCourseId", joinCourseId.trim());
    setJoinDialogOpen(false);
    setJoinCourseId("");
  };

  const switchModule = (mod: CourseModule) => {
    setActiveModule(mod);
    setSidebarOpen(false);
    setStats((s) => ({ ...s, concepts: Math.min(modules.length, s.concepts + 1) }));
  };

  const Sidebar = () => (
    <div className="flex flex-col h-full">
      <div className="px-4 pt-5 pb-3 border-b border-border">
        <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Course</p>
        <p className="font-serif text-foreground text-lg mt-1">{courseName}</p>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-3">
        {modules.length === 0 && !courseId ? (
          <div className="px-3 py-4 text-center">
            <p className="text-sm text-muted-foreground mb-3">No course joined yet</p>
            <button
              onClick={() => setJoinDialogOpen(true)}
              className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              Join a Course
            </button>
          </div>
        ) : (
          <>
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider px-2 mb-2">Topics</p>
            {modules.map((mod) => (
              <button
                key={mod.module_id}
                onClick={() => switchModule(mod)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  activeModule?.module_id === mod.module_id
                    ? "bg-primary/10 text-primary border-l-2 border-primary font-medium"
                    : "text-foreground hover:bg-muted"
                }`}
              >
                {mod.title}
              </button>
            ))}

            {/* Mastery progress */}
            <div className="mt-6 px-2">
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-3">Mastery</p>
              <div className="mb-3">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-foreground">{activeModule?.title || "—"}</span>
                  <span className="text-muted-foreground">{mastery}%</span>
                </div>
                <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${progressColor(mastery)}`}
                    style={{ width: `${mastery}%` }}
                  />
                </div>
              </div>
            </div>
          </>
        )}

        {/* Quick nav links */}
        <div className="px-2 mt-4 pt-4 border-t border-border space-y-1">
          <button
            onClick={() => navigate("/student/progress")}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <Star className="w-4 h-4" /> My Progress
          </button>
          <button
            onClick={() => navigate("/student/leaderboard")}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <Trophy className="w-4 h-4" /> Leaderboard
          </button>
        </div>

        {/* Streak widget */}
        <div className="mx-2 mt-3 mb-2 p-3 rounded-lg bg-orange-50 border border-orange-100">
          <div className="flex items-center gap-2">
            <Flame className="w-4 h-4 text-orange-500" />
            <span className="text-xs font-medium text-orange-700">4 day streak!</span>
          </div>
          <p className="text-xs text-orange-600 mt-0.5">Come back tomorrow to keep it going.</p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex flex-col md:flex-row">
      {/* Mobile header */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border bg-card">
        <button onClick={() => navigate("/roles")} className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <span className="font-serif text-foreground">{courseName}</span>
        <button onClick={() => setSidebarOpen(!sidebarOpen)} className="text-muted-foreground">
          {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile sidebar dropdown */}
      {sidebarOpen && (
        <div className="md:hidden border-b border-border bg-card">
          <Sidebar />
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden md:block w-[220px] border-r border-border bg-card flex-shrink-0 h-screen sticky top-0">
        <button
          onClick={() => navigate("/roles")}
          className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground hover:text-foreground border-b border-border w-full"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <Sidebar />
      </aside>

      {/* Chat area */}
      <main className="flex-1 flex flex-col h-screen md:h-screen">
        {/* Chat header */}
        <div className="px-5 py-4 border-b border-border bg-card flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-bold text-sm">
            A
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-foreground">Assign Tutor</p>
            <p className="text-xs text-muted-foreground">{activeModule?.title || "Select a topic"}</p>
          </div>
          {/* Mastery badge */}
          <div className="flex items-center gap-1.5">
            <Star className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-primary">{mastery}%</span>
          </div>
          {/* TTS toggle */}
          <button
            onClick={() => { setTtsEnabled(!ttsEnabled); if (isSpeaking) window.speechSynthesis.cancel(); }}
            className={`p-2 rounded-lg transition-colors ${ttsEnabled ? "text-primary bg-primary/10" : "text-muted-foreground hover:bg-muted"}`}
            title={ttsEnabled ? "Mute voice" : "Enable voice"}
          >
            {ttsEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className="max-w-[85%] md:max-w-[70%]">
                <div
                  className={`px-4 py-3 rounded-xl text-sm leading-relaxed ${
                    msg.role === "ai"
                      ? "bg-muted text-foreground rounded-bl-sm"
                      : "bg-foreground text-background rounded-br-sm"
                  }`}
                >
                  {msg.text}
                </div>
                {msg.role === "ai" && msg.chips && msg.chips.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {msg.chips.map((chip) => (
                      <button
                        key={chip}
                        onClick={() => handleChip(chip)}
                        disabled={streaming}
                        className="px-3 py-1.5 text-xs rounded-full border border-primary/30 text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {streaming && (
            <div className="flex justify-start">
              <div className="px-4 py-3 rounded-xl bg-muted text-foreground text-sm rounded-bl-sm">
                <span className="animate-pulse">...</span>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input */}
        <div className="px-4 md:px-8 py-3 border-t border-border bg-card">
          <div className="flex gap-2">
            <button
              onClick={toggleListening}
              className={`px-3 py-2.5 rounded-lg border transition-colors ${
                isListening
                  ? "bg-destructive text-destructive-foreground border-destructive"
                  : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
              title={isListening ? "Stop listening" : "Start voice input"}
            >
              {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Type your answer…"
              className="flex-1 px-4 py-2.5 rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
            <button
              onClick={handleSend}
              disabled={streaming || !input.trim()}
              className="px-4 py-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Session stats */}
        <div className="px-4 md:px-8 py-2 border-t border-border bg-muted/50 flex gap-4 text-xs text-muted-foreground">
          <span>Session: {stats.minutes} min</span>
          <span>·</span>
          <span>Questions asked: {stats.questions}</span>
          <span>·</span>
          <span>Concepts touched: {stats.concepts}</span>
        </div>
      </main>

      {/* Join Course Dialog */}
      <Dialog open={joinDialogOpen} onOpenChange={setJoinDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-serif">Join a Course</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <label className="block text-sm font-medium text-foreground">Course ID</label>
            <input
              type="text"
              value={joinCourseId}
              onChange={(e) => setJoinCourseId(e.target.value)}
              placeholder="Enter course ID or join link..."
              className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
            <button
              onClick={handleJoinCourse}
              className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              Join
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default StudentApp;
