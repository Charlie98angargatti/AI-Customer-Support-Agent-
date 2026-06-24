"""
agent/graph.py
==============
Builds and compiles the LangGraph agent graph.

LangGraph Graph Structure:
  START → agent_node → [tool_node → agent_node]* → END

  The square brackets indicate a loop: after tool_node runs,
  we go back to agent_node. This continues until the agent
  produces a message with no tool calls (final response).

Visual representation:
  ┌────────┐     ┌──────────────┐
  │ START  │────▶│  agent_node  │
  └────────┘     └──────┬───────┘
                        │
              ┌─────────▼──────────┐
              │  should_continue?  │
              └──┬─────────────┬───┘
              "tools"        "end"
                 │              │
         ┌───────▼──────┐   ┌──▼───┐
         │  tool_node   │   │ END  │
         └───────┬──────┘   └──────┘
                 │
         (loop back to agent_node)

Memory / Checkpointing:
  We use MemorySaver (in-memory checkpointing) so the graph can maintain
  conversation state across multiple turns within a session.
  In production, replace with SqliteSaver or RedisSaver for persistence.

How it connects:
  app.py imports build_graph() → creates a singleton compiled graph
  → each API call invokes the graph with a thread_id (session_id)
  → the graph reads/writes state to the checkpointer by thread_id
"""

"""
agent/graph.py  (FIXED)
========================
BUGS FIXED:
  1. Import was "from Models.llm import get_llm" (capital M).
     On Linux this fails because filenames are case-sensitive.
     Fixed to: "from models.llm import get_llm"

  2. tool_call_count was NOT reset between conversation turns.
     After 10 messages the counter hit MAX_TOOL_CALLS and every new
     message got the "I've reached my processing limit" safety response.
     Fix: reset tool_call_count=0 in run_agent() on every new invocation.
"""

"""
agent/graph.py  — COMPLETE REWRITE
====================================
ROOT CAUSE OF ALL PROBLEMS:
  Mistral 7B (and most 7B models via Ollama) do NOT support OpenAI-style
  function/tool calling. When you call llm.bind_tools([...]) with Mistral,
  it does not produce structured tool_call objects — it just prints
  "[Using the 'look_up_customer' tool]" as plain text because it treats
  the tool schema as something to describe, not execute.

SOLUTION:
  Replace the LangGraph bind_tools() approach with a CUSTOM AGENT LOOP:
  
  1. We send the LLM a prompt that says: output JSON like {"tool": "...", "args": {...}}
  2. We parse the JSON from the LLM response  
  3. We execute the real Python tool function ourselves
  4. We feed the result back to the LLM as context
  5. Repeat until LLM outputs a plain text final answer (no JSON tool call)

  This works with ANY model — Mistral, Llama, Qwen, etc.
  No bind_tools(), no ToolNode, no LangGraph tool routing needed.

SECURITY:
  The final response sent to the customer is ONLY the "final_answer" text.
  Tool results, customer data, order details are NEVER sent to the frontend.
  The frontend only ever sees the clean text from the "final_answer" field.
"""

"""
agent/graph.py  — FINAL CLEAN VERSION
=======================================
Architecture: Custom JSON-based agent loop (no bind_tools)

WHY NOT bind_tools():
  Mistral 7B via Ollama does not produce structured tool_call objects.
  It prints "[Using the 'look_up_customer' tool]" as plain text.
  Solution: teach the model to output JSON, parse it ourselves, run the tool.

FIXES IN THIS VERSION vs previous:
  1. Import fixed: "from models.llm" not "from Models.llm" (case sensitivity)
  2. Amount hallucination fixed: process_refund is now called by Python code,
     not by the LLM. The LLM only decides APPROVE/DENY. Python handles amounts.
  3. Reason detection fixed: we check if reason is present in the first message
     before calling the LLM, and skip the ask-for-reason step automatically.
  4. History is properly scoped per session with no bleed between sessions.
"""

"""
agent/graph.py
==============
Builds and compiles the real LangGraph agent graph.

Graph structure:

  START --> agent_node --> [should_continue?]
                |                |
              "tools"          "end"
                |                |
            tool_node           END
                |
        (loop back to agent_node)

  ┌────────┐     ┌──────────────┐
  │ START  │────▶│  agent_node  │◀────────────┐
  └────────┘     └──────┬───────┘             │
                        │                     │
              ┌─────────▼──────────┐          │
              │  should_continue?  │          │
              └──┬─────────────┬───┘          │
              "tools"        "end"            │
                 │              │              │
         ┌───────▼──────┐   ┌──▼───┐          │
         │  tool_node   │   │ END  │          │
         └───────┬──────┘   └──────┘          │
                 │                             │
                 └─────────────────────────────┘

Why this is genuine LangGraph (not just a while-loop with a new name):
  - State is a typed schema (agent/state.py) merged automatically by
    LangGraph's reducers (add_messages appends rather than overwrites).
  - Routing is a real conditional edge (`add_conditional_edges`), not an
    if/else inside a Python loop.
  - MemorySaver checkpoints state per `thread_id` (session_id), so a new
    process or request can resume a session by thread_id alone -- no
    hand-rolled `_memory: dict` module global.
  - tool_call_count lives IN the checkpointed state and is explicitly
    reset to 0 on every new run_agent() call, which is what actually
    fixes the "stuck after 10 messages" bug your comments describe --
    previously the counter was reset, but it was reset in a plain Python
    dict that wasn't the source of truth the graph reasoned over.

What's custom (and why): see the module docstring in agent/nodes.py.
Mistral-7B via Ollama has no native tool-calling, so the *tool-call
extraction* is a JSON parse instead of `message.tool_calls`. The graph
itself -- nodes, edges, state, checkpointing -- is unmodified LangGraph.
To go fully "vanilla" (bind_tools + prebuilt ToolNode), swap the model
in models/llm.py for one with native function calling (e.g. Ollama's
`mistral-nemo`/`qwen2.5`, or OpenAI/Anthropic) and replace
make_agent_node/make_tool_node accordingly -- the wiring below does not
need to change.
"""

"""
agent/graph.py
==============
Builds and compiles the real LangGraph agent graph — Mistral (Ollama)
version, using custom JSON tool-call parsing (see agent/nodes.py
docstring for why: plain `mistral` has no native function calling).

Graph structure:

  ┌────────┐     ┌──────────────┐
  │ START  │────▶│  agent_node  │◀────────────┐
  └────────┘     └──────┬───────┘             │
                        │                     │
              ┌─────────▼──────────┐          │
              │  should_continue?  │          │
              └──┬─────────────┬───┘          │
              "tools"        "end"            │
                 │              │              │
         ┌───────▼──────┐   ┌──▼───┐          │
         │  tool_node   │   │ END  │          │
         └───────┬──────┘   └──────┘          │
                 │                             │
                 └─────────────────────────────┘

Why this is genuine LangGraph (not just a while-loop with a new name):
  - State is a typed schema (agent/state.py) merged automatically by
    LangGraph's reducers (add_messages appends rather than overwrites).
  - Routing is a real conditional edge (`add_conditional_edges`), not an
    if/else inside a Python loop.
  - MemorySaver checkpoints state per `thread_id` (session_id), so a new
    process or request can resume a session by thread_id alone -- no
    hand-rolled `_memory: dict` module global.
  - tool_call_count lives IN the checkpointed state and is explicitly
    reset to 0 on every new run_agent() call (a per-turn budget, not a
    per-session lifetime counter).

What's custom (and why): see the module docstring in agent/nodes.py.
Mistral-7B via Ollama has no native tool-calling, so the *tool-call
extraction* is a JSON parse instead of `message.tool_calls`. The graph
itself -- nodes, edges, state, checkpointing -- is unmodified LangGraph.
"""

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


# from langgraph.graph import StateGraph, START, END
# from langgraph.checkpoint.memory import MemorySaver
# from langchain_core.messages import HumanMessage, AIMessage

# from agent.state import AgentState
# from agent.nodes import make_agent_node, make_tool_node, should_continue
# from Models.llm import get_llm

# _compiled_graph = None


# def build_graph():
#     """
#     Constructs and compiles the LangGraph agent graph.
#     Called once at server startup (e.g. from app.py).
#     """
#     global _compiled_graph
#     if _compiled_graph is not None:
#         return _compiled_graph

#     print("Loading LLM...")
#     llm = get_llm(temperature=0.0)
#     print("LLM loaded.")

#     agent_node = make_agent_node(llm)
#     tool_node = make_tool_node(lambda state: state.get("session_id", "unknown"))

#     graph = StateGraph(AgentState)
#     graph.add_node("agent", agent_node)
#     graph.add_node("tools", tool_node)

#     graph.add_edge(START, "agent")
#     graph.add_conditional_edges(
#         "agent",
#         should_continue,
#         {"tools": "tools", "end": END},
#     )
#     graph.add_edge("tools", "agent")

#     memory = MemorySaver()
#     _compiled_graph = graph.compile(checkpointer=memory)
#     return _compiled_graph


# def run_agent(session_id: str, user_message: str) -> str:
#     """
#     Main entry point called by app.py for every chat message.

#     `thread_id=session_id` ties this call to the checkpointed state for
#     that session -- prior customer_id/order_id/refund_reason/tool results
#     are restored automatically by MemorySaver, no manual dict needed.

#     tool_call_count is explicitly reset to 0 here, every call, because it
#     is a PER-TURN budget (how many tool calls this one message triggers),
#     not a per-session lifetime counter.
#     """
#     graph = build_graph()
#     config = {"configurable": {"thread_id": session_id}}

#     input_state = {
#         "messages": [HumanMessage(content=user_message)],
#         "session_id": session_id,
#         "tool_call_count": 0,
#         "final_answer": None,
#     }

#     final_state = graph.invoke(input_state, config=config)

#     final_answer = final_state.get("final_answer")
#     if final_answer:
#         return final_answer

#     for msg in reversed(final_state.get("messages", [])):
#         if isinstance(msg, AIMessage) and msg.content:
#             return msg.content

#     return ("I was unable to process your request. "
#             "Please contact support@shopease.com with your Order ID.")


# from langgraph.graph import StateGraph, START, END
# from langgraph.checkpoint.memory import MemorySaver
# from agent.state import AgentState
# from agent.nodes import make_agent_node, make_tool_node, should_continue
# from Models.llm import get_llm          # Fixed: was "Models.llm" (capital M)

# _compiled_graph = None


# def build_graph():
#     global _compiled_graph
#     if _compiled_graph is not None:
#         return _compiled_graph

#     print("Loading LLM...")
#     llm = get_llm(temperature=0.0)
#     print("LLM loaded.")

#     agent_node = make_agent_node(llm)
#     tool_node  = make_tool_node(lambda state: state.get("session_id", "unknown"))

#     graph = StateGraph(AgentState)
#     graph.add_node("agent", agent_node)
#     graph.add_node("tools", tool_node)

#     graph.add_edge(START, "agent")
#     graph.add_conditional_edges(
#         "agent",
#         should_continue,
#         {"tools": "tools", "end": END}
#     )
#     graph.add_edge("tools", "agent")

#     memory = MemorySaver()
#     _compiled_graph = graph.compile(checkpointer=memory)
#     return _compiled_graph


# def run_agent(session_id: str, user_message: str) -> str:
#     from langchain_core.messages import HumanMessage, AIMessage

#     graph = build_graph()
#     config = {"configurable": {"thread_id": session_id}}

#     # FIXED: tool_call_count resets to 0 on every new user message.
#     # Previously it accumulated across turns, causing the safety limit
#     # to fire after 10 total tool calls across the whole conversation.
#     input_state = {
#         "messages": [HumanMessage(content=user_message)],
#         "session_id": session_id,
#         "customer_data": None,
#         "order_data": None,
#         "policy_result": None,
#         "final_decision": None,
#         "tool_call_count": 0,      # Always reset for each new turn
#     }

#     final_state = graph.invoke(input_state, config=config)

#     messages = final_state.get("messages", [])
#     for msg in reversed(messages):
#         if isinstance(msg, AIMessage) and msg.content:
#             return msg.content

#     return "I was unable to process your request. Please try again or contact support@shopease.com."




# from langgraph.graph import StateGraph, START, END
# from langgraph.checkpoint.memory import MemorySaver
# from agent.state import AgentState
# from agent.nodes import make_agent_node, make_tool_node, should_continue
# from Models.llm import get_llm

# # ── Module-level singleton ──────────────────────────────────────────────────
# # The compiled graph is expensive to build (loads LLM, registers tools).
# # We build it once at startup and reuse it for all requests.
# _compiled_graph = None


# def build_graph():
#     """
#     Constructs and compiles the LangGraph agent graph.
#     Returns a compiled CompiledGraph object ready for invocation.

#     This is called once at server startup (in app.py).
#     """
#     global _compiled_graph
#     if _compiled_graph is not None:
#         return _compiled_graph

#     # ── 1. Initialize the LLM ─────────────────────────────────────────────
#     # llm = get_llm(temperature=0.0)
#     try:
#         print("Loading LLM...")
#         llm = get_llm(temperature=0.0)
#         print("LLM Loaded Successfully")
#     except Exception as e:
#         import traceback
#         print("\nLLM LOAD FAILED\n")
#         traceback.print_exc()
#         raise

#     # ── 2. Create node functions ──────────────────────────────────────────
#     agent_node = make_agent_node(llm)
#     tool_node = make_tool_node(lambda state: state.get("session_id", "unknown"))

#     # ── 3. Build the graph ─────────────────────────────────────────────────
#     graph = StateGraph(AgentState)

#     # Add nodes
#     graph.add_node("agent", agent_node)
#     graph.add_node("tools", tool_node)

#     # Add edges
#     graph.add_edge(START, "agent")   # Always start at the agent node

#     # Conditional edge: after agent_node, decide to loop or end
#     graph.add_conditional_edges(
#         "agent",
#         should_continue,
#         {
#             "tools": "tools",  # → tool_node if tool call requested
#             "end": END,        # → END if final response
#         }
#     )

#     # After tools run, always go back to the agent for next reasoning step
#     graph.add_edge("tools", "agent")

#     # ── 4. Add memory checkpointing ───────────────────────────────────────
#     # MemorySaver stores conversation state keyed by thread_id.
#     # Each session_id becomes a separate "thread" — isolated conversation state.
#     memory = MemorySaver()

#     # ── 5. Compile ────────────────────────────────────────────────────────
#     _compiled_graph = graph.compile(checkpointer=memory)

#     return _compiled_graph


# def run_agent(session_id: str, user_message: str) -> str:
#     """
#     Runs the agent for a single user message within a session.

#     The thread_id in the config ties this invocation to prior messages
#     in the same session — the checkpointer restores that conversation state.

#     Args:
#         session_id: Unique session identifier (used as thread_id)
#         user_message: The customer's text input

#     Returns:
#         The agent's final text response as a string.
#     """
#     from langchain_core.messages import HumanMessage

#     graph = build_graph()

#     # Config tells LangGraph which conversation thread to use
#     config = {"configurable": {"thread_id": session_id}}

#     # Input: just the new human message (prior history is in the checkpointer)
#     input_state = {
#         "messages": [HumanMessage(content=user_message)],
#         "session_id": session_id,
#         "customer_data": None,
#         "order_data": None,
#         "policy_result": None,
#         "final_decision": None,
#         "tool_call_count": 0,
#     }

#     # Invoke the graph — this runs the full agent loop until END
#     final_state = graph.invoke(input_state, config=config)

#     # Extract the last AIMessage content as the response
#     messages = final_state.get("messages", [])
#     from langchain_core.messages import AIMessage
#     for msg in reversed(messages):
#         if isinstance(msg, AIMessage) and msg.content:
#             return msg.content

#     return "I'm sorry, I couldn't process your request. Please try again."