"""
agents/course_generator.py
Two-pass course generator:
  Pass 1 (fast): Generate module structure from document
  Pass 2: For each module, decompose into 3-6 atomic concepts

Each concept = one teaching turn. A module with 4 concepts = 4 teach → validate cycles.
This is what makes it feel like a real course, not a single-question quiz.
"""
from __future__ import annotations
import os, json
from groq import Groq


async def generate_course(chunks: list[dict], title: str) -> dict:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # Limit chunks to avoid TPM overflow
    chunk_text = "\n\n".join([
        f"[Chunk {c['chunk_index']}]: {c['content'][:250]}"
        for c in chunks[:20]
    ])

    # ── Pass 1: Generate module structure ─────────────────────
    pass1_prompt = f"""You are an expert instructional designer building a real course.

Course Title: {title}

Source Material:
{chunk_text}

Generate a structured course with 4-8 modules.

IMPORTANT: Each module must have 3-5 specific CONCEPTS — these are the atomic ideas a student
must understand. Think of concepts as individual lesson units within the module.

Rules:
- Modules group related concepts
- Each concept is teachable in one focused explanation (2-4 minutes)
- Concepts within a module build on each other in order
- Do not create concepts that are too broad ("understand X") — make them specific ("explain why X causes Y")

Return ONLY valid JSON:
{{
  "title": "{title}",
  "description": "2-3 sentence course overview",
  "modules": [
    {{
      "title": "Module title (e.g. 'Foundations of Threat Modeling')",
      "description": "One sentence: what this module teaches",
      "prerequisites": [],
      "source_chunk_indices": [0, 1],
      "estimated_minutes": 25,
      "concepts": [
        {{
          "title": "Specific concept title (e.g. 'What threat modeling is and why it matters')",
          "learning_objective": "Student will be able to explain [specific thing] in their own words",
          "key_points": ["point 1", "point 2", "point 3"],
          "estimated_minutes": 5
        }}
      ]
    }}
  ]
}}"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": pass1_prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
            max_tokens=3000,
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
    except Exception as e:
        print(f"[COURSE_GEN] Error in pass 1: {e}")
        # Minimal fallback structure
        data = {
            "title": title,
            "description": f"A course covering {title}",
            "modules": [
                {
                    "title": f"Introduction to {title}",
                    "description": f"Core concepts of {title}",
                    "prerequisites": [],
                    "source_chunk_indices": list(range(min(5, len(chunks)))),
                    "estimated_minutes": 30,
                    "concepts": [
                        {
                            "title": f"What is {title}?",
                            "learning_objective": f"Student will be able to explain what {title} is",
                            "key_points": ["Definition", "Why it matters", "Key components"],
                            "estimated_minutes": 5,
                        }
                    ],
                }
            ],
        }

    # ── Validate and enrich structure ──────────────────────────
    modules = data.get("modules", [])
    enriched_modules = []

    for mod in modules:
        concepts = mod.get("concepts", [])

        # If no concepts generated, create them from learning objectives (fallback)
        if not concepts:
            objectives = mod.get("learning_objectives", [])
            if objectives:
                concepts = [
                    {
                        "title": obj.replace("Student will be able to ", "").replace("Student will understand ", "").capitalize(),
                        "learning_objective": obj,
                        "key_points": [],
                        "estimated_minutes": 5,
                    }
                    for obj in objectives[:5]
                ]
            else:
                # Last resort: one concept per module from description
                concepts = [
                    {
                        "title": mod.get("title", "Core Concept"),
                        "learning_objective": f"Student will be able to explain {mod.get('title', 'this concept')} in their own words",
                        "key_points": [],
                        "estimated_minutes": 5,
                    }
                ]

        # Ensure each concept has required fields
        clean_concepts = []
        for c in concepts:
            clean_concepts.append({
                "title": c.get("title", "Concept"),
                "learning_objective": c.get("learning_objective", f"Explain {c.get('title', 'this concept')}"),
                "key_points": c.get("key_points", []),
                "estimated_minutes": c.get("estimated_minutes", 5),
            })

        enriched_modules.append({
            "title": mod.get("title", "Module"),
            "description": mod.get("description", ""),
            "learning_objectives": [c["learning_objective"] for c in clean_concepts],
            "prerequisites": mod.get("prerequisites", []),
            "source_chunk_indices": mod.get("source_chunk_indices", []),
            "estimated_minutes": sum(c["estimated_minutes"] for c in clean_concepts),
            "concepts": clean_concepts,
        })

    return {
        "title": data.get("title", title),
        "description": data.get("description", ""),
        "modules": enriched_modules,
    }
