"""Command-line demo for the Agentic Hospital Management System.

Runs the multi-agent workflow directly (without the HTTP server) so you can
see the final structured output.

Usage:
    python demo.py                       # runs the default P002 sample
    python demo.py P001 "your request"   # custom patient id + query
"""
import json
import sys

from langchain_core.messages import HumanMessage

from backend.graph import app as graph_app

DEFAULT_QUERY = (
    "I have chest pain. Book the earliest appointment with a cardiologist. "
    "Check whether I already have an ECG report. If not, schedule an ECG test. "
    "Finally notify me with all the details."
)


def run(patient_id: str, user_query: str) -> dict:
    initial_state = {
        "patient_id": patient_id,
        "user_query": user_query,
        "messages": [
            HumanMessage(content=f"Patient {patient_id} request: {user_query}")
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
    final_state = dict(initial_state)
    for event in graph_app.stream(initial_state, config={"recursion_limit": 50}):
        for node_name, update in event.items():
            status_bits = {
                k: v
                for k, v in (update or {}).items()
                if k in ("needs_booking", "needs_lab", "appointment_status",
                         "lab_test_status", "notification_status", "validated")
            }
            print(f"  -> {node_name}: {status_bits}", flush=True)
            final_state.update(update or {})
    return {
        "appointment_status": final_state.get("appointment_status"),
        "lab_test_status": final_state.get("lab_test_status"),
        "notification_status": final_state.get("notification_status"),
        "summary": final_state.get("summary"),
    }


if __name__ == "__main__":
    patient_id = sys.argv[1] if len(sys.argv) > 1 else "P002"
    user_query = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_QUERY

    print(f"\n=== Patient {patient_id} ===")
    print(f"Query: {user_query}\n")
    result = run(patient_id, user_query)
    print(json.dumps(result, indent=4))
