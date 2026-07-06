from langchain_core.messages import SystemMessage
from backend.state import AgentState, PlannerDecision
from backend.llm import llm

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
