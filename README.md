# Recovery Console — AI Revenue Recovery Agent

**Razorpay Buildathon · Track 03 · AI Revenue Recovery**

An agent that detects failed and abandoned payments, diagnoses the root cause using an LLM, checks the recommended action against a bounded policy gate, executes (or escalates) the intervention, and logs every decision to an auditable trail.

Every money-adjacent action in this system is **explainable** (logged reasoning at each step), **bounded** (hard policy caps, no exceptions), and **gated** (nothing executes without passing the policy layer first) — in line with the track's bar.

---

## The pipeline

```
Detect  →  Diagnose (Gemini)  →  Gate (policy, pure code)  →  Act  →  Log
```

1. **Detector** pulls all `failed`/`abandoned` payments from the database.
2. **Diagnosis agent** (Gemini 3.5 Flash-Lite) classifies the root cause — `insufficient_funds`, `bank_timeout`, `expired_card`, or `otp_dropoff` — and recommends one action, with a confidence score and a one-sentence reasoning string. Output is structured JSON; malformed responses fail safe to `escalate_human` rather than crashing the batch.
3. **Policy gate** (plain Python, no LLM) independently checks the diagnosis against fixed rules before anything is allowed to execute:
   - Max retries: **3** — beyond this, always escalate to a human
   - Min confidence to act: **0.5** — below this, escalate
   - Auto-action cap: **Rs 10,000** — above this, escalate for human sign-off regardless of confidence
   - Cooldown: **6 hours** — no repeat contact within this window
   - `root_cause = unknown` always escalates, regardless of confidence
4. **Recovery agent** executes the gated action (retry link, SMS nudge, or escalation) and records the outcome.
5. Every step — detection, diagnosis, gate decision, execution — writes a row to the audit log with an actor, a decision, and a rationale.

## Why the diagnosis and gating are separate

The LLM decides *what* the right action probably is. It never decides *whether* that action is allowed to run. That check is deterministic code with fixed thresholds, so the same payment always gets the same gate decision for the same inputs, and every block or pass has a one-line, independently reproducible reason — not a model's opinion of itself.

## Result on a 60-record synthetic batch

Numbers vary slightly between runs (see [Note on reproducibility](#note-on-reproducibility) below).

| Metric | Value |
|---|---|
| Total at-risk amount | Rs 3,97,221 |
| Recovered amount | Rs 1,05,870 (best run) |
| Recovery rate | 26.7% (best run) |
| Payments processed | 60 |
| Escalated to human review | 15 |

**Graceful failure example (Payment 33):** retry count reached the policy cap of 3. Rather than auto-acting on the diagnosis agent's suggestion, the policy gate blocked execution and escalated to a human reviewer, logging the reason: *"Retry count has reached or exceeded 3, so human intervention is recommended to avoid annoying the customer."* This is visible live in the dashboard's audit trail viewer for any payment ID.

## Architecture

- **`models.py`** — SQLAlchemy schema: `payments`, `interventions`, `audit_log`
- **`generate_data.py`** — synthetic batch generator (60 records across 4 failure modes, weighted realistically)
- **`diagnosis_agent.py`** — Gemini-powered root-cause classifier with structured JSON output, retry/backoff on rate limits, and fail-safe parsing
- **`policy_gate.py`** — pure-code bounded/gated policy layer, independent of the LLM
- **`batch_runner.py`** — orchestrates detect → diagnose → gate → act → log across the batch; clears prior run data before each run
- **`audit_trail.py`** — reconstructs the full chronological decision chain for any payment
- **`dashboard.py`** — Streamlit console: batch metrics, outcome/failure charts, exceptions table, audit trail viewer

## Running it

```bash
pip install -r requirements.txt
```

Create `.env` from `.env.example` with a Gemini API key (`aistudio.google.com`):
```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash-lite
```

Generate synthetic data and run the batch:
```bash
python generate_data.py
python batch_runner.py
```

Launch the dashboard:
```bash
streamlit run dashboard.py
```

The dashboard's sidebar also has a "Run full batch" button that re-runs the entire pipeline live (clears prior results first, so re-running never double-counts).

## Note on reproducibility

Recovery outcomes (`recovered` / `no_response`) are currently simulated probabilistically in `batch_runner.py`'s `execute_action()`, standing in for a real Razorpay Payment Links / SMS send in this prototype. This means the recovery rate varies slightly run to run (observed range: ~19–27% across runs) — the diagnosis and gating decisions themselves are deterministic and fully reproducible; only the simulated customer response is randomized.

## What's simulated vs. real in this build

- **Real:** database, all 60 synthetic payment records, live Gemini API calls for every diagnosis, policy gate logic, full audit logging, dashboard reading live from the database
- **Simulated:** the actual SMS/retry-link delivery and customer response (stubbed with a probability model) — swapping in Razorpay's Payment Links API and a real SMS/WhatsApp send is the direct next step to take this to production