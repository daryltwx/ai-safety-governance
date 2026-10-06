"""
Centralized runtime configuration, loaded from environment variables.

Local dev: copy .env.example to .env and edit it; load_dotenv() below
picks it up automatically. CI/deployment: set real environment variables
(e.g. the CI workflow's `env:` block) -- load_dotenv() never overrides a
variable that's already set in the environment, so real env vars always
win over whatever's in .env, and nothing breaks if .env doesn't exist at
all (CI doesn't commit it; see .gitignore).

See .env.example for what every variable does and its default.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ---- LLM backend (Ollama via LangChain) ----
# Swapping either of these is the whole "plug in any model" point of this
# app's design -- see docs/2026-10-06-pii-tokenization-and-agentic-chaining.md
# before pointing OLLAMA_URL at a closed/third-party-hosted model: real
# PII flows wherever this points. tokenize_pii()/mask_record() in app.py
# only cover NRIC-shaped text, not a blanket guarantee.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

# ---- Bounded ReAct loop ----
MAX_TOOL_ROUNDS = int(os.environ.get("MAX_TOOL_ROUNDS", "4"))

# ---- Database (Postgres + pgvector) ----
# Holds citizen/claims records (real schema, always-synthetic data -- see
# seed_data.py) and the RAG policy-document embeddings, in one engine.
# The default below is for non-Docker local dev against a Postgres you've
# started yourself; docker-compose.yml overrides this to point at the
# `db` service instead. Credentials are a fixed local-dev default, not a
# secret -- this database never holds real PII, by design (see
# docs/2026-10-06-real-database-and-rag.md).
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://medicare:medicare@localhost:5432/medicare")

# ---- RAG embeddings ----
# Local embedding model served by the same Ollama instance as the chat
# model -- keeps the whole pipeline (chat + embeddings) on one backend
# with no external API key required.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")

# ---- Flask ----
PORT = int(os.environ.get("PORT", "5050"))
FLASK_DEBUG = _bool("FLASK_DEBUG", True)

# ---- Langfuse tracing ----
# Nothing to read here -- the Langfuse SDK reads LANGFUSE_PUBLIC_KEY,
# LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL directly from the
# environment wherever it's constructed in app.py. load_dotenv() above is
# what actually wires .env's values in; listed in .env.example so
# they're discoverable in one place.
