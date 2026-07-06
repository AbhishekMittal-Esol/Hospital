from backend.state import AgentState
from backend.agents.utils import run_agent_loop, _collect_tool_results
from backend.tools import send_notification

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
