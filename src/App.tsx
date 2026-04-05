import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/context/AuthContext";

import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import RoleSelector from "./pages/RoleSelector";
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import Leaderboard from "./pages/student/Leaderboard";
import Progress from "./pages/student/Progress";
import ClassSettings from "./pages/instructor/ClassSettings";

import CourseGraph from "./pages/CourseGraph";
import ProfessorUpload from "./pages/ProfessorUpload";
import ProfessorDashboard from "./pages/ProfessorDashboard";
import StudentCourseView from "./pages/StudentCourseView";
import StudentLearning from "./pages/StudentLearning";
import StudentEnroll from "./pages/StudentEnroll";
import DiagnosticQuiz from "./pages/DiagnosticQuiz";
import LearningPath from "./pages/LearningPath";
import StudentApp from "./pages/StudentApp";
import InstructorApp from "./pages/InstructorApp";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Index />} />
            <Route path="/roles" element={<RoleSelector />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/student" element={<StudentApp />} />
            <Route path="/student/leaderboard" element={<Leaderboard />} />
            <Route path="/student/progress" element={<Progress />} />
            <Route path="/instructor" element={<InstructorApp />} />
            <Route path="/instructor/settings" element={<ClassSettings />} />
            <Route path="/upload" element={<ProfessorUpload />} />
            <Route path="/course/:id" element={<CourseGraph />} />
            <Route path="/course/:courseId/learn" element={<StudentCourseView />} />
            <Route path="/course/:courseId/learn/:moduleId" element={<StudentLearning />} />
            <Route path="/join/:courseId" element={<StudentEnroll />} />
            <Route path="/diagnostic/:courseId" element={<DiagnosticQuiz />} />
            <Route path="/course/:courseId/diagnostic" element={<DiagnosticQuiz />} />
            <Route path="/learning-path/:courseId" element={<LearningPath />} />
            <Route path="/course/:courseId/path" element={<LearningPath />} />
            <Route path="/dashboard/:courseId" element={<ProfessorDashboard />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
