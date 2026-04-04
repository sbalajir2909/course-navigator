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

  teachSubmit: (sessionId: string, explanation: string) =>
    fetch(`${API}/api/teach/${sessionId}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ explanation }),
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

  dashboardStruggles: (courseId: string) =>
    fetch(`${API}/api/dashboard/${courseId}/heatmap`).then((r) => r.json()).then((data) => {
      // Derive struggle rows from the heatmap data: students with multiple attempts
      // The heatmap endpoint returns { modules, students, scores, attempts? }
      // We build struggle rows from the available data
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
      // Sort by attempts descending so worst struggles are first
      rows.sort((a, b) => b.attempts - a.attempts || a.last_score - b.last_score);
      return { struggles: rows };
    }),
};
