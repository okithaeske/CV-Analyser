from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware


def _parse_cors(origins_str: str):
    s = (origins_str or "").strip()
    if not s:
        return []
    if s == "*":
        return ["*"]
    return [o.strip() for o in s.split(",") if o.strip()]

# Comma-separated list of allowed origins, e.g.
#   CORS_ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:5173
CORS_ALLOWED_ORIGINS = _parse_cors(os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173"))
# Optional regex to match multiple origins (e.g., Vercel previews)
CORS_ALLOWED_ORIGIN_REGEX = os.getenv("CORS_ALLOWED_ORIGIN_REGEX")

# --------- Load taxonomy ---------
TAXONOMY_PATH = os.getenv("SKILLS_TAXONOMY_PATH", "skills_taxonomy.json")
taxonomy = json.loads(Path(TAXONOMY_PATH).read_text(encoding="utf-8"))
skills = taxonomy["skills"]

# Build lookup: canonical id -> aliases, role tags, etc.
SKILL_BY_ID = {s["id"]: s for s in skills}

# Build regex patterns per skill
def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9+\-#/\.\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def compile_patterns() -> Dict[str, re.Pattern]:
    patterns: Dict[str, re.Pattern] = {}
    for s in skills:
        aliases = s["aliases"]
        escaped = [re.escape(a.lower()) for a in aliases]
        # boundary-ish match; allows symbols inside skill tokens
        pattern = r"(?<![a-z0-9])(" + "|".join(escaped) + r")(?![a-z0-9])"
        patterns[s["id"]] = re.compile(pattern, re.IGNORECASE)
    return patterns

PATTERNS = compile_patterns()

@dataclass
class SkillFound:
    skill_id: str
    found_as: List[str]
    confidence: float

def extract_skills(text: str, role: str) -> Dict[str, SkillFound]:
    t = normalize_text(text)
    found: Dict[str, SkillFound] = {}

    for skill_id, pat in PATTERNS.items():
        meta = SKILL_BY_ID[skill_id]
        if role not in meta.get("roles", []):
            continue

        hits = list({m.group(1) for m in pat.finditer(t)})
        if hits:
            # Simple confidence: more distinct hits => higher
            conf = min(1.0, 0.55 + 0.08 * len(hits))
            found[skill_id] = SkillFound(skill_id=skill_id, found_as=sorted(hits), confidence=conf)

    return found

def importance_score(job_text: str, skill_id: str) -> float:
    jt = normalize_text(job_text)
    meta = SKILL_BY_ID[skill_id]
    aliases = meta["aliases"]

    # Count occurrences across aliases
    count = 0
    for a in aliases:
        a_norm = normalize_text(a)
        count += len(re.findall(rf"(?<![a-z0-9]){re.escape(a_norm)}(?![a-z0-9])", jt))

    base = min(1.0, 0.25 + 0.12 * count)

    required_words = ["required", "must", "essential", "mandatory", "need to", "strongly preferred"]
    canonical = normalize_text(meta["canonical_name"])

    for rw in required_words:
        # if skill appears within ~100 chars of required-ish words, boost
        if re.search(rf"{rw}.{{0,110}}{re.escape(canonical)}|{re.escape(canonical)}.{{0,110}}{rw}", jt):
            base = min(1.0, base + 0.25)
            break

    # Core skills slightly boosted
    if meta.get("level") == "core":
        base = min(1.0, base + 0.1)

    return base

def priority(imp: float) -> str:
    if imp >= 0.78:
        return "High"
    if imp >= 0.55:
        return "Medium"
    return "Low"

def suggested_path(skill_id: str) -> List[str]:
    # Lightweight roadmap templates by category
    meta = SKILL_BY_ID[skill_id]
    cat = meta.get("category","")

    templates = {
        "Cloud (AWS)": ["Cloud basics", "IAM permissions", "Networking basics (VPC)", "Deploy a small API", "Monitoring + cost basics"],
        "Cloud (Azure)": ["Cloud basics", "Identity (Entra ID)", "Networking basics (VNet)", "Deploy a Function/App", "Monitoring + cost basics"],
        "DevOps Fundamentals": ["Git workflow", "Containers", "CI pipeline", "CD pipeline", "Observability basics"],
        "Auth & Security": ["Threat basics", "OAuth/JWT", "Secure storage", "OWASP checks", "Audit logging"],
        "Databases": ["Schema design", "Indexes", "Transactions", "Query tuning", "Backup/restore basics"],
        "APIs & Integration": ["REST design", "Validation", "Auth", "Docs (OpenAPI)", "Performance + caching"],
        "Frontend Concepts": ["Core fundamentals", "Component patterns", "State management", "Testing", "Performance + a11y"],
        "Architecture & Patterns": ["Baseline design", "Reliability patterns", "Scaling", "Tradeoffs", "Hands-on refactor"],
    }
    return templates.get(cat, ["Learn fundamentals", "Build a small project using it", "Add a portfolio example"])

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
if CORS_ALLOWED_ORIGIN_REGEX:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=CORS_ALLOWED_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    resume_sk = extract_skills(req.resume_text, req.target_role)
    job_sk = extract_skills(req.job_text, req.target_role)

    matched_ids = sorted(set(resume_sk.keys()) & set(job_sk.keys()))
    missing_ids = sorted(set(job_sk.keys()) - set(resume_sk.keys()))

    matched = []
    for sid in matched_ids:
        meta = SKILL_BY_ID[sid]
        matched.append(SkillOut(
            skill_id=sid,
            skill=meta["canonical_name"],
            category=meta["category"],
            found_as=resume_sk[sid].found_as,
            confidence=round(resume_sk[sid].confidence, 2),
        ))

    ranked_missing: List[Tuple[str, float]] = []
    for sid in missing_ids:
        imp = importance_score(req.job_text, sid)
        ranked_missing.append((sid, imp))
    ranked_missing.sort(key=lambda x: x[1], reverse=True)

    missing = []
    for sid, imp in ranked_missing:
        meta = SKILL_BY_ID[sid]
        missing.append(SkillOut(
            skill_id=sid,
            skill=meta["canonical_name"],
            category=meta["category"],
            importance=round(imp, 2),
            priority=priority(imp),
            reason="Ranked by frequency + 'required/must' proximity in the job text (heuristic).",
            suggested_path=suggested_path(sid)
        ))

    resp = AnalyzeResponse(
        matched=matched,
        missing=missing,
        summary={
            "target_role": req.target_role,
            "matched_count": len(matched),
            "missing_count": len(missing),
        }
    )
    return resp
