import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Save } from "lucide-react";
import { classes as classesApi } from "@/lib/api";

/**
 * Instructor class settings page.
 * Lets instructors override global ai_config.yaml and scoring_config.yaml
 * defaults for their specific class — no code change required.
 */

const TUTOR_MODES = [
  { id: "socratic",  label: "Socratic Tutor",  desc: "Guides through questions. No direct answers." },
  { id: "hint_only", label: "Hint Mode",        desc: "Gives only hints, never full explanations." },
  { id: "explain",   label: "Explain Mode",     desc: "Full explanations with analogies." },
  { id: "quiz",      label: "Quiz Mode",        desc: "Tests student with adaptive questions." },
  { id: "exam_prep", label: "Exam Prep",        desc: "Simulates exam-style questions." },
];

const ClassSettings = () => {
  const navigate = useNavigate();
  const [saved, setSaved] = useState(false);

  // AI settings state (these override ai_config.yaml for this class)
  const [defaultMode, setDefaultMode] = useState("socratic");
  const [allowDirectAnswers, setAllowDirectAnswers] = useState(false);
  const [hintsBeforeAnswer, setHintsBeforeAnswer] = useState(2);
  const [toneStyle, setToneStyle] = useState("friendly");
  const [materialGroundedOnly, setMaterialGroundedOnly] = useState(false);

  // Gamification settings state (these override scoring_config.yaml for this class)
  const [leaderboardEnabled, setLeaderboardEnabled] = useState(true);
  const [streaksEnabled, setStreaksEnabled] = useState(true);
  const [badgesEnabled, setBadgesEnabled] = useState(true);

  const handleSave = async () => {
    // TODO: replace "CLASS_ID" with actual class ID from route params
    const aiSettings = {
      behavior: {
        default_mode: defaultMode,
        answer_policy: {
          allow_direct_answers: allowDirectAnswers,
          hints_required_before_answer: hintsBeforeAnswer,
        },
        tone: { style: toneStyle },
      },
      retrieval: {
        grounding: { material_grounded_only_mode: materialGroundedOnly },
      },
    };

    const gamificationSettings = {
      leaderboard: { enabled: leaderboardEnabled },
      streaks: { enabled: streaksEnabled },
      badges: { enabled: badgesEnabled },
    };

    // await classesApi.updateSettings("CLASS_ID", { ai_settings: aiSettings, gamification_settings: gamificationSettings });
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const Toggle = ({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) => (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${value ? "bg-primary" : "bg-muted"}`}
    >
      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${value ? "translate-x-5" : "translate-x-0.5"}`} />
    </button>
  );

  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b border-border bg-card px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/instructor")} className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <span className="font-serif text-xl text-foreground">Class Settings</span>
          <span className="text-sm text-muted-foreground">CS 301 — Algorithms</span>
        </div>
        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Save className="w-4 h-4" />
          {saved ? "Saved!" : "Save"}
        </button>
      </nav>

      <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
        {/* AI Behavior */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h2 className="font-serif text-lg text-foreground">AI Tutor Behavior</h2>
            <p className="text-xs text-muted-foreground mt-1">
              These settings override the global defaults for this class only.
            </p>
          </div>

          <div className="divide-y divide-border">
            {/* Default mode */}
            <div className="px-5 py-4">
              <label className="block text-sm font-medium text-foreground mb-3">Default tutor mode</label>
              <div className="space-y-2">
                {TUTOR_MODES.map((m) => (
                  <label key={m.id} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${defaultMode === m.id ? "border-primary/40 bg-primary/5" : "border-border hover:bg-muted/50"}`}>
                    <input
                      type="radio"
                      name="mode"
                      value={m.id}
                      checked={defaultMode === m.id}
                      onChange={() => setDefaultMode(m.id)}
                      className="mt-0.5 accent-primary"
                    />
                    <div>
                      <div className="text-sm font-medium text-foreground">{m.label}</div>
                      <div className="text-xs text-muted-foreground">{m.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Direct answers */}
            <div className="px-5 py-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Allow direct answers</p>
                <p className="text-xs text-muted-foreground">If off, AI won't give answers until hints are exhausted</p>
              </div>
              <Toggle value={allowDirectAnswers} onChange={setAllowDirectAnswers} />
            </div>

            {/* Hints before answer */}
            {!allowDirectAnswers && (
              <div className="px-5 py-4">
                <label className="block text-sm font-medium text-foreground mb-2">
                  Hints required before answer: <strong>{hintsBeforeAnswer}</strong>
                </label>
                <input
                  type="range"
                  min={1}
                  max={5}
                  value={hintsBeforeAnswer}
                  onChange={(e) => setHintsBeforeAnswer(+e.target.value)}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                  <span>1 hint</span><span>5 hints</span>
                </div>
              </div>
            )}

            {/* Tone */}
            <div className="px-5 py-4">
              <label className="block text-sm font-medium text-foreground mb-2">AI tone</label>
              <select
                value={toneStyle}
                onChange={(e) => setToneStyle(e.target.value)}
                className="px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                <option value="friendly">Friendly (recommended)</option>
                <option value="formal">Formal</option>
                <option value="neutral">Neutral</option>
              </select>
            </div>

            {/* Material grounded */}
            <div className="px-5 py-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">Material-grounded only</p>
                <p className="text-xs text-muted-foreground">AI only answers from uploaded materials, not general knowledge</p>
              </div>
              <Toggle value={materialGroundedOnly} onChange={setMaterialGroundedOnly} />
            </div>
          </div>
        </div>

        {/* Gamification */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h2 className="font-serif text-lg text-foreground">Gamification</h2>
          </div>
          <div className="divide-y divide-border">
            {[
              { label: "Leaderboard", desc: "Show class ranking to students", value: leaderboardEnabled, onChange: setLeaderboardEnabled },
              { label: "Streaks", desc: "Daily learning streak tracking", value: streaksEnabled, onChange: setStreaksEnabled },
              { label: "Badges", desc: "Achievement badges for milestones", value: badgesEnabled, onChange: setBadgesEnabled },
            ].map((item) => (
              <div key={item.label} className="px-5 py-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-foreground">{item.label}</p>
                  <p className="text-xs text-muted-foreground">{item.desc}</p>
                </div>
                <Toggle value={item.value} onChange={item.onChange} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ClassSettings;
