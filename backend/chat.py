"""Conversational Receptionist agent.

A friendly front-desk agent that chats with the patient, registers new patients,
and delegates the actual medical workflow (booking / lab / notification) to the
existing multi-agent graph. Returns structured result_card and agent_trace so
the frontend can display results and agent attribution immediately.
"""
import json
from typing import Dict, Any, List, Optional, Tuple

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from langchain_core.tools import tool

from backend.graph import llm, app as care_graph
from backend.tools import get_patient_details, register_patient, search_doctors

MAX_TOOL_ITERS = 6

# Agent labels shown in the UI
AGENT_LABELS = {
    "run_care_workflow": "Care Workflow",
    "get_patient_details": "Coordinator",
    "register_patient": "Receptionist",
}


def _extract_text(content: Any) -> str:
    """Normalise an AIMessage.content (str or list of parts) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and part.get("text"):
                    parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts).strip()
    return str(content)


# In-memory session store: session_id -> conversation history.
SESSIONS: Dict[str, List[BaseMessage]] = {}


@tool
def run_care_workflow(patient_id: str, request: str) -> Dict[str, Any]:
    """Runs the multi-agent care workflow for a KNOWN patient.

    Handles finding doctors, booking appointments, checking/scheduling lab tests
    and notifying the patient. Only call this once you have a valid patient_id
    and a clear description of what the patient needs.
    """
    patient_id = patient_id.upper()
    initial_state = {
        "patient_id": patient_id,
        "user_query": request,
        "messages": [HumanMessage(content=f"Patient {patient_id} request: {request}")],
        "needs_booking": False,
        "needs_lab": False,
        "appointment_status": "Not requested",
        "lab_test_status": "Not requested",
        "notification_status": "Pending",
        "summary": "Processing...",
        "retries": 0,
        "validated": False,
    }

    # Stream graph to collect which nodes ran (agent trace)
    nodes_visited = []
    final_state = dict(initial_state)
    for event in care_graph.stream(initial_state, config={"recursion_limit": 50}):
        for node_name, update in event.items():
            nodes_visited.append(node_name)
            if isinstance(update, dict):
                final_state.update(update)

    result = {
        "appointment_status": final_state.get("appointment_status", "Not requested"),
        "lab_test_status": final_state.get("lab_test_status", "Not requested"),
        "notification_status": final_state.get("notification_status", "Pending"),
        "summary": final_state.get("summary", ""),
        "_nodes_visited": nodes_visited,  # internal, extracted by caller
    }
    return result


RECEPTIONIST_TOOLS = [get_patient_details, register_patient, search_doctors, run_care_workflow]
_tools_by_name = {t.name: t for t in RECEPTIONIST_TOOLS}
_bound_llm = llm.bind_tools(RECEPTIONIST_TOOLS)

SYSTEM_PROMPT = (
    "You are a warm, helpful hospital front-desk assistant chatting with a patient.\n"
    "Your goals, in order:\n"
    "1. Identify the patient. Ask for their Patient ID. If they give one, call "
    "get_patient_details to look them up.\n"
    "2. If they are new, or the given ID is not found, register them: politely ask "
    "for their full name and age (ask for whatever is missing), then call "
    "register_patient. Tell them their new Patient ID.\n"
    "3. Once you have a valid patient_id, ask questions to understand their medical needs "
    "like a real human. If they have a symptom, ask clarifying questions (e.g., about pain).\n"
    "4. If they need an appointment, use the search_doctors tool to find available "
    "doctors and their slots. Present these options to the patient and ask them "
    "which doctor and time they prefer.\n"
    "5. Once the patient has confirmed a specific doctor and slot (or if they just want a lab test), "
    "call run_care_workflow. Pass a detailed description that includes the exact doctor name and slot chosen.\n"
    "6. Report the results back conversationally: mention the doctor name, appointment "
    "time, lab test outcome, and notification status clearly.\n\n"
    "Rules: Ask only for information you still need, one short question at a time. "
    "Never invent patient IDs, appointments, or results — only use tool outputs. "
    "If a request cannot be fulfilled, explain gently. Keep replies concise."
)


def _node_to_label(node: str) -> str:
    mapping = {
        "Coordinator": "Coordinator",
        "Planner": "Planner",
        "Booking": "Booking Agent",
        "Lab": "Lab Agent",
        "Validator": "Validator",
        "Notification": "Notification Agent",
    }
    return mapping.get(node, node)


def _run_turn(
    messages: List[BaseMessage],
) -> Tuple[List[BaseMessage], List[Dict[str, str]], Optional[Dict]]:
    """Run one assistant turn. Returns (new_messages, agent_trace, result_card)."""
    new_messages: List[BaseMessage] = []
    agent_trace: List[Dict[str, str]] = []
    result_card: Optional[Dict] = None

    for _ in range(MAX_TOOL_ITERS):
        response = _bound_llm.invoke(messages + new_messages)
        new_messages.append(response)

        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            break

        for call in tool_calls:
            tool_fn = _tools_by_name.get(call["name"])
            tool_label = AGENT_LABELS.get(call["name"], call["name"])

            if tool_fn is None:
                result = {"error": f"Unknown tool {call['name']}"}
            else:
                try:
                    result = tool_fn.invoke(call["args"])
                except Exception as exc:  # noqa: BLE001
                    result = {"error": f"Tool {call['name']} failed: {exc}"}

            # Build agent trace entry
            if call["name"] == "register_patient" and result.get("status") == "Success":
                agent_trace.append({
                    "agent": "Receptionist",
                    "action": f"Registered {result.get('name')} as {result.get('patient_id')}",
                })
            elif call["name"] == "get_patient_details" and not result.get("error"):
                agent_trace.append({
                    "agent": "Coordinator",
                    "action": f"Loaded patient record for {result.get('patient_id', '')}",
                })
            elif call["name"] == "run_care_workflow":
                # Extract nodes visited from the result
                nodes = result.pop("_nodes_visited", [])
                unique_nodes = list(dict.fromkeys(nodes))  # dedupe, keep order
                for node in unique_nodes:
                    label = _node_to_label(node)
                    appt = result.get("appointment_status", "")
                    lab = result.get("lab_test_status", "")
                    notif = result.get("notification_status", "")
                    if node == "Booking":
                        action = appt if appt else "Searched doctors and booked appointment"
                    elif node == "Lab":
                        action = lab if lab else "Checked lab reports"
                    elif node == "Validator":
                        action = "Verified all tasks completed"
                    elif node == "Notification":
                        action = f"Notification {notif}"
                    elif node == "Coordinator":
                        action = "Loaded patient context"
                    elif node == "Planner":
                        action = "Determined required tasks"
                    else:
                        action = f"{label} completed"
                    agent_trace.append({"agent": label, "action": action})

                # Build result_card to show structured statuses immediately
                result_card = {
                    "appointment_status": result.get("appointment_status", "Not requested"),
                    "lab_test_status": result.get("lab_test_status", "Not requested"),
                    "notification_status": result.get("notification_status", "Pending"),
                    "summary": result.get("summary", ""),
                }

            new_messages.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=call["id"],
                )
            )

    return new_messages, agent_trace, result_card


def chat(
    session_id: str, message: str
) -> Tuple[str, List[Dict[str, str]], Optional[Dict]]:
    """Process one user message. Returns (reply, agent_trace, result_card)."""
    history = SESSIONS.get(session_id)
    if history is None:
        history = [SystemMessage(content=SYSTEM_PROMPT)]

    history.append(HumanMessage(content=message))
    new_messages, agent_trace, result_card = _run_turn(history)
    history.extend(new_messages)
    SESSIONS[session_id] = history

    # The reply is the text of the last AI message that produced content.
    for msg in reversed(new_messages):
        if isinstance(msg, AIMessage):
            text = _extract_text(msg.content)
            if text:
                return text, agent_trace, result_card

    return "Sorry, I wasn't able to produce a response. Could you rephrase?", agent_trace, result_card


GREETING = (
    "Hello! I'm your hospital assistant. I can help you book appointments, check or "
    "schedule lab tests, and more. Do you have a Patient ID, or are you a new patient?"
)
