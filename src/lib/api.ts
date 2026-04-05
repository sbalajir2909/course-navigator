const API = "http://localhost:8000";

// ─── Shared request helper (authenticated) ────────────────────
class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("assign_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json();
}

// ─── Original course-navigator API ────────────────────────────
export const api = {
  ingest: (formData: FormData) =>
    fetch(`${API}/api/ingest`, { method: "POST", body: formData }),

  ingestStatus: (courseId: string) =>
    fetch(`${API}/api/ingest/${courseId}/status`).then((r) => r.json()),

  courseGraph: (courseId: string) =>
    fetch(`${API}/api/courses/${courseId}/graph`).then((r) => r.json()),

  courseDetail: (courseId: string) =>
    fetch(`${API}/api/courses/${courseId}`).then((r) => r.json()),

  enroll: (courseId: string, data: { name: string; email: string }) =>
    fetch(`${API}/api/courses/${courseId}/enroll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then((r) => r.json()),

  teachStart: (moduleId: string, studentId: string) =>
    fetch(`${API}/api/teach/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module_id: moduleId, student_id: studentId }),
    }).then((r) => r.json()),

  teachSubmit: (sessionId: string, explanation: string) =>
    fetch(`${API}/api/teach/${sessionId}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ explanation }),
    }).then((r) => r.json()),

  teachHistory: (sessionId: string) =>
    fetch(`${API}/api/teach/${sessionId}/history`).then((r) => r.json()),

  teachChat: (sessionId: string) =>
    fetch(`${API}/api/teach/${sessionId}/chat`).then((r) => r.json()),

  moduleAssessments: (courseId: string, moduleId: string) =>
    fetch(`${API}/api/courses/${courseId}/modules/${moduleId}/assessments`).then((r) => r.json()),

  dashboardStats: (courseId: string) =>
    fetch(`${API}/api/dashboard/${courseId}/stats`).then((r) => r.json()),

  dashboardHeatmap: (courseId: string) =>
    fetch(`${API}/api/dashboard/${courseId}/heatmap`).then((r) => r.json()),

  dashboardInterventions: (courseId: string) =>
    fetch(`${API}/api/dashboard/${courseId}/interventions`).then((r) => r.json()),

  dashboardExport: (courseId: string) =>
    fetch(`${API}/api/dashboard/${courseId}/export`),

  dashboardStruggles: (courseId: string) =>
    fetch(`${API}/api/dashboard/${courseId}/heatmap`).then((r) => r.json()).then((data) => {
      const rows: { student_name: string; module_title: string; attempts: number; last_score: number }[] = [];
      if (data.modules && data.students && data.scores) {
        for (let mi = 0; mi < data.modules.length; mi++) {
          for (let si = 0; si < data.students.length; si++) {
            const score = data.scores[mi]?.[si] ?? 0;
            const attempts = data.attempts?.[mi]?.[si] ?? (score < 60 ? 2 : 1);
            if (score > 0) {
              rows.push({
                student_name: data.students[si],
                module_title: data.modules[mi],
                attempts,
                last_score: score,
              });
            }
          }
        }
      }
      rows.sort((a, b) => b.attempts - a.attempts || a.last_score - b.last_score);
      return { struggles: rows };
    }),
};

// ─── Auth ─────────────────────────────────────────────────────
export const auth = {
  register: (body: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
    role: "student" | "instructor";
    education_level?: string;
  }) => request<{ access_token: string; user_id: string; role: string; first_name: string }>(
    "/api/auth/register",
    { method: "POST", body: JSON.stringify(body) }
  ),

  login: (email: string, password: string) => {
    const form = new URLSearchParams({ username: email, password });
    return request<{ access_token: string; user_id: string; role: string; first_name: string }>(
      "/api/auth/login",
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      }
    );
  },
};

// ─── AI / Sessions ────────────────────────────────────────────
export const ai = {
  createSession: (classId: string, topic: string, mode = "socratic") =>
    request<{ session_id: string }>("/api/ai/sessions", {
      method: "POST",
      body: JSON.stringify({ class_id: classId, topic, mode }),
    }),

  chat: (sessionId: string, message: string, isChip = false) =>
    request<{
      message: string;
      mode: string;
      chips: string[];
      confusion_detected: boolean;
      misconception?: string;
      confidence_estimate?: number;
    }>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message, is_chip_response: isChip }),
    }),

  endSession: (sessionId: string) =>
    request<{ is_qualifying: boolean; streak: Record<string, unknown> }>(
      `/api/sessions/${sessionId}/end`,
      { method: "POST" }
    ),
};

// ─── Classes ──────────────────────────────────────────────────
export const classes = {
  create: (body: { name: string; description?: string; course_code?: string }) =>
    request<{ class_id: string; invite_code: string; name: string }>("/api/classes/", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  join: (inviteCode: string, studentId: string) =>
    request<{ class_id: string; class_name: string }>("/api/classes/join", {
      method: "POST",
      body: JSON.stringify({ invite_code: inviteCode, student_id: studentId }),
    }),

  get: (classId: string) => request<Record<string, unknown>>(`/api/classes/${classId}`),

  updateSettings: (classId: string, settings: { ai_settings?: Record<string, unknown>; gamification_settings?: Record<string, unknown> }) =>
    request(`/api/classes/${classId}/settings`, {
      method: "PATCH",
      body: JSON.stringify(settings),
    }),

  listMaterials: (classId: string) =>
    request<{ materials: Array<Record<string, unknown>> }>(`/api/classes/${classId}/materials`),
};

// ─── Analytics ────────────────────────────────────────────────
export const analytics = {
  overview: (classId: string, days = 7) =>
    request<Record<string, unknown>>(`/api/analytics/class/${classId}/overview?days=${days}`),

  confusion: (classId: string, days = 7) =>
    request<{ confusion_by_topic: Record<string, number> }>(
      `/api/analytics/class/${classId}/confusion?days=${days}`
    ),

  students: (classId: string) =>
    request<{ students: Array<Record<string, unknown>> }>(`/api/analytics/class/${classId}/students`),

  alerts: (classId: string) =>
    request<{ alerts: Array<Record<string, unknown>> }>(`/api/analytics/class/${classId}/alerts`),
};

// ─── Gamification ─────────────────────────────────────────────
export const gamification = {
  streak: (userId: string) =>
    request<{
      current_streak: number;
      longest_streak: number;
      last_qualifying_date: string | null;
      freeze_tokens_remaining: number;
    }>(`/api/gamification/streak/${userId}`),

  applyFreeze: (userId: string) =>
    request(`/api/gamification/streak/${userId}/freeze`, { method: "POST" }),

  leaderboard: (classId: string, period = "all_time") =>
    request<{
      leaderboard: Array<{ rank: number; name: string; total_score: number }>;
    }>(`/api/gamification/leaderboard/${classId}?period=${period}`),

  badges: (userId: string) =>
    request<{
      badges: Array<{ badge_id: string; label: string; icon: string; description: string; earned_at: string }>;
    }>(`/api/gamification/badges/${userId}`),
};

// ─── Events (analytics tracking) ─────────────────────────────
export const events = {
  leaderboardViewed: (_data: { userId: string; classId: string }) => {
    // No-op for now — placeholder for analytics tracking
  },
};

// ─── Assign B2B Backend ───────────────────────────────────────
const ASSIGN_URL = 'http://localhost:8000';

export const assign = {
  ingestFile: (formData: FormData) =>
    fetch(`${ASSIGN_URL}/api/ingest`, { method: 'POST', body: formData }).then(r => r.json()),

  pollStatus: (courseId: string) =>
    fetch(`${ASSIGN_URL}/api/ingest/${courseId}/status`).then(r => r.json()),

  getCourse: (courseId: string) =>
    fetch(`${ASSIGN_URL}/api/courses/${courseId}`).then(r => r.json()),

  getCourseGraph: (courseId: string) =>
    fetch(`${ASSIGN_URL}/api/courses/${courseId}/graph`).then(r => r.json()),

  enrollStudent: (courseId: string, body: { email: string; name: string }) =>
    fetch(`${ASSIGN_URL}/api/courses/${courseId}/enroll`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => r.json()),

  startSession: (moduleId: string, studentId: string) =>
    fetch(`${ASSIGN_URL}/api/teach/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ module_id: moduleId, student_id: studentId }),
    }).then(r => r.json()),

  submitExplanation: (sessionId: string, explanation: string) =>
    fetch(`${ASSIGN_URL}/api/teach/${sessionId}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ explanation }),
    }).then(r => r.json()),

  getDashboardStats: (courseId: string) =>
    fetch(`${ASSIGN_URL}/api/dashboard/${courseId}/stats`).then(r => r.json()),

  getHeatmap: (courseId: string) =>
    fetch(`${ASSIGN_URL}/api/dashboard/${courseId}/heatmap`).then(r => r.json()),

  getInterventions: (courseId: string) =>
    fetch(`${ASSIGN_URL}/api/dashboard/${courseId}/interventions`).then(r => r.json()),
};

export async function streamExplanation(
  sessionId: string,
  strategy = 'initial',
  onToken: (t: string) => void,
  onDone: () => void
) {
  const res = await fetch(`${ASSIGN_URL}/api/teach/${sessionId}/explain?strategy=${strategy}`);
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() || '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const ev = JSON.parse(line.slice(6));
          if (ev.token) onToken(ev.token);
          if (ev.done) { onDone(); return; }
        } catch { /* ignore */ }
      }
    }
  }
  onDone();
}

export { ApiError };
