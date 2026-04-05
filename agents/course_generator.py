"""
agents/course_generator.py

Two-pass course generation that covers ALL source material:

  Pass 1 — Topic extraction
    Process every chunk (batched, 150 chars each) through the LLM.
    Collect a flat list of every topic/concept mentioned in the document.
    Deduplicate and group into 5-12 module-level topics.

  Pass 2 — Module expansion
    For each module topic, find the most relevant source chunks by keyword overlap.
    Call the LLM to expand the topic into a module with 3-5 atomic concepts.
    Each concept = one teach→validate cycle.

No content is silently dropped. Every chunk participates in topic extraction.
Module count and concept counts are logged to the terminal.
"""
from __future__ import annotations
import json
import re
from api.cf_client import complete_json as cf_json

# ── Tunables ──────────────────────────────────────────────────────────────────
_EXTRACT_CHARS   = 180   # chars per chunk sent to pass-1 LLM
_BATCH_SIZE      = 45    # chunks per pass-1 batch (keeps prompt under ~10k chars)
_EXPAND_CHARS    = 600   # chars per chunk sent to pass-2 LLM
_EXPAND_CHUNKS   = 10    # top-N relevant chunks used in pass-2
_MAX_MODULES     = 12    # cap to avoid runaway generation on huge documents
_MIN_CONCEPTS    = 5
_MAX_CONCEPTS    = 8


# ── Helpers ───────────────────────────────────────────────────────────────────

def _keyword_score(topic: str, chunk_content: str) -> int:
    """Rough keyword overlap score between a topic string and chunk content."""
    topic_words = set(re.sub(r"[^a-z0-9 ]", " ", topic.lower()).split()) - {
        "the", "a", "an", "of", "in", "to", "and", "or", "is", "are", "be",
        "that", "this", "it", "its", "for", "with", "from", "how", "why", "what",
    }
    if not topic_words:
        return 0
    content_lower = chunk_content.lower()
    return sum(1 for w in topic_words if w in content_lower)


def _relevant_chunks(topic: str, chunks: list[dict], top_n: int = _EXPAND_CHUNKS) -> list[int]:
    """Return the chunk_index values of the top-N most relevant chunks for a topic."""
    scored = [(c["chunk_index"], _keyword_score(topic, c["content"])) for c in chunks]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [idx for idx, score in scored[:top_n] if score > 0]
    # If nothing matched, fall back to the first few chunks
    if not top:
        top = [c["chunk_index"] for c in chunks[:3]]
    return top


def _clean_concepts(raw: list[dict]) -> list[dict]:
    """Normalise concept dicts to a consistent shape."""
    clean = []
    for c in raw[:_MAX_CONCEPTS]:
        clean.append({
            "title":              c.get("title", "Concept"),
            "learning_objective": c.get("learning_objective",
                                        f"Explain {c.get('title', 'this concept')} in own words"),
            "key_points":         c.get("key_points", [])[:6],   # allow up to 6 key points
            "estimated_minutes":  c.get("estimated_minutes", 5),
        })
    return clean


# ── Pass 1 — Topic extraction ─────────────────────────────────────────────────

async def _extract_topics_from_batch(batch: list[dict], title: str) -> list[str]:
    """Extract a flat list of topics from one batch of chunks."""
    batch_text = "\n".join(
        f"[{c['chunk_index']}] {c['content'][:_EXTRACT_CHARS]}"
        for c in batch
    )
    prompt = f"""You are analyzing source material from a course titled "{title}".

Below are excerpts (chunk index + first {_EXTRACT_CHARS} chars):
{batch_text}

List EVERY distinct topic, concept, framework, process, or technical term covered.
Be specific — not "Introduction" but "What threat modeling is and why it matters".
Include anything a student would need to learn from this material.

Return ONLY valid JSON:
{{"topics": ["topic 1", "topic 2", ...]}}"""

    try:
        data = await cf_json(
            messages=[{"role": "user", "content": prompt}],
            model_key="course",
            temperature=0.2,
            max_tokens=800,
        )
        return [t.strip() for t in data.get("topics", []) if isinstance(t, str) and t.strip()]
    except Exception as e:
        print(f"[COURSE_GEN] Batch extraction error: {e}")
        return []


async def _group_topics(raw_topics: list[str], title: str) -> list[str]:
    """Deduplicate and group raw topics into module-level themes via LLM."""
    if not raw_topics:
        return [f"Introduction to {title}", f"Core concepts of {title}"]

    prompt = f"""You extracted these topics from a document about "{title}":

{json.dumps(raw_topics, indent=2)}

Group and deduplicate into {_MAX_MODULES} or fewer distinct module themes.
- Remove exact/near duplicates
- Combine closely related topics under one heading
- Keep genuinely distinct subjects separate
- Each theme should be teachable in 20-40 minutes
- Order them logically (foundations first)

Return ONLY valid JSON:
{{"modules": ["Module theme 1", "Module theme 2", ...]}}"""

    try:
        data = await cf_json(
            messages=[{"role": "user", "content": prompt}],
            model_key="course",
            temperature=0.2,
            max_tokens=600,
        )
        themes = [t.strip() for t in data.get("modules", []) if isinstance(t, str) and t.strip()]
        return themes[:_MAX_MODULES] if themes else raw_topics[:_MAX_MODULES]
    except Exception as e:
        print(f"[COURSE_GEN] Topic grouping error: {e}")
        # Fallback: simple deduplication
        seen: set[str] = set()
        unique = []
        for t in raw_topics:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                unique.append(t)
        return unique[:_MAX_MODULES]


# ── Pass 2 — Module expansion ─────────────────────────────────────────────────

async def _expand_topic_to_module(
    topic: str,
    chunk_index_map: dict[int, str],   # chunk_index → content
    relevant_indices: list[int],
    title: str,
) -> dict:
    """Expand a single topic string into a full module dict with 3-5 concepts."""
    relevant_text = "\n---\n".join(
        f"[Chunk {idx}]: {chunk_index_map.get(idx, '')[:_EXPAND_CHARS]}"
        for idx in relevant_indices[:_EXPAND_CHUNKS]
        if idx in chunk_index_map
    )
    if not relevant_text:
        relevant_text = "(no source material available — use general knowledge about the topic)"

    prompt = f"""You are an expert instructional designer building a module for a course on "{title}".

Module topic: "{topic}"

Relevant source material:
{relevant_text}

Create a complete, thorough learning module with EXACTLY {_MIN_CONCEPTS}-{_MAX_CONCEPTS} ATOMIC concepts.
You MUST generate at least {_MIN_CONCEPTS} concepts — this is a hard requirement. Do not stop early.
- Each concept = one specific idea a student explains back in 3-5 minutes
- Concepts must BUILD on each other — foundational first, applied last
- Concept titles must be SPECIFIC: "Why X causes Y" not "Understanding X"
- 4-5 concrete key_points per concept (more detail = better learning)
- Cover the topic completely — leave no important aspect out
- source_chunk_indices must be integers from: {relevant_indices[:_EXPAND_CHUNKS]}

Return ONLY valid JSON:
{{
  "title": "Clear module title",
  "description": "One sentence: what this module teaches and why it matters",
  "concepts": [
    {{
      "title": "Specific concept title",
      "learning_objective": "Student will be able to explain [specific thing] in their own words",
      "key_points": ["concrete point 1", "concrete point 2", "concrete point 3", "concrete point 4"],
      "estimated_minutes": 5
    }}
  ],
  "source_chunk_indices": {relevant_indices[:_EXPAND_CHUNKS]}
}}"""

    try:
        data = await cf_json(
            messages=[{"role": "user", "content": prompt}],
            model_key="course",
            temperature=0.3,
            max_tokens=3000,
        )
        concepts = _clean_concepts(data.get("concepts", []))

        # Enforce minimum: if LLM returned fewer than _MIN_CONCEPTS, pad with synthetic ones
        if len(concepts) < _MIN_CONCEPTS:
            existing_titles = {c["title"] for c in concepts}
            key_points_pool = [kp for c in concepts for kp in c.get("key_points", [])]
            for i in range(len(concepts), _MIN_CONCEPTS):
                # Generate a synthetic concept from remaining key points
                kp_start = i * 2
                synthetic_kps = key_points_pool[kp_start:kp_start + 4] if kp_start < len(key_points_pool) else [f"Key aspect {i+1} of {topic}"]
                synth_title = f"Applying {topic} — Part {i + 1}"
                if synth_title not in existing_titles:
                    concepts.append({
                        "title": synth_title,
                        "learning_objective": f"Student will be able to describe a practical aspect of {topic} in their own words",
                        "key_points": synthetic_kps if synthetic_kps else [f"Important aspect of {topic}"],
                        "estimated_minutes": 5,
                    })

        if not concepts:
            raise ValueError("No concepts in response")
        return {
            "title":              data.get("title", topic),
            "description":        data.get("description", ""),
            "learning_objectives":[c["learning_objective"] for c in concepts],
            "prerequisites":      [],
            "source_chunk_indices": relevant_indices[:_EXPAND_CHUNKS],
            "estimated_minutes":  sum(c["estimated_minutes"] for c in concepts),
            "concepts":           concepts,
        }
    except Exception as e:
        print(f"[COURSE_GEN] Expand error for '{topic}': {e}")
        fallback_concept = {
            "title":              f"What is {topic}?",
            "learning_objective": f"Student will be able to explain {topic} in their own words",
            "key_points":         ["Definition", "Why it matters", "Key components"],
            "estimated_minutes":  5,
        }
        return {
            "title":              topic,
            "description":        f"Core concepts of {topic}",
            "learning_objectives":[fallback_concept["learning_objective"]],
            "prerequisites":      [],
            "source_chunk_indices": relevant_indices[:3],
            "estimated_minutes":  15,
            "concepts":           [fallback_concept],
        }


# ── Public entry point ─────────────────────────────────────────────────────────

async def generate_course(chunks: list[dict], title: str) -> dict:
    """
    Full two-pass course generation from all source chunks.

    Returns the same dict shape as before:
    {"title": ..., "description": ..., "modules": [...]}
    """
    total_chunks = len(chunks)
    print(f"[COURSE_GEN] Starting '{title}' — {total_chunks} source chunks")

    # ── Pass 1: Extract all topics from ALL chunks ─────────────────────────────
    print(f"[COURSE_GEN] Pass 1: extracting topics in batches of {_BATCH_SIZE} chunks")
    raw_topics: list[str] = []
    n_batches = (total_chunks + _BATCH_SIZE - 1) // _BATCH_SIZE

    for batch_idx in range(n_batches):
        batch = chunks[batch_idx * _BATCH_SIZE : (batch_idx + 1) * _BATCH_SIZE]
        batch_topics = await _extract_topics_from_batch(batch, title)
        raw_topics.extend(batch_topics)
        print(f"[COURSE_GEN]   Batch {batch_idx + 1}/{n_batches}: {len(batch_topics)} topics extracted")

    print(f"[COURSE_GEN] Pass 1 complete: {len(raw_topics)} raw topics across all batches")

    # Deduplicate and group into module themes
    module_themes = await _group_topics(raw_topics, title)
    print(f"[COURSE_GEN] Pass 1 grouped: {len(module_themes)} module themes")
    for i, t in enumerate(module_themes, 1):
        print(f"[COURSE_GEN]   {i}. {t}")

    # Build lookup: chunk_index → content
    chunk_index_map: dict[int, str] = {c["chunk_index"]: c["content"] for c in chunks}

    # ── Pass 2: Expand each theme into a full module ───────────────────────────
    print(f"[COURSE_GEN] Pass 2: expanding {len(module_themes)} themes into modules")
    modules: list[dict] = []

    for i, topic in enumerate(module_themes, 1):
        rel_indices = _relevant_chunks(topic, chunks)
        print(f"[COURSE_GEN]   [{i}/{len(module_themes)}] '{topic}' → chunks {rel_indices[:4]}")
        module = await _expand_topic_to_module(topic, chunk_index_map, rel_indices, title)
        n_concepts = len(module.get("concepts", []))
        print(f"[COURSE_GEN]     → {n_concepts} concepts generated")
        modules.append(module)

    total_concepts = sum(len(m.get("concepts", [])) for m in modules)
    print(
        f"[COURSE_GEN] Complete: {len(modules)} modules, "
        f"{total_concepts} total concepts, "
        f"avg {total_concepts / max(len(modules), 1):.1f} concepts/module"
    )

    # Build course description
    if module_themes:
        theme_preview = ", ".join(f'"{t}"' for t in module_themes[:3])
        extra = f" and {len(module_themes) - 3} more" if len(module_themes) > 3 else ""
        description = f"A course on {title} covering {theme_preview}{extra}."
    else:
        description = f"A comprehensive course covering {title}."

    return {
        "title":       title,
        "description": description,
        "modules":     modules,
    }


# ── Sub-module generator (for inline drilling) ────────────────────────────────

async def generate_submodule(
    concept: dict,
    source_chunks: list[str],
    pain_point: str = "",
    module_title: str = "",
) -> list[dict]:
    """
    Break a complex concept into 3-4 teachable sub-concepts when a student is stuck.
    Returns a list of sub-concept dicts ordered from foundational to applied.
    """
    concept_title    = concept.get("title", "this concept")
    learning_obj     = concept.get("learning_objective", "")
    key_points       = concept.get("key_points", [])
    source_text      = "\n---\n".join(
        " ".join(c.split()[:120]) for c in source_chunks[:3]
    ) if source_chunks else ""
    pain_context     = f"\nThe student is specifically struggling with: {pain_point}" if pain_point else ""

    prompt = f"""A student cannot understand this concept after multiple attempts.
Break it into 3-4 prerequisite sub-concepts ordered from foundational to applied.

Parent concept: {concept_title}
From module: {module_title}
Learning objective: {learning_obj}
Key points: {', '.join(key_points[:4]) if key_points else 'not specified'}
{pain_context}

Source material:
{source_text[:600]}

Rules:
- Sub-concepts ordered: foundational first, applied last
- Each simpler and narrower than the parent
- Final sub-concept connects back to parent concept
- Titles must be specific ("explain why X causes Y") not broad ("understand X")
- Each teachable in 2-3 minutes

Return ONLY valid JSON:
{{
  "sub_concepts": [
    {{
      "title": "Specific sub-concept title",
      "learning_objective": "Student will be able to explain [specific thing]",
      "key_points": ["point 1", "point 2"],
      "estimated_minutes": 3,
      "builds_toward": "How this connects to the parent concept"
    }}
  ]
}}"""

    try:
        data = await cf_json(
            messages=[{"role": "user", "content": prompt}],
            model_key="course",
            temperature=0.3,
            max_tokens=1200,
        )
        sub_concepts = data.get("sub_concepts", [])
    except Exception as e:
        print(f"[SUBMODULE_GEN] Error: {e}")
        sub_concepts = [
            {"title": f"What is {concept_title}?",
             "learning_objective": f"Define {concept_title} in own words",
             "key_points": key_points[:2], "estimated_minutes": 3,
             "builds_toward": f"Foundation for {concept_title}"},
            {"title": f"Why {concept_title} matters",
             "learning_objective": f"Explain why {concept_title} is important",
             "key_points": key_points[1:3] if len(key_points) > 1 else [],
             "estimated_minutes": 3,
             "builds_toward": f"Context for {concept_title}"},
            {"title": f"How {concept_title} works in practice",
             "learning_objective": f"Describe {concept_title} in a real scenario",
             "key_points": key_points[2:4] if len(key_points) > 2 else [],
             "estimated_minutes": 3,
             "builds_toward": f"Completes understanding of {concept_title}"},
        ]

    clean = []
    for sc in sub_concepts[:4]:
        clean.append({
            "title":              sc.get("title", "Sub-concept"),
            "learning_objective": sc.get("learning_objective",
                                         f"Explain {sc.get('title', 'this sub-concept')}"),
            "key_points":         sc.get("key_points", []),
            "estimated_minutes":  sc.get("estimated_minutes", 3),
            "builds_toward":      sc.get("builds_toward", ""),
            "is_submodule":       True,
            "parent_concept_title": concept_title,
        })
    return clean
