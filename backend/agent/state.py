"""
agent/state.py
==============
Defines the AgentState TypedDict used by the LangGraph graph.

In LangGraph, the "state" is a shared object passed between every node.
Each node can read from and write to this state.

Think of it as the agent's working memory for a single conversation turn:
  - What did the user say? (messages)
  - What customer/order have we looked up so far? (customer_data, order_data)
  - What did the policy check conclude? (policy_result)
  - What decision have we made? (final_decision)
  - What session is this? (session_id — for log grouping)
  - How many tool calls have we made? (tool_call_count — loop safety)

The `messages` list is a standard LangChain Messages list:
  [HumanMessage, AIMessage, ToolMessage, AIMessage, ...]
This is what gets sent to the LLM on each invocation.

The `add_messages` reducer merges new messages into the list
(instead of replacing it), which is the correct behavior for a chat loop.
"""

"""
agent/state.py
===============
TypedDict schema for the LangGraph agent state.

This is the single source of truth that flows through every node.
LangGraph merges returned partial-state dicts into this on each step.
"""

"""
agent/state.py
===============
TypedDict schema for the LangGraph agent state.

This is the single source of truth that flows through every node.
LangGraph merges returned partial-state dicts into this on each step.
"""

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


# from typing import TypedDict, Optional, Annotated
# from langchain_core.messages import BaseMessage
# from langgraph.graph.message import add_messages


# class AgentState(TypedDict):
#     # `messages` uses the add_messages reducer: every node that returns
#     # {"messages": [...]} APPENDS to the list rather than overwriting it.
#     messages: Annotated[list[BaseMessage], add_messages]

#     session_id: str

#     # Slot-filling memory carried across turns within a session.
#     # These persist via the checkpointer (MemorySaver) keyed by thread_id.
#     customer_id: Optional[str]
#     order_id: Optional[str]
#     refund_reason: Optional[str]

#     # Tool results, cached once fetched so we don't re-call tools
#     # unnecessarily and so process_refund can use exact, non-hallucinated values.
#     customer_data: Optional[dict]
#     order_data: Optional[dict]
#     policy_result: Optional[dict]
#     refund_result: Optional[dict]

#     # Safety valve: hard cap on tool-calling iterations per turn.
#     # Reset to 0 at the start of every new user message (see graph.py).
#     tool_call_count: int

#     # Set by the agent node when it has produced a customer-facing final
#     # answer (no further tool call requested). Routing reads this to
#     # decide whether to go to "tools" or to END.
#     final_answer: Optional[str]


# from typing import TypedDict, Optional, Annotated
# from langchain_core.messages import BaseMessage
# from langgraph.graph.message import add_messages


# class AgentState(TypedDict):
#     # ── Conversation history ───────────────────────────────────────────────
#     # Annotated with add_messages so LangGraph merges new messages
#     # instead of overwriting the list on each graph step.
#     messages: Annotated[list[BaseMessage], add_messages]

#     # ── Session metadata ───────────────────────────────────────────────────
#     session_id: str                  # Unique ID for log grouping

#     # ── Data collected by tools ────────────────────────────────────────────
#     customer_data: Optional[dict]    # Result from look_up_customer
#     order_data: Optional[dict]       # Result from look_up_order
#     policy_result: Optional[dict]    # Result from check_refund_policy

#     # ── Agent decision ─────────────────────────────────────────────────────
#     final_decision: Optional[str]    # "APPROVE" | "PARTIAL" | "DENY" | "ESCALATE" | "INFO"

#     # ── Safety counter ─────────────────────────────────────────────────────
#     # Prevents infinite tool-call loops (max 10 iterations)
#     tool_call_count: int

# from typing import TypedDict, Optional, Annotated
# from langchain_core.messages import BaseMessage
# from langgraph.graph.message import add_messages


# class AgentState(TypedDict):
#     # ── Conversation history ───────────────────────────────────────────────
#     # Annotated with add_messages so LangGraph merges new messages
#     # instead of overwriting the list on each graph step.
#     messages: Annotated[list[BaseMessage], add_messages]

#     # ── Session metadata ───────────────────────────────────────────────────
#     session_id: str                  # Unique ID for log grouping

#     # ── Data collected by tools ────────────────────────────────────────────
#     customer_data: Optional[dict]    # Result from look_up_customer
#     order_data: Optional[dict]       # Result from look_up_order
#     policy_result: Optional[dict]    # Result from check_refund_policy

#     # ── Agent decision ─────────────────────────────────────────────────────
#     final_decision: Optional[str]    # "APPROVE" | "PARTIAL" | "DENY" | "ESCALATE" | "INFO"

#     # ── Safety counter ─────────────────────────────────────────────────────
#     # Prevents infinite tool-call loops (max 10 iterations)
#     tool_call_count: int