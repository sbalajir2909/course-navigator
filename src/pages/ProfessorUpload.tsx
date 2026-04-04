import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Upload, FileText, Loader2 } from "lucide-react";
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
  const [file, setFile] = useState<File | null>(null);
  const [courseTitle, setCourseTitle] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusIdx, setStatusIdx] = useState(0);

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted.length > 0) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    maxFiles: 1,
  });

  const handleSubmit = async () => {
    if (!file || !courseTitle || !email) return;
    setLoading(true);
    setStatusIdx(0);

    const fd = new FormData();
    fd.append("file", file);
    fd.append("course_title", courseTitle);
    fd.append("professor_email", email);

    try {
      const res = await api.ingest(fd);
      const { course_id } = await res.json();

      const interval = setInterval(() => {
        setStatusIdx((i) => Math.min(i + 1, statusMessages.length - 1));
      }, 3000);

      const poll = setInterval(async () => {
        try {
          const status = await api.ingestStatus(course_id);
          if (status.status === "ready") {
            clearInterval(poll);
            clearInterval(interval);
            navigate(`/course/${course_id}`);
          }
        } catch {}
      }, 3000);
    } catch {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-secondary/30">
      <div className="w-full max-w-xl bg-card rounded-xl shadow-lg border p-8 space-y-6">
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold text-foreground">Assign</h1>
          <p className="text-muted-foreground text-sm">Upload your course material to auto-generate a structured course.</p>
        </div>

        {loading ? (
          <div className="flex flex-col items-center py-12 space-y-4">
            <Loader2 className="h-10 w-10 text-primary animate-spin" />
            <p className="text-foreground font-medium">{statusMessages[statusIdx]}</p>
          </div>
        ) : (
          <>
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
                isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
              }`}
            >
              <input {...getInputProps()} />
              {file ? (
                <div className="flex items-center justify-center gap-2 text-foreground">
                  <FileText className="h-5 w-5 text-primary" />
                  <span className="font-medium">{file.name}</span>
                </div>
              ) : (
                <div className="space-y-2">
                  <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
                  <p className="text-muted-foreground text-sm">
                    Drag & drop a PDF, PPTX, or DOCX file here, or click to browse
                  </p>
                </div>
              )}
            </div>

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

            <Button onClick={handleSubmit} disabled={!file || !courseTitle || !email} className="w-full">
              Generate Course
            </Button>
          </>
        )}
      </div>
    </div>
  );
};

export default ProfessorUpload;
