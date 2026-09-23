"""
MediCare Assist — mock prototype (Flask version)

Security-assessment prototype only. All policy text and eligibility
results are mock/fake data. No real backend, no real citizen data,
no write operations.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000
"""
from flask import Flask, request, jsonify, render_template
import time
import requests

app = Flask(__name__)

# ---- Local LLM (Ollama) config ----
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:14b"  # change to whatever you've pulled, e.g. "mistral", "qwen2.5", 'llama3.2'

SYSTEM_PROMPT = (
    "You are MediCare Assist, a prototype government chatbot. Answer the "
    "citizen's question using ONLY the policy excerpts provided below. "
    "Do not invent facts, figures, or eligibility rules that are not in the "
    "excerpts. If the excerpts don't cover the question, say you don't have "
    "that information and suggest a human handoff. Keep answers to 2-3 "
    "sentences, plain language, no markdown."
)


def call_ollama(question: str, docs: list) -> str:
    """Send retrieved doc snippets + the question to a local Ollama model.
    Raises requests.exceptions.RequestException if Ollama isn't reachable."""
    context = "\n\n".join(f"[{d['id']}] {d['text']}" for d in docs) or "(no matching excerpts found)"
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Policy excerpts:\n{context}\n\n"
        f"Citizen question: {question}\n\n"
        f"Answer:"
    )
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()

# ---- Mock "policy document" corpus for simulated RAG ----
# In a real deployment, replace search_docs() with a call to the RAG
# retrieval service (e.g. a vector DB query against the official policy
# document store).
DOCS = [
    {
        "id": "POL-014",
        "title": "MediSave Outpatient Subsidy Guide (2026 ed., mock)",
        "text": (
            "MediSave can be used to offset outpatient treatment for chronic "
            "conditions under the CDMP. Claims require a valid polyclinic or "
            "approved GP referral."
        ),
        "keywords": ["outpatient", "chronic", "cdmp", "claim", "gp", "referral"],
    },
    {
        "id": "POL-021",
        "title": "MediSave Overview (mock)",
        "text": (
            "MediSave is a national medical savings scheme that helps citizens "
            "set aside part of their income to pay for healthcare expenses, "
            "including hospitalisation and selected outpatient treatments."
        ),
        "keywords": ["what is medisave", "overview", "savings", "hospitalisation"],
    },
    {
        "id": "POL-033",
        "title": "Subsidy Eligibility Criteria (mock)",
        "text": (
            "Eligibility for enhanced subsidies depends on household monthly "
            "income per person and citizenship status, assessed against "
            "published income tiers."
        ),
        "keywords": ["eligible", "eligibility", "income", "subsidy", "citizenship"],
    },
    {
        "id": "POL-040",
        "title": "Claims Submission Process (mock)",
        "text": (
            "Claims are submitted through the polyclinic or hospital at point "
            "of billing; no separate citizen-initiated claim form is required "
            "for standard subsidised visits."
        ),
        "keywords": ["claim", "submit", "process", "billing"],
    },
]


def search_docs(query: str, top_n: int = 2):
    """Very simple keyword-overlap 'retrieval'. Stand-in for real RAG search."""
    q = query.lower()
    scored = []
    for doc in DOCS:
        score = sum(1 for kw in doc["keywords"] if kw in q)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in scored[:top_n]]


# ---- Mock eligibility "API". Read-only, no write operations. ----
# In a real deployment, replace this with an authenticated call to the
# backend eligibility service, e.g.:
#     resp = requests.get(ELIGIBILITY_API_URL, params=..., headers=auth_headers)
def check_eligibility(income: float, citizenship: str) -> dict:
    time.sleep(0.4)  # simulate network latency
    eligible = citizenship == "citizen" and income <= 2800
    if eligible:
        tier = "Tier A (highest support)" if income <= 1500 else "Tier B"
        note = (
            "Based on the mock income tiers above, this profile qualifies "
            "for enhanced subsidies."
        )
    else:
        tier = "Not applicable"
        note = "This mock profile does not meet the demo income/citizenship threshold."
    return {"eligible": eligible, "tier": tier, "note": note}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/ask", methods=["POST"])
def api_ask():
    data = request.get_json(force=True) or {}
    message = str(data.get("message", "")).strip()
    lower = message.lower()

    if "eligib" in lower or "qualify" in lower:
        return jsonify({"type": "eligibility_form"})

    docs = search_docs(message)
    citations = [{"id": d["id"], "title": d["title"]} for d in docs]

    try:
        reply = call_ollama(message, docs)
        if not reply:
            raise ValueError("empty response from model")
    except (requests.exceptions.RequestException, ValueError) as e:
        # Ollama not running / unreachable / bad response — fall back to the
        # plain retrieved-snippet behaviour rather than failing the request.
        app.logger.warning("Ollama call failed, falling back to raw snippets: %s", e)
        if docs:
            reply = " ".join(d["text"] for d in docs)
        else:
            reply = (
                "I couldn't find a matching policy passage in the demo "
                "document set for that question. In production this would "
                "fall back to a human handoff. (Note: local LLM at "
                f"{OLLAMA_URL} was unreachable, so this is the raw-retrieval "
                "fallback.)"
            )

    return jsonify({"type": "text", "reply": reply, "citations": citations})


@app.route("/api/eligibility", methods=["POST"])
def api_eligibility():
    data = request.get_json(force=True) or {}
    try:
        income = float(data.get("income", 0))
    except (TypeError, ValueError):
        income = 0.0
    citizenship = str(data.get("citizenship", "other"))

    result = check_eligibility(income, citizenship)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)