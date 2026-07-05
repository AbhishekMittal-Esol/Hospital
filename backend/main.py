from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Load environment variables (e.g. GOOGLE_API_KEY)
load_dotenv()

from backend.graph import app as graph_app
from backend.chat import chat as run_chat, GREETING
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "hospital.db")

app = FastAPI(title="Agentic Hospital Management API")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RequestModel(BaseModel):
    patient_id: str
    user_query: str

class ResponseModel(BaseModel):
    appointment_status: str
    lab_test_status: str
    notification_status: str
    summary: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    agent_trace: list = []
    result_card: dict | None = None


@app.get("/api/chat/greeting")
async def chat_greeting():
    return {"reply": GREETING}


@app.post("/api/chat", response_model=ChatResponse)
async def handle_chat(req: ChatRequest):
    if not req.session_id or not req.message:
        raise HTTPException(status_code=400, detail="Missing session_id or message")
    try:
        reply, agent_trace, result_card = run_chat(req.session_id, req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(reply=reply, agent_trace=agent_trace, result_card=result_card)

@app.post("/api/request", response_model=ResponseModel)
async def handle_request(req: RequestModel):
    if not req.patient_id or not req.user_query:
        raise HTTPException(status_code=400, detail="Missing patient_id or user_query")
    
    initial_state = {
        "patient_id": req.patient_id,
        "user_query": req.user_query,
        "messages": [
            HumanMessage(content=f"Patient {req.patient_id} request: {req.user_query}")
        ],
        "needs_booking": False,
        "needs_lab": False,
        "appointment_status": "Not requested",
        "lab_test_status": "Not requested",
        "notification_status": "Pending",
        "summary": "Processing...",
        "retries": 0,
        "validated": False,
    }
    
    # Run the graph
    try:
        # invoke runs the graph synchronously
        # We need to set recursion_limit higher if the agents talk back and forth a lot
        config = {"recursion_limit": 50}
        final_state = graph_app.invoke(initial_state, config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return ResponseModel(
        appointment_status=final_state.get("appointment_status", "Unknown"),
        lab_test_status=final_state.get("lab_test_status", "Unknown"),
        notification_status=final_state.get("notification_status", "Unknown"),
        summary=final_state.get("summary", "Workflow completed but no summary provided.")
    )

@app.get("/api/database")
async def get_database_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    data = {}
    tables = ["patients", "doctors", "doctor_slots", "appointments", "lab_reports"]
    for table in tables:
        cursor.execute(f"SELECT * FROM {table}")
        data[table] = [dict(row) for row in cursor.fetchall()]
        
    conn.close()
    return data

# Mount frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
