import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import ProfessorUpload from "./pages/ProfessorUpload";
import CourseGraph from "./pages/CourseGraph";
import StudentEnroll from "./pages/StudentEnroll";
import StudentCourseView from "./pages/StudentCourseView";
import StudentLearning from "./pages/StudentLearning";
import DiagnosticQuiz from "./pages/DiagnosticQuiz";
import LearningPath from "./pages/LearningPath";
import ProfessorDashboard from "./pages/ProfessorDashboard";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ProfessorUpload />} />
          <Route path="/course/:id" element={<CourseGraph />} />
          <Route path="/join/:courseId" element={<StudentEnroll />} />
          <Route path="/course/:courseId/diagnostic" element={<DiagnosticQuiz />} />
          <Route path="/course/:courseId/path" element={<LearningPath />} />
          <Route path="/course/:courseId/learn" element={<StudentCourseView />} />
          <Route path="/course/:courseId/learn/:moduleId" element={<StudentLearning />} />
          <Route path="/dashboard/:courseId" element={<ProfessorDashboard />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
