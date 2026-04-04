const API = "http://localhost:8000";

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

  teachExplainSSE: (sessionId: string) =>
    new EventSource(`${API}/api/teach/${sessionId}/explain`),

  teachSubmit: (sessionId: string, response: string) =>
    fetch(`${API}/api/teach/${sessionId}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ response }),
    }).then((r) => r.json()),

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
};
