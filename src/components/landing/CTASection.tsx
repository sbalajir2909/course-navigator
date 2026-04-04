import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

const CTASection = () => {
  const navigate = useNavigate();
  return (
    <section className="py-24">
      <div className="container">
        <div className="relative rounded-2xl bg-foreground text-background overflow-hidden p-12 md:p-16 text-center">
          <div className="absolute inset-0 opacity-10">
            <div className="absolute top-0 right-0 w-64 h-64 rounded-full bg-primary blur-3xl" />
            <div className="absolute bottom-0 left-0 w-48 h-48 rounded-full bg-primary blur-3xl" />
          </div>
          <div className="relative z-10 max-w-2xl mx-auto space-y-6">
            <h2 className="text-3xl md:text-4xl tracking-tight">
              Ready to see how your students{" "}
              <em className="italic">actually</em> learn?
            </h2>
            <p className="text-background/70 text-lg">
              Join 40+ institutions using Assign to improve outcomes and give
              instructors the visibility they've never had.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <Button size="lg" className="gap-2" onClick={() => navigate("/roles")}>
                Try the Demo <ArrowRight className="w-4 h-4" />
              </Button>
              <Button size="lg" variant="outline" className="border-background/20 text-background hover:bg-background/10" onClick={() => navigate("/instructor")}>
                See Instructor View
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default CTASection;
