const steps = [
  {
    num: "01",
    title: "Students learn with AI",
    description: "Every interaction—questions, hesitations, retries—generates structured learning signals.",
  },
  {
    num: "02",
    title: "Assign analyzes signals",
    description: "Patterns emerge: which concepts confuse, who's falling behind, where materials fail.",
  },
  {
    num: "03",
    title: "Instructors act on insights",
    description: "Walk into class knowing what to reteach. Get actionable suggestions, not just charts.",
  },
  {
    num: "04",
    title: "Outcomes improve at scale",
    description: "Better teaching → better results → more adoption. The loop that institutions pay for.",
  },
];

const HowItWorks = () => {
  return (
    <section id="how-it-works" className="py-20 bg-secondary/50">
      <div className="container">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <h2 className="text-3xl md:text-4xl tracking-tight mb-4">
            The feedback loop
          </h2>
          <p className="text-muted-foreground text-lg">
            Student usage feeds instructor intelligence. That's the engine.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
          {steps.map((step, i) => (
            <div key={step.num} className="relative">
              <div className="text-5xl font-serif text-primary/15 mb-2">{step.num}</div>
              <h3 className="text-lg font-serif mb-2">{step.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {step.description}
              </p>
              {i < steps.length - 1 && (
                <div className="hidden lg:block absolute top-8 -right-3 text-primary/30 text-xl">→</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorks;
