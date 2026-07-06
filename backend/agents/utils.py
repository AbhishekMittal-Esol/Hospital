import json
from langchain_core.messages import SystemMessage, ToolMessage
from backend.llm import llm

# Guardrails to keep the workflow bounded.
MAX_TOOL_ITERS = 5      # tool-calling steps inside a single specialist agent
MAX_RETRIES = 1         # validator -> planner correction loops

def run_agent_loop(tools, system_prompt: str, prior_messages: list) -> list:
    """Runs a bounded ReAct loop: the model calls tools until it is done.

    Returns the list of new messages produced during this turn.
    """
    tools_by_name = {t.name: t for t in tools}
    bound_llm = llm.bind_tools(tools)

    new_messages: list = []
    for _ in range(MAX_TOOL_ITERS):
        response = bound_llm.invoke(
            [SystemMessage(content=system_prompt)] + prior_messages + new_messages
        )
        new_messages.append(response)

        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            break

        for call in tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                result = {"error": f"Unknown tool {call['name']}"}
            else:
                # Failure recovery: never let a tool exception crash the graph.
                try:
                    result = tool.invoke(call["args"])
                except Exception as exc:  # noqa: BLE001
                    result = {"error": f"Tool {call['name']} failed: {exc}"}
            new_messages.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=call["id"],
                )
            )
    return new_messages


def _collect_tool_results(messages: list, tool_name: str) -> list:
    """Pull decoded JSON payloads for a given tool from ToolMessages."""
    results = []
    # Map tool_call_id -> tool name from AI messages.
    id_to_name = {}
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            id_to_name[call["id"]] = call["name"]
    for msg in messages:
        if isinstance(msg, ToolMessage) and id_to_name.get(msg.tool_call_id) == tool_name:
            try:
                results.append(json.loads(msg.content))
            except (json.JSONDecodeError, TypeError):
                results.append({"raw": msg.content})
    return results
