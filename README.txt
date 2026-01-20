# Skill Gap Suggestions - Starter Kit

## Files
- skills_taxonomy.json (341 skills, role-tagged)
- supabase_schema.sql (tables + RLS policies)
- api_main.py (FastAPI /analyze endpoint)
- SkillGapPage.tsx (React UI to paste resume + job)

## Quick start (API)
1) Create venv + install:
   pip install fastapi uvicorn pydantic

2) Run:
   export SKILLS_TAXONOMY_PATH=skills_taxonomy.json
   uvicorn api_main:app --reload --port 8000

## Quick start (React)
- Set env:
  VITE_ML_API_URL=http://localhost:8000
- Render <SkillGapPage />

## Next upgrades
- Add PDF/DOCX parsing (server-side)
- Add embeddings-based semantic matching
- Persist analyses in Supabase via service role key from API
