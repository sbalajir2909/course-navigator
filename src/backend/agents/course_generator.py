"""
agents/course_generator.py
Generates structured course from document chunks using Groq (llama-3.3-70b).
"""
from __future__ import annotations
import os, json
from groq import Groq
from pydantic import BaseModel

class Module(BaseModel):
    title: str
    description: str
    learning_objectives: list[str]
    prerequisites: list[str]
    source_chunk_indices: list[int]
    estimated_minutes: int

class CourseStructure(BaseModel):
    title: str
    description: str
    modules: list[Module]

async def generate_course(chunks: list[dict], title: str) -> dict:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # Limit to first 15 chunks and truncate each to stay under TPM limit
    chunk_text = "\n\n".join([f"[Chunk {c['chunk_index']}]: {c['content'][:300]}" for c in chunks[:15]])

    prompt = f"""You are an expert instructional designer. Given the following document chunks, generate a structured course.

Course Title: {title}

Document Content:
{chunk_text}

Generate a comprehensive course with 6-12 modules. Return ONLY valid JSON in this exact format with no markdown, no explanation:
{{
  "title": "{title}",
  "description": "2-3 sentence course overview",
  "modules": [
    {{
      "title": "Module title",
      "description": "What this module covers",
      "learning_objectives": ["Student will be able to...", "Student will understand..."],
      "prerequisites": [],
      "source_chunk_indices": [0, 1, 2],
      "estimated_minutes": 30
    }}
  ]
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    data = json.loads(raw)
    course = CourseStructure(**data)
    return course.dict()
