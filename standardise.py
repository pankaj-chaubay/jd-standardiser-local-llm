"""
Standardise job descriptions into one template with a local LLM (Ollama).

Why local: job descriptions often carry names, phone numbers and internal details.
Running the model on your own machine means no text leaves the company network,
which keeps the process simple under GDPR. Personal data is also removed before
the text reaches the model, and every result is marked for human review.

Steps
1. Read every .txt file in ./samples (fictional job descriptions, English and German).
2. Remove personal data: e-mail addresses, phone numbers and contact names.
3. Ask the local model for a fixed JSON structure (title, job family, level, location,
   work model, language, responsibilities, requirements, languages required).
4. Validate the JSON against the template. Anything that fails goes to the review list.
5. Write ./output/standardised.csv and ./output/standardised.json.

Run with a local model (install Ollama from ollama.com, then `ollama pull llama3.1:8b`):
    python standardise.py
Run without a model, to test the pipeline (simple keyword rules instead of the LLM):
    python standardise.py --dry-run
"""
import argparse
import json
import re
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "output"
OUT.mkdir(exist_ok=True)
OLLAMA_URL = "http://localhost:11434/api/chat"

TEMPLATE = {
    "type": "object",
    "properties": {
        "job_title": {"type": "string"},
        "job_family": {"type": "string", "enum": ["HR Analytics", "HR Business Partnering", "Payroll",
                                                   "Talent Acquisition", "Other HR", "Not HR"]},
        "level": {"type": "string", "enum": ["Junior", "Professional", "Senior", "Lead / Manager"]},
        "location": {"type": "string"},
        "work_model": {"type": "string", "enum": ["On-site", "Hybrid", "Remote", "Not stated"]},
        "posting_language": {"type": "string", "enum": ["English", "German"]},
        "min_years_experience": {"type": ["integer", "null"]},
        "responsibilities": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "requirements": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "languages_required": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["job_title", "job_family", "level", "location", "work_model", "posting_language",
                 "min_years_experience", "responsibilities", "requirements", "languages_required"],
}

PROMPT = """You standardise job descriptions for an HR team.
Return only JSON that matches the schema. Write responsibilities and requirements in short
English phrases (max 5 each), even if the posting is in German. Use "Not stated" or null when
the posting does not say something. Do not invent details.

Job description:
{text}"""

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)\d{3,4}[\s-]?\d{3,5}")
CONTACT = re.compile(r"(?i)(contact|ansprechpartner(?:in)?|questions\?\s*contact)\s*:?\s*([A-ZÄÖÜ][a-zäöüß]+\s+[A-ZÄÖÜ][a-zäöüß]+)")


def scrub(text: str) -> tuple[str, int]:
    """Remove personal data before the text goes to the model. Returns text and number of removals."""
    n = 0
    text, k = EMAIL.subn("[email removed]", text); n += k
    text, k = PHONE.subn("[phone removed]", text); n += k
    text, k = CONTACT.subn(lambda m: m.group(1) + ": [name removed]", text); n += k
    return text, n


def ask_llm(text: str, model: str) -> dict:
    body = {"model": model, "stream": False, "format": TEMPLATE, "options": {"temperature": 0},
            "messages": [{"role": "user", "content": PROMPT.format(text=text)}]}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


def rules_stub(text: str) -> dict:
    """Keyword rules used by --dry-run, so the pipeline can be tested without a model."""
    t = text.lower()
    family = ("HR Analytics" if "analytics" in t or "analyst" in t else
              "Payroll" if "payroll" in t else
              "Talent Acquisition" if "recruit" in t or "talent acquisition" in t else
              "HR Business Partnering" if "business partner" in t else "Other HR")
    years = re.search(r"(\d+)\+?\s*(?:years|yrs|jahre)", t)
    return {
        "job_title": text.strip().splitlines()[0][:80],
        "job_family": family,
        "level": "Senior" if "senior" in t or (years and int(years.group(1)) >= 5) else "Professional",
        "location": next((c for c in ["Munich", "Hamburg", "Berlin", "Germany"] if c.lower() in t), "Not stated"),
        "work_model": "Remote" if "remote" in t else "Hybrid" if "hybrid" in t else "Not stated",
        "posting_language": "German" if re.search(r"\b(wir|ihre|und)\b", t) else "English",
        "min_years_experience": int(years.group(1)) if years else None,
        "responsibilities": [],
        "requirements": [],
        "languages_required": [l for l, keys in {"German": ["german", "deutsch"], "English": ["english", "englisch"]}.items()
                               if any(k in t for k in keys)],
    }


def validate(rec: dict) -> list[str]:
    problems = [f"missing {k}" for k in TEMPLATE["required"] if k not in rec]
    for k, spec in TEMPLATE["properties"].items():
        if k in rec and "enum" in spec and rec[k] not in spec["enum"]:
            problems.append(f"{k} not in template: {rec[k]}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="use keyword rules instead of the LLM")
    ap.add_argument("--model", default="llama3.1:8b")
    args = ap.parse_args()

    rows = []
    for f in sorted((HERE / "samples").glob("*.txt")):
        clean, removed = scrub(f.read_text(encoding="utf-8"))
        rec = rules_stub(clean) if args.dry_run else ask_llm(clean, args.model)
        problems = validate(rec)
        rows.append({"file": f.name, **rec, "personal_data_removed": removed,
                     "validation": "; ".join(problems) or "ok", "human_review": "pending"})

    df = pd.DataFrame(rows)
    df.to_json(OUT / "standardised.json", orient="records", indent=2, force_ascii=False)
    flat = df.copy()
    for c in ["responsibilities", "requirements", "languages_required"]:
        flat[c] = flat[c].apply(lambda v: " | ".join(v))
    flat.to_csv(OUT / "standardised.csv", index=False)
    print(flat[["file", "job_family", "level", "location", "work_model", "posting_language",
                "min_years_experience", "languages_required", "personal_data_removed", "validation"]].to_string(index=False))


if __name__ == "__main__":
    main()
