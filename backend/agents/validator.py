from langchain_core.messages import SystemMessage, AIMessage
from backend.state import AgentState, ValidationDecision
from backend.llm import llm
from backend.agents.utils import MAX_RETRIES

def validator_agent(state: AgentState) -> dict:
    """Verifies every requested task is complete and consistent with tool outputs."""
    prompt = (
        "You are the Validator. Review the full conversation and confirm that every "
        "task in the patient's request was actually completed by tool calls, with no "
        "hallucinated results.\n"
        f"Request: '{state['user_query']}'.\n"
        "CRITICAL: Ignore any requests related to sending notifications, alerts, or summaries. These are handled downstream AFTER validation.\n"
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
