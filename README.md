# Agentic Hospital Management System

A multi-agent AI system that handles complex patient requests (booking appointments,
checking/scheduling lab tests, and notifying the patient) through collaborating agents.

- **Frontend:** HTML / CSS / vanilla JS
- **Backend:** FastAPI
- **Agents:** LangGraph orchestrating Google Gemini (`gemini-2.5-flash`)
- **Database:** SQLite

## Two ways to interact

1. **Chat (recommended):** a conversational front-desk assistant that identifies or
   registers you, then handles your request and reports back in plain language.
2. **Structured API:** a one-shot `POST /api/request` that returns the four status fields.

## Architecture

```
Chat (Receptionist agent)  ->  register_patient / get_patient_details
                           ->  run_care_workflow  ->  multi-agent graph:

Coordinator  ->  Planner  ->  [ Booking  ||  Lab ]  ->  Validator  ->  Notification
                    ^                                        |
                    +------------ retry if incomplete -------+
```

The Receptionist agent chats with the patient (with per-session memory), auto-registers
new patients (collecting name + age, auto-generating an ID like `P003`), and delegates
the medical work to the multi-agent graph below.

- **Coordinator** loads the patient record into shared state.
- **Planner** decides which independent work streams are needed and skips ones already satisfied (dynamic decision making).
- **Booking** and **Lab** run in parallel. Booking does a multi-step flow (search doctor -> pick earliest slot -> book). Lab checks for an existing report and only schedules a new test if none exists.
- **Validator** verifies every requested task was completed and matches tool outputs; if not, it loops back for self-correction (bounded by a retry cap).
- **Notification** sends the final summary to the patient.

Agents communicate through a shared LangGraph state and never crash on tool failures (errors are returned as data so the workflow can recover).

When no specialist is available for a request, the system automatically falls back to a General Practice (GP) doctor.

## Project layout

- `backend/tools.py` - database-backed tools the agents call (incl. `register_patient`).
- `backend/graph.py` - care agents, shared state, and the LangGraph workflow.
- `backend/chat.py` - conversational Receptionist agent + in-memory sessions.
- `backend/main.py` - FastAPI app (`/api/chat`, `/api/request`) that serves the frontend.
- `frontend/` - chat UI (`index.html`, `style.css`, `app.js`).
- `database/init_db.py` - creates and seeds `hospital.db`.
- `demo.py` - run the care workflow from the command line.
- `run_server.py` - convenience launcher (Uvicorn on port 5000).

## First-time setup after clone

```bash
python -m venv venv
venv\Scripts\activate          # Windows (PowerShell: venv\Scripts\Activate.ps1)
pip install -r requirements.txt
```

Copy the environment template and add your Gemini API key:

```bash
copy .env.example .env         # Windows
# cp .env.example .env         # macOS / Linux
```

Edit `.env`:

```
GOOGLE_API_KEY=your_key_here
```

Initialize the database:

```bash
python database/init_db.py
```

Start the server:

```bash
python run_server.py
```

Open http://localhost:5000 in your browser and start chatting.

> **Note:** `.env`, `venv/`, `database/hospital.db`, and `question.txt` are gitignored.
> The database is regenerated locally via `init_db.py`. Never commit your API key.

## Run

```bash
python run_server.py
```

Then open http://localhost:5000 and start chatting. Example: "I have chest pain, book the earliest cardiologist and check my ECG." The assistant will register you if you're new, then handle everything.

### API

**Chat** - `POST /api/chat`

Request:

```json
{ "session_id": "abc123", "message": "I have chest pain, book a cardiologist." }
```

Response:

```json
{
  "reply": "I've booked an appointment with Dr. Brown...",
  "agent_trace": [
    { "agent": "Coordinator", "action": "Loaded patient context" },
    { "agent": "Booking Agent", "action": "Booked: Dr. Brown (Cardiology) — ..." }
  ],
  "result_card": {
    "appointment_status": "Booked: Dr. Brown (Cardiology) — 2026-07-10 11:00 (ID: A1B2C)",
    "lab_test_status": "Scheduled (new test)",
    "notification_status": "Sent",
    "summary": "..."
  }
}
```

Send the same `session_id` on each message to keep context. `result_card` is `null` until the care workflow runs. `GET /api/chat/greeting` returns the opening message.

**Structured (one-shot)** - `POST /api/request`

```json
{ "patient_id": "P002", "user_query": "Book the earliest cardiologist appointment and schedule an ECG if I don't have one, then notify me." }
```

Response:

```json
{
  "appointment_status": "...",
  "lab_test_status": "...",
  "notification_status": "...",
  "summary": "..."
}
```

### Command-line demo

```bash
python demo.py P002
python demo.py P001 "Book a cardiologist and check my ECG report, then notify me."
```

## Sample data

After running `python database/init_db.py`:

- **Patients:** `P001` (John Doe, has ECG report + appointment), `P002` (Alice Smith, no history).
- **Cardiology (3):** Dr. Brown (D101), Dr. Patel (D102), Dr. Khan (D103).
- **Orthopedics (2):** Dr. Green (D104), Dr. Lee (D105).
- **General Practice / fallback (3):** Dr. Adams (D201), Dr. Nair (D202), Dr. Smith (D203).

If no specialist matches the request, the system books with an available GP.
