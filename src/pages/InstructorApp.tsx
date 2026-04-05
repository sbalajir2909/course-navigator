import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Settings, Upload, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { assign } from "@/lib/api";

const TABS = ["Overview", "Students", "Concepts", "Alerts"] as const;
type Tab = (typeof TABS)[number];

type Risk = "High" | "Medium" | "On track";

interface KPIData {
  label: string;
  value: string;
  delta: string;
  deltaColor: string;
}

interface ConfusionData {
  name: string;
  pct: number;
  color: string;
}

interface ActionData {
  icon: string;
  text: string;
}

interface Student {
  name: string;
  sessions: number;
  stuck: string;
  engagement: number;
  risk: Risk;
  lastSession: string;
  mostRevisited: string;
  longestStuck: string;
  suggested: string;
}

interface ConceptData {
  name: string;
  confusion: number;
  students: number;
  tag: "Needs reteach" | "Monitor" | "On track";
  bars: number[];
}

interface AlertItem {
  id: number;
  color: string;
  borderColor: string;
  icon: string;
  time: string;
  text: string;
  action: "message" | "lecture" | "dismiss";
  studentName?: string;
}

// Fallback demo data
const DEMO_KPI: KPIData[] = [
  { label: "Engaged this week", value: "38", delta: "\u2191 4", deltaColor: "text-primary" },
  { label: "Avg sessions/student", value: "4.2", delta: "\u2191 0.8", deltaColor: "text-primary" },
  { label: "At-risk students", value: "7", delta: "\u2191 3", deltaColor: "text-destructive" },
  { label: "Top confused concept", value: "Recursion", delta: "", deltaColor: "text-warning" },
];

const DEMO_CONFUSION: ConfusionData[] = [
  { name: "Recursion", pct: 62, color: "bg-destructive" },
  { name: "Base cases", pct: 48, color: "bg-warning" },
  { name: "Call stack", pct: 41, color: "bg-warning" },
  { name: "Big-O", pct: 22, color: "bg-primary" },
  { name: "Sorting", pct: 14, color: "bg-primary" },
];

const DEMO_ACTIONS: ActionData[] = [
  { icon: "\ud83d\udd34", text: "Reteach recursion Thursday \u2014 62% returned to it 3+ times this week" },
  { icon: "\ud83d\udfe1", text: "5 students haven't opened a session since Week 4" },
  { icon: "\ud83d\udfe2", text: "Big-O comprehension strong \u2014 safe to move faster next week" },
];

const DEMO_STUDENTS: Student[] = [
  { name: "Priya M.", sessions: 7, stuck: "Recursion, call stack", engagement: 4, risk: "Medium", lastSession: "Today", mostRevisited: "Recursion", longestStuck: "18 min", suggested: "Review base case exercises" },
  { name: "Jordan K.", sessions: 0, stuck: "\u2014", engagement: 0, risk: "High", lastSession: "14 days ago", mostRevisited: "\u2014", longestStuck: "\u2014", suggested: "Reach out directly" },
  { name: "Ananya R.", sessions: 9, stuck: "None", engagement: 5, risk: "On track", lastSession: "Today", mostRevisited: "Big-O", longestStuck: "4 min", suggested: "Challenge with advanced topics" },
  { name: "Marcus L.", sessions: 3, stuck: "Base cases", engagement: 2, risk: "Medium", lastSession: "Yesterday", mostRevisited: "Base cases", longestStuck: "22 min", suggested: "Assign targeted practice" },
  { name: "Lena B.", sessions: 6, stuck: "Recursion depth", engagement: 4, risk: "On track", lastSession: "Today", mostRevisited: "Recursion", longestStuck: "8 min", suggested: "No action needed" },
  { name: "Devon T.", sessions: 1, stuck: "DP, graphs", engagement: 1, risk: "High", lastSession: "5 days ago", mostRevisited: "DP", longestStuck: "40 min", suggested: "Schedule one-on-one" },
];

const DEMO_CONCEPTS: ConceptData[] = [
  { name: "Recursion", confusion: 62, students: 26, tag: "Needs reteach", bars: [80, 60, 90, 70, 95] },
  { name: "Base cases", confusion: 48, students: 20, tag: "Monitor", bars: [40, 55, 50, 60, 48] },
  { name: "Call stack", confusion: 41, students: 17, tag: "Monitor", bars: [30, 45, 50, 40, 41] },
  { name: "Big-O", confusion: 22, students: 9, tag: "On track", bars: [20, 25, 18, 22, 20] },
  { name: "Sorting", confusion: 14, students: 6, tag: "On track", bars: [10, 15, 12, 14, 10] },
  { name: "DP", confusion: 55, students: 23, tag: "Needs reteach", bars: [50, 60, 55, 65, 55] },
];

const DEMO_ALERTS: AlertItem[] = [
  { id: 1, color: "text-destructive", borderColor: "border-l-destructive", icon: "\ud83d\udd34", time: "Today 9:14am", text: "Jordan K. has not engaged in 14 days", action: "message", studentName: "Jordan K." },
  { id: 2, color: "text-warning", borderColor: "border-l-warning", icon: "\ud83d\udfe1", time: "Today 8:50am", text: "Recursion confusion spike: +18% in 48 hours", action: "lecture" },
  { id: 3, color: "text-destructive", borderColor: "border-l-destructive", icon: "\ud83d\udd34", time: "Yesterday", text: "Devon T. spent 40 min on one question without resolving it", action: "message", studentName: "Devon T." },
  { id: 4, color: "text-primary", borderColor: "border-l-primary", icon: "\ud83d\udfe2", time: "Yesterday", text: "Ananya R. completed all 5 topics ahead of schedule", action: "dismiss" },
  { id: 5, color: "text-warning", borderColor: "border-l-warning", icon: "\ud83d\udfe1", time: "2 days ago", text: "DP module has the lowest completion rate this cohort: 31%", action: "lecture" },
];

// ─── COMPONENTS ───
const riskBadge = (risk: Risk) => {
  const cls =
    risk === "High"
      ? "bg-destructive/10 text-destructive"
      : risk === "Medium"
      ? "bg-warning/10 text-warning"
      : "bg-primary/10 text-primary";
  return <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${cls}`}>{risk}</span>;
};

const engagementDots = (n: number) => (
  <div className="flex gap-1">
    {[1, 2, 3, 4, 5].map((i) => (
      <span
        key={i}
        className={`w-2.5 h-2.5 rounded-full ${i <= n ? "bg-primary" : "bg-border"}`}
      />
    ))}
  </div>
);

const tagColor = (tag: string) =>
  tag === "Needs reteach"
    ? "bg-destructive/10 text-destructive"
    : tag === "Monitor"
    ? "bg-warning/10 text-warning"
    : "bg-primary/10 text-primary";

const InstructorApp = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [filter, setFilter] = useState<"All" | "High" | "On track">("All");
  const [expandedStudent, setExpandedStudent] = useState<string | null>(null);
  const [alerts, setAlerts] = useState(DEMO_ALERTS);
  const [messageModal, setMessageModal] = useState<{ open: boolean; student: string }>({ open: false, student: "" });
  const [messageText, setMessageText] = useState("");
  const [toast, setToast] = useState("");
  const [animatedBars, setAnimatedBars] = useState(false);

  // Upload dialog state
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploading, setUploading] = useState(false);

  // Data state (try real API, fallback to demo)
  const [kpis, setKpis] = useState<KPIData[]>(DEMO_KPI);
  const [confusion, setConfusion] = useState<ConfusionData[]>(DEMO_CONFUSION);
  const [actions, setActions] = useState<ActionData[]>(DEMO_ACTIONS);
  const [students, setStudents] = useState<Student[]>(DEMO_STUDENTS);
  const [concepts, setConcepts] = useState<ConceptData[]>(DEMO_CONCEPTS);

  const courseId = localStorage.getItem("instructorCourseId");

  const showToast = (text: string) => {
    setToast(text);
    setTimeout(() => setToast(""), 3000);
  };

  // Load real data if courseId exists
  useEffect(() => {
    if (!courseId) return;
    assign.getDashboardStats(courseId).then((data) => {
      if (data.kpis) setKpis(data.kpis);
    }).catch(() => {});
    assign.getHeatmap(courseId).then((data) => {
      if (data.modules) {
        const confusionData: ConfusionData[] = (data.modules as string[]).map((name: string, i: number) => {
          const avgScore = data.scores?.[i]?.reduce((a: number, b: number) => a + b, 0) / (data.scores?.[i]?.length || 1) || 0;
          const pct = Math.round(100 - avgScore);
          return {
            name,
            pct,
            color: pct >= 50 ? "bg-destructive" : pct >= 30 ? "bg-warning" : "bg-primary",
          };
        });
        setConfusion(confusionData);
      }
    }).catch(() => {});
    assign.getInterventions(courseId).then((data) => {
      if (data.interventions) {
        setActions(data.interventions.map((item: { priority: string; message: string }) => ({
          icon: item.priority === "high" ? "\ud83d\udd34" : item.priority === "medium" ? "\ud83d\udfe1" : "\ud83d\udfe2",
          text: item.message,
        })));
      }
    }).catch(() => {});
  }, [courseId]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    if (tab === "Overview" || tab === "Concepts") {
      setAnimatedBars(false);
      setTimeout(() => setAnimatedBars(true), 50);
    }
  };

  // Trigger animation on mount
  useEffect(() => {
    setTimeout(() => setAnimatedBars(true), 100);
  }, []);

  const handleUpload = async () => {
    if (!uploadFile || !uploadTitle.trim()) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", uploadFile);
    formData.append("title", uploadTitle.trim());
    formData.append("professor_email", "instructor@assign.dev");
    try {
      const res = await assign.ingestFile(formData);
      if (res.course_id) {
        localStorage.setItem("instructorCourseId", res.course_id);
        showToast("Course uploaded successfully!");
        setUploadOpen(false);
        setUploadFile(null);
        setUploadTitle("");
      }
    } catch {
      showToast("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const filteredStudents =
    filter === "All"
      ? students
      : filter === "High"
      ? students.filter((s) => s.risk === "High")
      : students.filter((s) => s.risk === "On track");

  return (
    <div className="min-h-screen bg-background">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-foreground text-background px-4 py-2.5 rounded-lg text-sm shadow-lg animate-in fade-in slide-in-from-top-2">
          {toast}
        </div>
      )}

      {/* Nav */}
      <nav className="border-b border-border bg-card px-4 md:px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate("/roles")} className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <span className="font-serif text-xl text-primary font-bold">Assign</span>
          <span className="text-sm text-muted-foreground hidden sm:inline">Instructor Dashboard</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setUploadOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
          >
            <Upload className="w-3.5 h-3.5" /> Upload Course
          </button>
          <button
            onClick={() => navigate("/instructor/settings")}
            className="text-muted-foreground hover:text-foreground transition-colors"
            title="Class settings"
          >
            <Settings className="w-4 h-4" />
          </button>
          <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium text-foreground">
            JD
          </div>
        </div>
      </nav>

      {/* Tabs */}
      <div className="border-b border-border bg-card px-4 md:px-6">
        <div className="flex gap-1 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => handleTabChange(tab)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 animate-in fade-in duration-150" key={activeTab}>
        {activeTab === "Overview" && (
          <>
            {/* KPIs */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {kpis.map((k) => (
                <div key={k.label} className="rounded-xl border border-border bg-card p-4">
                  <p className="text-xs text-muted-foreground mb-1">{k.label}</p>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-serif text-foreground">{k.value}</span>
                    {k.delta && <span className={`text-xs font-medium ${k.deltaColor}`}>{k.delta}</span>}
                  </div>
                </div>
              ))}
            </div>

            {/* Two columns */}
            <div className="grid md:grid-cols-2 gap-6">
              {/* Confusion bars */}
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="font-serif text-lg text-foreground mb-4">Confusion by concept</h3>
                <div className="space-y-3">
                  {confusion.map((c) => (
                    <div key={c.name}>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-foreground">{c.name}</span>
                        <span className="text-muted-foreground">{c.pct}%</span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ease-out ${c.color}`}
                          style={{ width: animatedBars ? `${c.pct}%` : "0%" }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Suggested actions */}
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="font-serif text-lg text-foreground mb-4">Suggested actions</h3>
                <div className="space-y-3">
                  {actions.map((a, i) => (
                    <div key={i} className="flex gap-3 p-3 rounded-lg bg-muted/50">
                      <span className="text-lg">{a.icon}</span>
                      <p className="text-sm text-foreground leading-relaxed">{a.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}

        {activeTab === "Students" && (
          <>
            {/* Filters */}
            <div className="flex gap-2 mb-4">
              {(["All", "High", "On track"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                    filter === f
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-card text-muted-foreground border-border hover:text-foreground"
                  }`}
                >
                  {f === "High" ? "High Risk" : f}
                </button>
              ))}
            </div>

            {/* Table */}
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Name</th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Sessions</th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground hidden md:table-cell">
                        Stuck concepts
                      </th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground hidden sm:table-cell">
                        Engagement
                      </th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground">Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStudents.map((s) => (
                      <React.Fragment key={s.name}>
                        <tr
                          onClick={() => setExpandedStudent(expandedStudent === s.name ? null : s.name)}
                          className="border-b border-border hover:bg-muted/50 cursor-pointer transition-colors"
                        >
                          <td className="px-4 py-3 font-medium text-foreground">{s.name}</td>
                          <td className="px-4 py-3 text-foreground">{s.sessions}</td>
                          <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{s.stuck}</td>
                          <td className="px-4 py-3 hidden sm:table-cell">{engagementDots(s.engagement)}</td>
                          <td className="px-4 py-3">{riskBadge(s.risk)}</td>
                        </tr>
                        {expandedStudent === s.name && (
                          <tr key={`${s.name}-detail`} className="bg-muted/30">
                            <td colSpan={5} className="px-4 py-3">
                              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
                                <span>Last session: <strong className="text-foreground">{s.lastSession}</strong></span>
                                <span>Most revisited: <strong className="text-foreground">{s.mostRevisited}</strong></span>
                                <span>Longest stuck: <strong className="text-foreground">{s.longestStuck}</strong></span>
                                <span>Suggested: <strong className="text-foreground">{s.suggested}</strong></span>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {activeTab === "Concepts" && (
          <div className="grid sm:grid-cols-2 gap-4">
            {concepts.map((c) => (
              <div key={c.name} className="rounded-xl border border-border bg-card p-5">
                <div className="flex items-start justify-between mb-3">
                  <h3 className="font-serif text-lg text-foreground">{c.name}</h3>
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${tagColor(c.tag)}`}>
                    {c.tag}
                  </span>
                </div>
                <div className="flex items-baseline gap-1 mb-3">
                  <span
                    className={`text-3xl font-serif ${
                      c.confusion >= 50 ? "text-destructive" : c.confusion >= 30 ? "text-warning" : "text-primary"
                    }`}
                  >
                    {c.confusion}%
                  </span>
                  <span className="text-xs text-muted-foreground">confusion rate</span>
                </div>
                {/* Sparkline */}
                <div className="flex items-end gap-1 h-8 mb-3">
                  {c.bars.map((b, i) => (
                    <div
                      key={i}
                      className="flex-1 bg-primary/20 rounded-sm overflow-hidden flex flex-col justify-end"
                    >
                      <div
                        className="bg-primary rounded-sm transition-all duration-700"
                        style={{ height: animatedBars ? `${b}%` : "0%" }}
                      />
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">{c.students} students struggling</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === "Alerts" && (
          <div className="space-y-3">
            {alerts.map((a) => (
              <div
                key={a.id}
                className={`rounded-xl border border-border bg-card p-4 border-l-4 ${a.borderColor} flex flex-col sm:flex-row sm:items-center gap-3 animate-in fade-in`}
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span>{a.icon}</span>
                    <span className="text-xs text-muted-foreground">{a.time}</span>
                  </div>
                  <p className="text-sm text-foreground">{a.text}</p>
                </div>
                {a.action === "message" && (
                  <button
                    onClick={() => {
                      setMessageModal({ open: true, student: a.studentName || "" });
                      setMessageText(`Hi ${a.studentName}, I noticed you might need some help. Would you like to schedule a time to chat?`);
                    }}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors whitespace-nowrap"
                  >
                    Message student
                  </button>
                )}
                {a.action === "lecture" && (
                  <button
                    onClick={() => showToast("Added to Thursday's lecture notes \u2713")}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors whitespace-nowrap"
                  >
                    Add to lecture
                  </button>
                )}
                {a.action === "dismiss" && (
                  <button
                    onClick={() => setAlerts((prev) => prev.filter((x) => x.id !== a.id))}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border text-muted-foreground hover:bg-muted transition-colors whitespace-nowrap"
                  >
                    Dismiss
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Message modal */}
      <Dialog open={messageModal.open} onOpenChange={(open) => setMessageModal({ ...messageModal, open })}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-serif">Message {messageModal.student}</DialogTitle>
          </DialogHeader>
          <textarea
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            className="w-full h-28 px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground resize-none focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          <div className="flex justify-end">
            <button
              onClick={() => {
                setMessageModal({ open: false, student: "" });
                showToast("Message sent \u2713");
              }}
              className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              Send
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Upload Course Dialog */}
      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-serif">Upload Course Material</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">Course Title</label>
              <input
                type="text"
                value={uploadTitle}
                onChange={(e) => setUploadTitle(e.target.value)}
                placeholder="e.g. CS 301 — Algorithms"
                className="w-full px-3 py-2.5 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">File (PDF, PPTX, DOCX)</label>
              <input
                type="file"
                accept=".pdf,.pptx,.docx"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="w-full text-sm text-muted-foreground file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
              />
            </div>
            <button
              onClick={handleUpload}
              disabled={uploading || !uploadFile || !uploadTitle.trim()}
              className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {uploading ? "Uploading..." : "Upload & Generate Course"}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default InstructorApp;
