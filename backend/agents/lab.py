from backend.state import AgentState
from backend.agents.utils import run_agent_loop, _collect_tool_results
from backend.tools import check_lab_reports, schedule_lab_test

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
