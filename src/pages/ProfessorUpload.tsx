import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Upload, FileText, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const statusMessages = [
  "Parsing document…",
  "Generating course…",
  "Running faithfulness check…",
];

const ProfessorUpload = () => {
  const navigate = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [courseTitle, setCourseTitle] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusIdx, setStatusIdx] = useState(0);
  const [progressText, setProgressText] = useState("");
  const [createdCourses, setCreatedCourses] = useState<{ id: string; title: string }[]>([]);

  const onDrop = useCallback((accepted: File[]) => {
    setFiles((prev) => [...prev, ...accepted]);
  }, []);

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    multiple: true,
  });

  const handleSubmit = async () => {
    if (files.length === 0 || !courseTitle || !email) return;
    setLoading(true);
    setStatusIdx(0);
    setCreatedCourses([]);

    const interval = setInterval(() => {
      setStatusIdx((i) => Math.min(i + 1, statusMessages.length - 1));
    }, 3000);

    const courseIds: { id: string; title: string }[] = [];

    try {
      for (let i = 0; i < files.length; i++) {
        setProgressText(`Processing file ${i + 1} of ${files.length}…`);

        const fd = new FormData();
        fd.append("file", files[i]);
        fd.append("course_title", courseTitle);
        fd.append("professor_email", email);

        const res = await api.ingest(fd);
        const { course_id } = await res.json();
        courseIds.push({ id: course_id, title: files[i].name });

        // Poll status for the last file
        if (i === files.length - 1) {
          await new Promise<void>((resolve) => {
            const poll = setInterval(async () => {
              try {
                const status = await api.ingestStatus(course_id);
                if (status.status === "ready") {
                  clearInterval(poll);
                  resolve();
                }
              } catch {}
            }, 3000);
          });
        }
      }

      clearInterval(interval);
      setCreatedCourses(courseIds);

      // If single file, navigate directly
      if (courseIds.length === 1) {
        navigate(`/course/${courseIds[0].id}`);
      } else {
        setLoading(false);
        setProgressText("");
      }
    } catch {
      clearInterval(interval);
      setLoading(false);
      setProgressText("");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-secondary/30">
      <div className="w-full max-w-xl bg-card rounded-xl shadow-lg border p-8 space-y-6">
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold text-foreground">Assign</h1>
          <p className="text-muted-foreground text-sm">Upload your course material to auto-generate a structured course.</p>
        </div>

        {/* Show created courses list when multiple files processed */}
        {createdCourses.length > 1 && !loading && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-foreground">All files processed! Select a course:</p>
            {createdCourses.map((c) => (
              <button
                key={c.id}
                onClick={() => navigate(`/course/${c.id}`)}
                className="w-full text-left bg-secondary/50 hover:bg-secondary border rounded-lg p-3 flex items-center gap-3 transition-colors"
              >
                <FileText className="h-4 w-4 text-primary shrink-0" />
                <div>
                  <p className="text-sm font-medium text-foreground">{c.title}</p>
                  <p className="text-xs text-muted-foreground">Course ID: {c.id}</p>
                </div>
              </button>
            ))}
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center py-12 space-y-4">
            <Loader2 className="h-10 w-10 text-primary animate-spin" />
            <p className="text-foreground font-medium">{statusMessages[statusIdx]}</p>
            {progressText && (
              <p className="text-sm text-muted-foreground">{progressText}</p>
            )}
          </div>
        ) : createdCourses.length <= 1 ? (
          <>
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
                isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
              }`}
            >
              <input {...getInputProps()} />
              <div className="space-y-2">
                <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
                <p className="text-muted-foreground text-sm">
                  Drag & drop PDF, PPTX, or DOCX files here, or click to browse
                </p>
              </div>
            </div>

            {/* File list */}
            {files.length > 0 && (
              <div className="space-y-2">
                {files.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 bg-secondary/50 rounded-lg px-3 py-2"
                  >
                    <FileText className="h-4 w-4 text-primary shrink-0" />
                    <span className="text-sm text-foreground flex-1 truncate">{f.name}</span>
                    <button
                      onClick={() => removeFile(i)}
                      className="text-muted-foreground hover:text-destructive transition-colors"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="title">Course Title</Label>
                <Input id="title" value={courseTitle} onChange={(e) => setCourseTitle(e.target.value)} placeholder="e.g. Introduction to Machine Learning" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="email">Professor Email</Label>
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="professor@university.edu" />
              </div>
            </div>

            <Button onClick={handleSubmit} disabled={files.length === 0 || !courseTitle || !email} className="w-full">
              Generate Course{files.length > 1 ? ` (${files.length} files)` : ""}
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
};

export default ProfessorUpload;
