from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel

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
