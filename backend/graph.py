from typing import List
from langgraph.graph import StateGraph, START, END

from backend.state import AgentState
from backend.agents import (
    coordinator_agent,
    planner_agent,
    booking_agent,
    lab_agent,
    validator_agent,
    notification_agent,
)


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
