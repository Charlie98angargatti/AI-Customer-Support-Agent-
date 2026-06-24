from typing import TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # `messages` uses the add_messages reducer: every node that returns
    # {"messages": [...]} APPENDS to the list rather than overwriting it.
    messages: Annotated[list[BaseMessage], add_messages]

    session_id: str

    # Slot-filling memory carried across turns within a session.
    # These persist via the checkpointer (MemorySaver) keyed by thread_id.
    customer_id: Optional[str]
    order_id: Optional[str]
    refund_reason: Optional[str]

    # Tool results, cached once fetched so we don't re-call tools
    # unnecessarily and so process_refund can use exact, non-hallucinated values.
    customer_data: Optional[dict]
    order_data: Optional[dict]
    policy_result: Optional[dict]
    refund_result: Optional[dict]

    # Safety valve: hard cap on tool-calling iterations per turn.
    # Reset to 0 at the start of every new user message (see graph.py).
    tool_call_count: int

    # Set by the agent node when it has produced a customer-facing final
    # answer (no further tool call requested). Routing reads this to
    # decide whether to go to "tools" or to END.
    final_answer: Optional[str]
