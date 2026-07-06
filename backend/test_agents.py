import asyncio
import json
from backend.graph import app
from langchain_core.messages import HumanMessage

def test_workflow():
    initial_state = {
        "patient_id": "P001",
        "user_query": "Book the earliest available cardiologist appointment. Check whether I already have an ECG report. If no ECG exists, schedule an ECG test. Notify me after everything is complete",
        "messages": [
            HumanMessage(content="Patient P001 request: Book the earliest available cardiologist appointment. Check whether I already have an ECG report. If no ECG exists, schedule an ECG test. Notify me after everything is complete")
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

    print("Running workflow with full trace...")
    for event in app.stream(initial_state, config={"recursion_limit": 50}):
        for node_name, update in event.items():
            print(f"\n--- Node: {node_name} ---")
            if "messages" in update:
                for msg in update["messages"]:
                    print(msg.__class__.__name__, msg.content)
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        print("Tool Calls:", msg.tool_calls)
            else:
                print("Update:", update)
                
if __name__ == "__main__":
    test_workflow()
