from backend.state import AgentState
from backend.agents.utils import run_agent_loop
from backend.tools import get_patient_details

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
