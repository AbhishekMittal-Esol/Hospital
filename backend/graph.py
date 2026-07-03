import os
import json
from typing import TypedDict, Annotated, List, Literal

from dotenv import load_dotenv

# Load environment variables (GOOGLE_API_KEY) before the Gemini client is built.
load_dotenv()

from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel

from backend.tools import (
    get_patient_details,
    search_doctors,
    book_appointment,
    check_lab_reports,
    schedule_lab_test,
    send_notification,
)

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# Guardrails to keep the workflow bounded.
MAX_TOOL_ITERS = 5      # tool-calling steps inside a single specialist agent
MAX_RETRIES = 1         # validator -> planner correction loops


# --------------------------------------------------------------------------
# Shared State
# --------------------------------------------------------------------------
class AgentState(TypedDict):
    patient_id: str
    user_query: str
    messages: Annotated[list[BaseMessage], add_messages]
    needs_booking: bool
    needs_lab: bool
    appointment_status: str
    lab_test_status: str
    notification_status: str
    summary: str
    retries: int
    validated: bool


# --------------------------------------------------------------------------
# Structured-output schemas
# --------------------------------------------------------------------------
class PlannerDecision(BaseModel):
    needs_booking: bool
    needs_lab: bool
    reason: str


class ValidationDecision(BaseModel):
    is_valid: bool
    missing_tasks: str
    appointment_status: str
    lab_test_status: str
    summary: str


# --------------------------------------------------------------------------
# Generic tool-calling loop used by every specialist agent
# --------------------------------------------------------------------------
def run_agent_loop(tools, system_prompt: str, prior_messages: list) -> list:
    """Runs a bounded ReAct loop: the model calls tools until it is done.

    Returns the list of new messages produced during this turn.
    """
    tools_by_name = {t.name: t for t in tools}
    bound_llm = llm.bind_tools(tools)

    new_messages: list = []
    for _ in range(MAX_TOOL_ITERS):
        response = bound_llm.invoke(
            [SystemMessage(content=system_prompt)] + prior_messages + new_messages
        )
        new_messages.append(response)

        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            break

        for call in tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                result = {"error": f"Unknown tool {call['name']}"}
            else:
                # Failure recovery: never let a tool exception crash the graph.
                try:
                    result = tool.invoke(call["args"])
                except Exception as exc:  # noqa: BLE001
                    result = {"error": f"Tool {call['name']} failed: {exc}"}
            new_messages.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=call["id"],
                )
            )
    return new_messages


def _collect_tool_results(messages: list, tool_name: str) -> list:
    """Pull decoded JSON payloads for a given tool from ToolMessages."""
    results = []
    # Map tool_call_id -> tool name from AI messages.
    id_to_name = {}
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            id_to_name[call["id"]] = call["name"]
    for msg in messages:
        if isinstance(msg, ToolMessage) and id_to_name.get(msg.tool_call_id) == tool_name:
            try:
                results.append(json.loads(msg.content))
            except (json.JSONDecodeError, TypeError):
                results.append({"raw": msg.content})
    return results


# --------------------------------------------------------------------------
# Agents
# --------------------------------------------------------------------------
def coordinator_agent(state: AgentState) -> dict:
    """Understands the request and loads patient context into shared state."""
    prompt = (
        "You are the Coordinator agent in a hospital system. "
        f"Patient ID: {state['patient_id']}. "
        f"Request: '{state['user_query']}'.\n"
        "Call get_patient_details to load this patient's record so downstream "
        "agents know their existing appointments and lab reports."
    )
    new_messages = run_agent_loop([get_patient_details], prompt, state["messages"])
    return {"messages": new_messages}


def planner_agent(state: AgentState) -> dict:
    """Decides which independent branches are required (dynamic decision making)."""
    prompt = (
        "You are the Planner. Based on the patient's request and their existing "
        "record in the conversation, decide which independent work streams are needed.\n"
        f"Request: '{state['user_query']}'.\n"
        "- needs_booking: true if the patient wants a doctor appointment.\n"
        "- needs_lab: true if the request involves checking or scheduling any lab test.\n"
        "Only enable a stream if it is actually required by the request."
    )
    structured = llm.with_structured_output(PlannerDecision)
    decision = structured.invoke([SystemMessage(content=prompt)] + state["messages"])

    needs_booking = decision.needs_booking
    needs_lab = decision.needs_lab

    # Do not re-dispatch a branch that has already succeeded (prevents double
    # booking / duplicate lab tests on validator-triggered retries).
    if state.get("appointment_status", "").startswith("Booked"):
        needs_booking = False
    lab_status = state.get("lab_test_status", "")
    if lab_status.startswith("Scheduled") or "already exists" in lab_status:
        needs_lab = False

    return {"needs_booking": needs_booking, "needs_lab": needs_lab}


def booking_agent(state: AgentState) -> dict:
    """Multi-step: search a suitable doctor, pick the earliest slot, book it."""
    prompt = (
        "You are the Booking agent. Fulfil any appointment request in the query.\n"
        f"Patient ID: {state['patient_id']}. Request: '{state['user_query']}'.\n"
        "Steps: use search_doctors for the right specialization, choose the earliest "
        "available slot, then call book_appointment. If booking fails or no slot is "
        "available, try another available slot or doctor before giving up."
    )
    new_messages = run_agent_loop(
        [search_doctors, book_appointment], prompt, state["messages"]
    )

    booking_results = _collect_tool_results(new_messages, "book_appointment")
    success = next((r for r in booking_results if r.get("status") == "Success"), None)
    if success:
        doc = success.get("doctor_name", "")
        spec = success.get("specialization", "")
        appt_id = success.get("appointment_id", "")
        slot = success.get("slot", "")
        label = f"{doc} ({spec})" if spec else doc
        status = f"Booked: {label} — {slot} (ID: {appt_id})"
    elif booking_results:
        status = f"Failed: {booking_results[-1].get('error', 'unknown error')}"
    else:
        status = "No booking action taken"
    return {"messages": new_messages, "appointment_status": status}


def lab_agent(state: AgentState) -> dict:
    """Dynamic: check for an existing report, only schedule if it is missing."""
    prompt = (
        "You are the Lab agent. Handle any lab-test part of the request.\n"
        f"Patient ID: {state['patient_id']}. Request: '{state['user_query']}'.\n"
        "First call check_lab_reports for the relevant test. Only call "
        "schedule_lab_test if no matching report already exists. Do not schedule "
        "duplicates."
    )
    new_messages = run_agent_loop(
        [check_lab_reports, schedule_lab_test], prompt, state["messages"]
    )

    scheduled = _collect_tool_results(new_messages, "schedule_lab_test")
    checks = _collect_tool_results(new_messages, "check_lab_reports")
    scheduled_ok = next((r for r in scheduled if r.get("status") == "Success"), None)
    if scheduled_ok:
        status = "Scheduled (new test)"
    elif any(c.get("exists") for c in checks):
        status = "Report already exists (no scheduling needed)"
    elif checks or scheduled:
        status = "No lab action required"
    else:
        status = "No lab action taken"
    return {"messages": new_messages, "lab_test_status": status}


def validator_agent(state: AgentState) -> dict:
    """Verifies every requested task is complete and consistent with tool outputs."""
    prompt = (
        "You are the Validator. Review the full conversation and confirm that every "
        "task in the patient's request was actually completed by tool calls, with no "
        "hallucinated results.\n"
        f"Request: '{state['user_query']}'.\n"
        "Report the real appointment_status and lab_test_status based only on tool "
        "outputs. Set is_valid=false and describe missing_tasks if anything requested "
        "was not done. Provide a concise patient-facing summary."
    )
    structured = llm.with_structured_output(ValidationDecision)
    decision = structured.invoke([SystemMessage(content=prompt)] + state["messages"])

    retries = state.get("retries", 0)
    # Accept if valid, or if we've exhausted correction attempts (best effort).
    accepted = decision.is_valid or retries >= MAX_RETRIES

    update = {
        "appointment_status": decision.appointment_status,
        "lab_test_status": decision.lab_test_status,
        "summary": decision.summary,
        "validated": accepted,
    }
    if not accepted:
        update["retries"] = retries + 1
        update["messages"] = [
            AIMessage(
                content=f"Validation failed. Missing/incorrect: {decision.missing_tasks}. "
                "Re-running the necessary steps."
            )
        ]
    return update


def notification_agent(state: AgentState) -> dict:
    """Sends the final notification once everything else is validated."""
    prompt = (
        "You are the Notification agent. Send one final notification to the patient "
        "using send_notification, summarising what was done.\n"
        f"Patient ID: {state['patient_id']}.\n"
        f"Summary to convey: {state.get('summary', '')}"
    )
    new_messages = run_agent_loop([send_notification], prompt, state["messages"])

    sent = _collect_tool_results(new_messages, "send_notification")
    if any(r.get("status") == "Sent" for r in sent):
        status = "Sent"
    elif sent:
        status = f"Failed: {sent[-1].get('error', 'unknown error')}"
    else:
        status = "Not sent"
    return {"messages": new_messages, "notification_status": status}


# --------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------
def route_after_planner(state: AgentState) -> List[str]:
    """Fan out to the needed independent branches in parallel."""
    targets: List[str] = []
    if state.get("needs_booking"):
        targets.append("Booking")
    if state.get("needs_lab"):
        targets.append("Lab")
    if not targets:
        # Nothing to delegate; go straight to validation.
        return ["Validator"]
    return targets


def route_after_validator(state: AgentState) -> str:
    if state.get("validated"):
        return "Notification"
    return "Planner"


# --------------------------------------------------------------------------
# Build graph
# --------------------------------------------------------------------------
graph_builder = StateGraph(AgentState)

graph_builder.add_node("Coordinator", coordinator_agent)
graph_builder.add_node("Planner", planner_agent)
graph_builder.add_node("Booking", booking_agent)
graph_builder.add_node("Lab", lab_agent)
graph_builder.add_node("Validator", validator_agent)
graph_builder.add_node("Notification", notification_agent)

graph_builder.add_edge(START, "Coordinator")
graph_builder.add_edge("Coordinator", "Planner")

graph_builder.add_conditional_edges(
    "Planner",
    route_after_planner,
    ["Booking", "Lab", "Validator"],
)

# Booking and Lab fan back in to the Validator (barrier / join).
graph_builder.add_edge("Booking", "Validator")
graph_builder.add_edge("Lab", "Validator")

graph_builder.add_conditional_edges(
    "Validator",
    route_after_validator,
    {"Notification": "Notification", "Planner": "Planner"},
)

graph_builder.add_edge("Notification", END)

app = graph_builder.compile()
