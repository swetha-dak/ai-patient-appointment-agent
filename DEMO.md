# Demo walkthrough

Fictional clinic data only. Start the API first (`uvicorn main:app --reload`). Ollama is optional; the planner still books if the model is down.

The scripted demo resets SQLite (`APT-001` only), talks through `/chat`, then checks `/appointments`. It also runs the eight-scenario evaluator against `data/eval.db`.

```bash
python -m evaluation.demo
```

If port 8000 is not up, the script falls back to an in-process agent with Ollama disabled.

## UI (Vite)

Terminal 1 — API already running.

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Confirm the header shows **backend phase 19**.

`--reload` wipes in-memory sessions when Python files change. Finish a conversation before editing, or use a new `session_id`.

Live Ollama can take a minute per turn. Evaluation and `python -m evaluation.demo` still check SQLite, not the phrasing.

Use a new browser session if you already booked during the CLI demo. Reset the clinic first:

```bash
python -m backend.database.seed --reset
```

Then send:

1. `I need an appointment with Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.`
   - Expect a confirmation question, not a new appointment id.
2. `Yes`
   - Expect `APT-002` and a success line built from the tool result.
3. Optionally confirm in the API: http://127.0.0.1:8000/appointments

Other prompts:

- Unavailable: `Book me with Dr. Smith on 2026-10-06 at 11:00. I am PAT-002.` then `Yes` — must not create a second 11:00 booking.
- Ambiguous: `I want an appointment with Dr. Smith sometime next week. I am PAT-003.` — must not invent a date.

## Curl

After a seed reset:

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"demo-session-001\",\"message\":\"I need an appointment with Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.\"}"

curl -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"demo-session-001\",\"message\":\"Yes\"}"

curl http://127.0.0.1:8000/appointments
```

## Evaluation

```bash
python -m evaluation.evaluator
pytest
```

Or `POST /evaluate`. The evaluator is not an LLM judge.
