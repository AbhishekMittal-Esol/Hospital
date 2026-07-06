from backend.state import AgentState
from backend.agents.utils import run_agent_loop, _collect_tool_results
from backend.tools import search_doctors, book_appointment

def booking_agent(state: AgentState) -> dict:
    """Multi-step: search a suitable doctor, pick the earliest slot, book it."""
    prompt = (
        "You are the Booking agent. Fulfil any appointment request in the query.\n"
        f"Patient ID: {state['patient_id']}. Request: '{state['user_query']}'.\n"
        "Steps: use search_doctors for the right specialization. If the request specifies "
        "a particular doctor and slot, call book_appointment with those details. Otherwise, "
        "choose the earliest available slot. If booking fails, try another slot."
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
