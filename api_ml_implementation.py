from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ML Imports
from sentence_transformers import SentenceTransformer, util
import torch

# --------- Load taxonomy ---------
TAXONOMY_PATH = os.getenv("SKILLS_TAXONOMY_PATH", "skills_taxonomy.json")
taxonomy = json.loads(Path(TAXONOMY_PATH).read_text(encoding="utf-8"))
skills = taxonomy["skills"]

# Build lookup: canonical id -> aliases, role tags, etc.
SKILL_BY_ID = {s["id"]: s for s in skills}

# Config
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
ML_MODEL_NAME = os.getenv("ML_MODEL_NAME", "all-MiniLM-L6-v2")
# Threshold for semantic match
# 0.35-0.4 is usually a good starting point for MiniLM cosine similarity on short text
try:
    ML_SIMILARITY_THRESHOLD = float(os.getenv("ML_SIMILARITY_THRESHOLD", "0.35"))
except ValueError:
    ML_SIMILARITY_THRESHOLD = 0.35

print(f"Loading ML model: {ML_MODEL_NAME}...")
# Load model (downloads on first run)
model = SentenceTransformer(ML_MODEL_NAME)
print("Model loaded.")

# --------- Pre-compute Skill Embeddings ---------
# We encode every alias of every skill to find the best matching variant.
skill_variants = []
skill_variant_map = []  # Tuple of (skill_id, variant_text)

for s in skills:
    sid = s["id"]
    # Include canonical name
    name = s["canonical_name"]
    skill_variants.append(name)
    skill_variant_map.append((sid, name))

    # Include aliases
    for alias in s["aliases"]:
        skill_variants.append(alias)
        skill_variant_map.append((sid, alias))

print(f"Encoding {len(skill_variants)} skill variants...")
SKILL_EMBEDDINGS = model.encode(skill_variants, convert_to_tensor=True)
print("Skill taxonomy encoded.")


@dataclass
class SkillFound:
    skill_id: str
    found_as: List[str]
    confidence: float


def normalize_text(text: str) -> str:
    # Basic cleanup
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(text: str) -> List[str]:
    # Split into sentences/chunks approximately
    # Split by . ! ? followed by whitespace or newline
    raw_chunks = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    for c in raw_chunks:
        c = c.strip()
        if len(c) > 5:  # Ignore very short garbage
            chunks.append(c)
    return chunks


def extract_skills(text: str, role: str) -> Dict[str, SkillFound]:
    text = normalize_text(text)
    chunks = chunk_text(text)

    if not chunks:
        return {}

    # Encode chunks: (M, 384)
    chunk_embeddings = model.encode(chunks, convert_to_tensor=True)

    # Compute cosine similarity: (M, N_skills)
    # chunk_embeddings is 'query', SKILL_EMBEDDINGS is 'corpus'
    # util.cos_sim returns (QuerySize, CorpusSize)
    scores = util.cos_sim(chunk_embeddings, SKILL_EMBEDDINGS)

    # We want to find: for each skill variant, what was the max score in the text?
    # Max over chunks (dim 0) -> (N_skills,)
    max_scores_per_variant, _ = torch.max(scores, dim=0)

    # Process results
    found: Dict[str, SkillFound] = {}

    # Iterate over all variants and their scores
    # We need to map back to skill_id and aggregate

    # Group by skill_id
    skill_scores: Dict[
        str, List[Tuple[float, str]]
    ] = {}  # sid -> [(score, variant_text)]

    # Move to cpu for iteration
    max_scores_list = max_scores_per_variant.tolist()

    for idx, score in enumerate(max_scores_list):
        if score < ML_SIMILARITY_THRESHOLD:
            continue

        sid, variant = skill_variant_map[idx]

        # Check role constraint
        meta = SKILL_BY_ID[sid]
        if role not in meta.get("roles", []):
            continue

        if sid not in skill_scores:
            skill_scores[sid] = []
        skill_scores[sid].append((score, variant))

    # Construct SkillFound objects
    for sid, matches in skill_scores.items():
        # Best confidence for this skill
        best_conf = max(m[0] for m in matches)
        # Unique variants found
        variants = sorted(list(set(m[1] for m in matches)))

        # Limit confidence to 1.0
        final_conf = min(1.0, best_conf)

        found[sid] = SkillFound(skill_id=sid, found_as=variants, confidence=final_conf)

    return found


def importance_score(job_text: str, skill_id: str, base_confidence: float) -> float:
    # Start with the ML confidence from the job description match
    base = base_confidence

    # Boost if explicit "required" keywords are near the canonical name or aliases (Regex fallback)
    # This ensures that "Must have Python" gets higher priority than just "Python is nice"
    # even if semantic match is similar.

    meta = SKILL_BY_ID[skill_id]
    names = [meta["canonical_name"]] + meta["aliases"]

    jt_lower = job_text.lower()
    required_words = [
        "required",
        "must",
        "essential",
        "mandatory",
        "need to",
        "strongly preferred",
    ]

    boost = 0.0
    for name in names:
        n_lower = name.lower()
        # Escaped regex for safe matching
        pattern = re.escape(n_lower)

        # Check proximity
        for rw in required_words:
            # Look for regex match with context
            if re.search(rf"{rw}.{{0,110}}{pattern}|{pattern}.{{0,110}}{rw}", jt_lower):
                boost = 0.25
                break
        if boost > 0:
            break

    final_score = min(1.0, base + boost)

    # Core skills slightly boosted
    if meta.get("level") == "core":
        final_score = min(1.0, final_score + 0.1)

    return final_score


def priority(imp: float) -> str:
    if imp >= 0.78:
        return "High"
    if imp >= 0.55:
        return "Medium"
    return "Low"


def suggested_path(skill_id: str) -> List[str]:
    # Lightweight roadmap templates by category
    meta = SKILL_BY_ID[skill_id]
    cat = meta.get("category", "")

    templates = {
        "Cloud (AWS)": [
            "Cloud basics",
            "IAM permissions",
            "Networking basics (VPC)",
            "Deploy a small API",
            "Monitoring + cost basics",
        ],
        "Cloud (Azure)": [
            "Cloud basics",
            "Identity (Entra ID)",
            "Networking basics (VNet)",
            "Deploy a Function/App",
            "Monitoring + cost basics",
        ],
        "DevOps Fundamentals": [
            "Git workflow",
            "Containers",
            "CI pipeline",
            "CD pipeline",
            "Observability basics",
        ],
        "Auth & Security": [
            "Threat basics",
            "OAuth/JWT",
            "Secure storage",
            "OWASP checks",
            "Audit logging",
        ],
        "Databases": [
            "Schema design",
            "Indexes",
            "Transactions",
            "Query tuning",
            "Backup/restore basics",
        ],
        "APIs & Integration": [
            "REST design",
            "Validation",
            "Auth",
            "Docs (OpenAPI)",
            "Performance + caching",
        ],
        "Frontend Concepts": [
            "Core fundamentals",
            "Component patterns",
            "State management",
            "Testing",
            "Performance + a11y",
        ],
        "Architecture & Patterns": [
            "Baseline design",
            "Reliability patterns",
            "Scaling",
            "Tradeoffs",
            "Hands-on refactor",
        ],
    }
    return templates.get(
        cat,
        [
            "Learn fundamentals",
            "Build a small project using it",
            "Add a portfolio example",
        ],
    )


class AnalyzeRequest(BaseModel):
    resume_text: str = Field(..., min_length=30)
    job_text: str = Field(..., min_length=30)
    target_role: str = Field(..., pattern="^(backend|fullstack|cloud_devops)$")


class SkillOut(BaseModel):
    skill_id: str
    skill: str
    category: str
    found_as: Optional[List[str]] = None
    confidence: Optional[float] = None
    importance: Optional[float] = None
    priority: Optional[str] = None
    reason: Optional[str] = None
    suggested_path: Optional[List[str]] = None


class AnalyzeResponse(BaseModel):
    matched: List[SkillOut]
    missing: List[SkillOut]
    summary: dict


app = FastAPI(title="Skill Gap Analyzer", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "model": ML_MODEL_NAME}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    resume_sk = extract_skills(req.resume_text, req.target_role)
    job_sk = extract_skills(req.job_text, req.target_role)

    matched_ids = sorted(set(resume_sk.keys()) & set(job_sk.keys()))
    missing_ids = sorted(set(job_sk.keys()) - set(resume_sk.keys()))

    matched = []
    for sid in matched_ids:
        meta = SKILL_BY_ID[sid]
        matched.append(
            SkillOut(
                skill_id=sid,
                skill=meta["canonical_name"],
                category=meta["category"],
                found_as=resume_sk[sid].found_as,
                confidence=round(resume_sk[sid].confidence, 2),
            )
        )

    ranked_missing: List[Tuple[str, float]] = []
    for sid in missing_ids:
        # Pass the ML confidence of the skill found in the job text
        base_conf = job_sk[sid].confidence
        imp = importance_score(req.job_text, sid, base_conf)
        ranked_missing.append((sid, imp))
    ranked_missing.sort(key=lambda x: x[1], reverse=True)

    missing = []
    for sid, imp in ranked_missing:
        meta = SKILL_BY_ID[sid]
        missing.append(
            SkillOut(
                skill_id=sid,
                skill=meta["canonical_name"],
                category=meta["category"],
                importance=round(imp, 2),
                priority=priority(imp),
                reason="Analyzed via ML semantic similarity + requirement context.",
                suggested_path=suggested_path(sid),
            )
        )

    resp = AnalyzeResponse(
        matched=matched,
        missing=missing,
        summary={
            "target_role": req.target_role,
            "matched_count": len(matched),
            "missing_count": len(missing),
        },
    )
    return resp
