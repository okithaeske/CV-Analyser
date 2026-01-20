import React, { useMemo, useRef, useState } from "react";
// Use Vite worker plugin for PDF.js worker
// @ts-ignore - Vite returns a Worker constructor for ?worker imports
import PDFWorker from "pdfjs-dist/build/pdf.worker.mjs?worker";
import { useAuth } from "./auth/AuthProvider";
import "./index.css";

type SkillOut = {
  skill_id: string;
  skill: string;
  category: string;
  found_as?: string[];
  confidence?: number;
  importance?: number;
  priority?: "High" | "Medium" | "Low";
  reason?: string;
  suggested_path?: string[];
};

type AnalyzeResponse = {
  matched: SkillOut[];
  missing: SkillOut[];
  summary: { target_role: string; matched_count: number; missing_count: number };
};

const PriorityBadge: React.FC<{ p: "High" | "Medium" | "Low" }> = ({ p }) => {
  const cls =
    p === "High"
      ? "bg-red-100 text-red-800"
      : p === "Medium"
      ? "bg-amber-100 text-amber-800"
      : "bg-emerald-100 text-emerald-800";
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>{p}</span>;
};

export default function SkillGapPage() {
  const { session } = useAuth();
  const [targetRole, setTargetRole] = useState<"backend" | "fullstack" | "cloud_devops">("backend");
  const [resumeText, setResumeText] = useState("");
  const [jobText, setJobText] = useState("");
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pdfStatus, setPdfStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  let pdfWorkerInstance: Worker | null = null;

  const missingByPriority = useMemo(() => {
    const out = { High: [] as SkillOut[], Medium: [] as SkillOut[], Low: [] as SkillOut[] };
    (data?.missing ?? []).forEach((s) => out[(s.priority ?? "Low") as "High" | "Medium" | "Low"].push(s));
    return out;
  }, [data]);

  async function runAnalyze() {
    setLoading(true);
    setErr(null);
    setData(null);
    try {
      const res = await fetch((import.meta as any).env.VITE_ML_API_URL + "/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
        },
        body: JSON.stringify({ resume_text: resumeText, job_text: jobText, target_role: targetRole }),
      });
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const json = (await res.json()) as AnalyzeResponse;
      setData(json);
    } catch (e: any) {
      setErr(e?.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function extractPdfText(file: File): Promise<string> {
    // Lazy import pdfjs to keep initial bundle small
    const pdfjsLib: any = await import("pdfjs-dist");
    // Provide a proper Worker instance via Vite's ?worker import
    if (!pdfWorkerInstance) {
      // @ts-ignore - constructor provided by Vite worker plugin
      pdfWorkerInstance = new PDFWorker();
    }
    pdfjsLib.GlobalWorkerOptions.workerPort = pdfWorkerInstance;

    const arrayBuffer = await file.arrayBuffer();
    const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
    const pdf = await loadingTask.promise;
    let out: string[] = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      // @ts-ignore - runtime object has items
      const textContent = await page.getTextContent();
      // Concatenate strings with spaces to preserve word boundaries
      const pageText = (textContent.items || [])
        .map((it: any) => (typeof it?.str === "string" ? it.str : ""))
        .join(" ");
      out.push(pageText);
    }
    // Normalize whitespace a bit
    return out.join("\n\n").replace(/\s+/g, " ").trim();
  }

  async function onPdfSelected(file?: File | null) {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setPdfStatus("Please choose a PDF file (.pdf)");
      return;
    }
    setPdfStatus("Extracting text from PDF...");
    try {
      const text = await extractPdfText(file);
      if (!text || text.length < 5) {
        setPdfStatus("Couldn’t extract text from this PDF");
        return;
      }
      // Append or replace? Replace to keep it clean.
      setResumeText(text);
      setPdfStatus(`Loaded: ${file.name}`);
    } catch (e: any) {
      setPdfStatus(e?.message || "Failed to read PDF");
    }
  }

  return (
    <div className="mx-auto max-w-6xl p-6">
      <h1 className="text-2xl font-bold">Skill Gap Analyzer</h1>
      <p className="mt-1 text-sm text-gray-600">
        Paste your resume + a job description → get matched skills, missing skills, and a learning roadmap.
      </p>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border bg-white p-4 shadow-sm md:col-span-1">
          <label className="text-sm font-semibold">Target Role</label>
          <select
            className="mt-2 w-full rounded-xl border px-3 py-2"
            value={targetRole}
            onChange={(e) => setTargetRole(e.target.value as any)}
          >
            <option value="backend">Backend Engineer</option>
            <option value="fullstack">Fullstack Engineer</option>
            <option value="cloud_devops">Cloud/DevOps Engineer</option>
          </select>

          <button
            onClick={runAnalyze}
            disabled={
              loading ||
              (pdfStatus !== null && pdfStatus.toLowerCase().includes("extracting")) ||
              resumeText.trim().length < 30 ||
              jobText.trim().length < 30
            }
            className="mt-4 w-full rounded-xl bg-black px-4 py-2 text-white disabled:opacity-40"
          >
            {loading ? "Analyzing..." : "Analyze"}
          </button>

          {err && <p className="mt-3 text-sm text-red-600">{err}</p>}

          {data && (
            <div className="mt-4 rounded-xl bg-gray-50 p-3 text-sm">
              <div className="flex justify-between">
                <span>Matched</span>
                <span className="font-semibold">{data.summary.matched_count}</span>
              </div>
              <div className="flex justify-between">
                <span>Missing</span>
                <span className="font-semibold">{data.summary.missing_count}</span>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-2xl border bg-white p-4 shadow-sm md:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <label className="text-sm font-semibold">Resume Text</label>
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(e) => onPdfSelected(e.target.files?.[0])}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="rounded-lg border px-3 py-1 text-sm hover:bg-gray-50"
              >
                Attach PDF
              </button>
            </div>
          </div>
          <textarea
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            className="mt-2 h-40 w-full rounded-xl border p-3 text-sm"
            placeholder="Paste your resume text here..."
          />
          {pdfStatus && <p className="mt-2 text-xs text-gray-600">{pdfStatus}</p>}

          <label className="mt-4 block text-sm font-semibold">Job Description</label>
          <textarea
            value={jobText}
            onChange={(e) => setJobText(e.target.value)}
            className="mt-2 h-40 w-full rounded-xl border p-3 text-sm"
            placeholder="Paste the job description here..."
          />
        </div>
      </div>

      {data && (
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <h2 className="text-lg font-bold">Missing Skills</h2>

            {(["High", "Medium", "Low"] as const).map((p) => (
              <div key={p} className="mt-4">
                <div className="flex items-center gap-2">
                  <PriorityBadge p={p} />
                  <span className="text-sm font-semibold">{p} priority</span>
                </div>

                <div className="mt-2 space-y-3">
                  {missingByPriority[p].length === 0 ? (
                    <p className="text-sm text-gray-500">None</p>
                  ) : (
                    missingByPriority[p].map((s) => (
                      <div key={s.skill_id} className="rounded-xl bg-gray-50 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="font-semibold">{s.skill}</div>
                            <div className="text-xs text-gray-600">{s.category}</div>
                          </div>
                          <div className="text-xs text-gray-600">importance {s.importance?.toFixed(2)}</div>
                        </div>
                        {s.suggested_path?.length ? (
                          <ol className="mt-2 list-decimal pl-5 text-sm text-gray-700">
                            {s.suggested_path.map((step) => (
                              <li key={step}>{step}</li>
                            ))}
                          </ol>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <h2 className="text-lg font-bold">Matched Skills</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {data.matched.length === 0 ? (
                <p className="text-sm text-gray-500">No matches found yet — try adding more detail to your resume.</p>
              ) : (
                data.matched.map((s) => (
                  <div key={s.skill_id} className="rounded-xl bg-gray-50 p-3">
                    <div className="font-semibold">{s.skill}</div>
                    <div className="text-xs text-gray-600">{s.category}</div>
                    {s.found_as?.length ? (
                      <div className="mt-2 text-xs text-gray-700">
                        found as: <span className="font-mono">{s.found_as.join(", ")}</span>
                      </div>
                    ) : null}
                    {typeof s.confidence === "number" ? (
                      <div className="mt-1 text-xs text-gray-600">confidence {s.confidence.toFixed(2)}</div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
