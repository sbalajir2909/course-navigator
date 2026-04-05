import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BookOpen } from "lucide-react";

const StudentEnroll = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  const handleJoin = async () => {
    if (!courseId || !name || !email) return;
    setLoading(true);
    try {
      const data = await api.enroll(courseId, { name, email });
      localStorage.setItem("assign_student_id", data.student_id);
      localStorage.setItem("assign_student_name", name);
      localStorage.setItem("assign_course_id", courseId);
      navigate(`/course/${courseId}/diagnostic`);
    } catch {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-secondary/30">
      <div className="w-full max-w-md bg-card rounded-xl shadow-lg border p-8 space-y-6">
        <div className="text-center space-y-2">
          <BookOpen className="h-10 w-10 mx-auto text-primary" />
          <h1 className="text-2xl font-bold text-foreground">Join Course</h1>
          <p className="text-sm text-muted-foreground">Enter your details to enroll and start learning.</p>
        </div>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Your Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" />
          </div>
          <div className="space-y-1.5">
            <Label>Email</Label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@university.edu" />
          </div>
        </div>
        <Button onClick={handleJoin} disabled={!name || !email || loading} className="w-full">
          {loading ? "Joining…" : "Join Course"}
        </Button>
      </div>
    </div>
  );
};

export default StudentEnroll;
