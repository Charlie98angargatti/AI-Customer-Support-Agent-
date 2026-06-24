from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage

from agent.state import AgentState
from agent.nodes import make_agent_node, make_tool_node, should_continue
from Models.llm import get_llm

_compiled_graph = None


def build_graph():
    """
    Constructs and compiles the LangGraph agent graph.
    Called once at server startup (e.g. from app.py).
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    print("Loading LLM...")
    llm = get_llm(temperature=0.0)
    print("LLM loaded.")

    agent_node = make_agent_node(llm)
    tool_node = make_tool_node(lambda state: state.get("session_id", "unknown"))

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    graph.add_edge("tools", "agent")

    memory = MemorySaver()
    _compiled_graph = graph.compile(checkpointer=memory)
    return _compiled_graph


def run_agent(session_id: str, user_message: str) -> str:
    """
    Main entry point called by app.py for every chat message.

    `thread_id=session_id` ties this call to the checkpointed state for
    that session -- prior customer_id/order_id/refund_reason/tool results
    are restored automatically by MemorySaver, no manual dict needed.

    tool_call_count is explicitly reset to 0 here, every call, because it
    is a PER-TURN budget (how many tool calls this one message triggers),
    not a per-session lifetime counter.
    """
    graph = build_graph()
    config = {"configurable": {"thread_id": session_id}}

    input_state = {
        "messages": [HumanMessage(content=user_message)],
        "session_id": session_id,
        "tool_call_count": 0,
        "final_answer": None,
    }

    final_state = graph.invoke(input_state, config=config)

    final_answer = final_state.get("final_answer")
    if final_answer:
        return final_answer

    for msg in reversed(final_state.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content

    return ("I was unable to process your request. "
            "Please contact support@shopease.com with your Order ID.")
