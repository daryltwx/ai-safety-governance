# MediCare Assist: Langfuse tracing & centralized config/.env

**Date:** 2026-10-06
**Scope:** `app.py`, `config.py` (new), `.env.example` (new), `.gitignore` (new), `requirements.txt`

Second distinct piece of work this calendar day, after
`2026-10-06-pii-tokenization-and-agentic-chaining.md`. Covers adding
observability (Langfuse) to the agentic pipeline, then centralizing the
app's scattered hardcoded/env-var config into `config.py` + `.env` —
including a real bug found in the process.

---

## 1. Langfuse tracing

**Motivation:** no visibility existed into the agentic pipeline beyond
Flask logs — which tool calls fired, what the model actually saw at each
step, retry behavior, verifier verdicts. Wanted basic request tracing.

**Decision point surfaced before writing any code:** Langfuse ships
trace data (prompts, tool-call args/results, responses) to wherever it's
hosted. Self-hosted keeps that on-machine, consistent with local Ollama
and the PII work from earlier sessions; Langfuse Cloud (SaaS) makes every
trace a new third-party-exposure channel, in parallel to the
`ChatOllama`-swap risk already hardened against. Asked; answer was
"just tracking logs" — read as a preference for the lighter-weight
option (Cloud, just an API key, no Docker) over infra setup, so went
with Cloud but scoped what gets traced accordingly (see below).

**Solution:**
- `Langfuse(mask=_mask_pii)` + `langfuse.langchain.CallbackHandler`
  (`LANGFUSE_CONFIG = {"callbacks": [langfuse_handler]}`) passed to every
  `.invoke()` call in the pipeline: the main tool-calling loop,
  `lookup_citizen_record`, `read_uploaded_document`, the verifier
  (`reply_is_grounded`), and `reformulate_query`.
- `@observe(name="api_ask", capture_input=False, capture_output=False)`
  on the Flask route groups each citizen request into one trace.
  `capture_input/output` disabled because a Flask view takes no
  meaningful args and returns a `Response` object, not serializable data
  — the nested LangChain spans carry the actual content.
- `@app.after_request` hook calls `get_client().flush()` so traces show
  up promptly against a short-lived dev-server process rather than
  sitting in the client's batching buffer.
- `_mask_pii`: a regex backstop (reusing the existing `NRIC_PATTERN`)
  registered as the client's global `mask`, applied to every span's
  captured input/output in-process, before serialization, before any
  network call.

**Why the mask matters — a gap surfaced while wiring this in, not caused
by it:** not every model call in this app goes through the
`tokenize_pii()`/`mask_record()` path built in the previous session.
`reformulate_query()` is called from `agentic_retrieve()`, which runs
*before* `call_ollama()` ever tokenizes the citizen's message — it ships
the raw, real-NRIC-containing question to `OLLAMA_MODEL`. `reply_is_grounded()`
checks `call_ollama()`'s already-*detokenized* output — the real reply,
real PII included. Both are pre-existing, undocumented-until-now gaps in
the tokenization work, not introduced by tracing. But tracing is what
would otherwise turn them into a concrete leak on every single request,
by shipping that real PII to Langfuse Cloud in the trace. `_mask_pii`
closes that specific export-time exposure without requiring a call-order
restructure of those two functions — same structured-identifier-only
limitation as `tokenize_pii()` (NRIC-shaped text only, not names/addresses).

**Verification:**
- Confirmed graceful no-op with no Langfuse env vars set: client logs a
  warning and disables itself; `/api/ask` works normally, same latency.
- `ci-regression.yaml`: re-run 4 times total across this session's
  changes — 6/6, 6/6, 6/6, then one run at 5/6 (see "known flake" below,
  confirmed unrelated), then 6/6 again after the config refactor.
- **Known flake, confirmed not caused by this change:** one regression
  run flagged the RT-02 case (fabricated "CHAS tier" eligibility figures
  under a "simulate a lookup" framing) as failed, after 3 prior clean
  runs. Fired the identical prompt 3 times directly afterward: refusal,
  fabrication, refusal — confirming this is the same pre-existing
  sampling-dependent jailbreak resistance already documented in the
  2026-10-05 session doc, not a regression. Nothing in passing a
  `config={"callbacks": [...]}` kwarg through `.invoke()` touches model
  sampling.

---

## 2. Centralizing config into `config.py` + `.env`

**Problem:** `OLLAMA_URL` was hardcoded (`"http://localhost:11434"`,
not overridable without editing source); `OLLAMA_MODEL` was read inline
via `os.environ.get(...)`; `MAX_TOOL_ROUNDS` and the Flask `port`/`debug`
args were bare literals. No `.env` support, no single place documenting
what's configurable. Also: no `.gitignore` existed at all in this repo.

**Solution:**
- `config.py`: one module, `load_dotenv()` once, exposes typed constants
  (`OLLAMA_URL`, `OLLAMA_MODEL`, `MAX_TOOL_ROUNDS`, `PORT`, `FLASK_DEBUG`)
  read from the environment. `app.py` imports from it instead of
  hardcoding or re-reading `os.environ` itself.
- `.env.example` (committed): documents every variable, its default, and
  for `OLLAMA_URL`/`OLLAMA_MODEL` specifically, a pointer back to the
  third-party-exposure writeup before pointing it at a closed model.
- `.env` (local, gitignored): working copy, same defaults as
  `.env.example` initially.
- `.gitignore` (new file — none existed): `.env`, `__pycache__/`,
  `*.pyc`. Added *before* `.env` existed, specifically so there was never
  a window where a real secret could get swept into `git add -A`.
- `requirements.txt`: added `python-dotenv`.
- Chose `config.py` over a YAML config: secrets (Langfuse keys) need to
  come from env/`.env` regardless of what holds the non-secret settings,
  so the real choice was "YAML + .env" vs "just .env" — YAML would only
  add a second format and a parsing dependency for values plain env vars
  already handle, with no benefit for values that must be env-sourced
  anyway.

**A real bug found and fixed in the process:** the first `.env.example`
shipped `LANGFUSE_PUBLIC_KEY=` — present, but empty — with a comment
claiming that's a safe way to disable tracing. It isn't. Confirmed live:
an empty-but-set `LANGFUSE_PUBLIC_KEY` is NOT the same as a genuinely
absent one. The SDK's "disable cleanly" path only triggers when the var
is truly unset; present-but-empty instead made the OTel exporter actually
attempt a network call to `cloud.langfuse.com` on every request, hit a
local SSL certificate verification error, and retry/fail repeatedly
(visible in the dev server log — `Transient error ... SSLCertVerificationError
... retrying`). Fixed by commenting the three Langfuse lines out by
default in both `.env.example` and `.env`, rather than leaving them
blank, and corrected the matching (previously wrong) claim in `app.py`'s
Langfuse setup comment.

**Also fixed in passing:** the module docstring's "Then open
http://localhost:5000" was stale — the actual default port has been
5050 since this file's `app.run(port=5050)` call, well before this
session. Updated the docstring and pointed it at `.env`/`PORT` instead of
a hardcoded number.

**Operational finding, not a code change:** while tracking down which
Python environment actually runs this app to test the new dependencies,
found three candidate environments in play (`/private/tmp/lc_venv`
used for this session's direct-instrumentation testing, a conda
installation, and `/Users/daryltwx/Desktop/Project/.venv` — the one the
IDE's Pylance actually resolves against). The `.venv` one was missing
`ollama`, `langchain-ollama`, `langfuse`, `langchain`, and
`python-dotenv` even though the live dev server had been running
successfully all session — meaning the server process was started from
some other environment or shell state not captured in any committed
file. Installed the full dependency set into `.venv` so it's usable and
consistent with what the IDE expects going forward. Not fully resolved:
*which* environment the original `python app.py` launch actually used
was never conclusively identified.

**Verification:**
- `.env` edits take effect with zero code changes (`MAX_TOOL_ROUNDS=7`
  test, confirmed via direct `config.py` import).
- A real environment variable still overrides `.env`
  (`MAX_TOOL_ROUNDS=99` env var test) — confirms CI's existing
  `OLLAMA_MODEL` override (set via workflow `env:`, no `.env` file in
  CI) keeps working unchanged.
- `git check-ignore -v .env` confirms it's actually ignored, not just
  assumed to be.
- `ci-regression.yaml`: 6/6 after the full config refactor.

---

## Summary of what changed

| Area | Change |
|---|---|
| Observability | Langfuse tracing on every model/tool `.invoke()` call, one trace per request via `@observe` |
| PII export protection | `_mask_pii` — regex backstop masking NRIC-shaped text from all traced span data |
| Gap surfaced (not fixed) | `reformulate_query()`/`reply_is_grounded()` send real PII to `OLLAMA_MODEL` regardless of tracing — pre-existing, now documented |
| Config | `config.py` centralizes `OLLAMA_URL`/`OLLAMA_MODEL`/`MAX_TOOL_ROUNDS`/`PORT`/`FLASK_DEBUG`, all `.env`-overridable |
| New files | `.env.example`, `.gitignore` (repo had none) |
| Bug found & fixed | Empty-but-present `LANGFUSE_PUBLIC_KEY` ≠ unset — caused real network retries/failures every request; fixed by commenting the lines out by default |
| Also fixed | Stale "open http://localhost:5000" in the module docstring (actual default has been 5050) |

## What's still open

- `reformulate_query()` ships the raw (untokenized) citizen question to
  `OLLAMA_MODEL`, and `reply_is_grounded()` checks the already-detokenized
  real reply — both bypass the tokenization work entirely, independent
  of Langfuse. `_mask_pii` only protects the *trace export* of these
  calls, not the calls themselves reaching whatever model is configured.
  Closing this for real would mean restructuring `api_ask()` to tokenize
  the question once, up front, before `agentic_retrieve()` runs, and
  moving `reply_is_grounded()`'s check before `detokenize()` — a real
  change to call order, scoped but not built this session.
- The environment that was actually running the dev server all session
  was never identified — only worked around by installing the missing
  packages into the IDE's `.venv`. Worth deliberately settling on one
  environment (document it, or commit a lockfile) rather than leaving it
  implicit.
- No automated red-team suite has been run against the Langfuse/config
  changes specifically — not expected to be needed (neither changes
  model-facing behavior), confirmed only via `ci-regression.yaml` and
  direct smoke tests.
