import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import heroImage from "@/assets/hero-illustration.jpg";

const stats = [
  { value: "34%", label: "improvement in student outcomes" },
  { value: "2.1x", label: "faster concept mastery" },
  { value: "60%", label: "reduction in repetitive office hours" },
];

const HeroSection = () => {
  const navigate = useNavigate();
  return (
    <section className="pt-32 pb-20 md:pt-40 md:pb-28">
      <div className="container">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          <div className="space-y-8">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 text-primary text-sm font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              Now in 40+ institutions
            </div>

            <h1 className="text-4xl md:text-5xl lg:text-6xl leading-[1.1] tracking-tight">
              The system that{" "}
              <em className="not-italic font-serif italic text-primary">sees</em>{" "}
              how students learn
            </h1>

            <p className="text-lg text-muted-foreground max-w-lg leading-relaxed">
              Assign gives instructors real-time visibility into student learning
              while giving every student a personal AI tutor that teaches—not
              just answers.
            </p>

            <div className="flex flex-wrap gap-3">
              <Button size="lg" className="gap-2" onClick={() => navigate("/roles")}>
                See It Live <ArrowRight className="w-4 h-4" />
              </Button>
              <Button size="lg" variant="outline" onClick={() => navigate("/student")}>
                Try Student View
              </Button>
            </div>
          </div>

          <div className="relative">
            <div className="rounded-2xl overflow-hidden border shadow-2xl shadow-primary/10">
              <img
                src={heroImage}
                alt="Assign platform showing learning data flow between students and instructors"
                className="w-full h-auto"
              />
            </div>
            <div className="absolute -bottom-4 -left-4 w-24 h-24 rounded-2xl bg-primary/10 -z-10" />
            <div className="absolute -top-4 -right-4 w-16 h-16 rounded-full bg-primary/5 -z-10" />
          </div>
        </div>

        {/* Stats bar */}
        <div className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-8 border-t pt-12">
          {stats.map((stat) => (
            <div key={stat.label} className="text-center md:text-left">
              <div className="text-3xl md:text-4xl font-serif text-primary">{stat.value}</div>
              <div className="text-sm text-muted-foreground mt-1">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
