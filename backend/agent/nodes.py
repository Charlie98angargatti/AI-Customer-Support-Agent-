import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.state import AgentState
from agent.prompts import build_system_prompt
from services.log_service import log_step

MAX_TOOL_CALLS = 10

# Tool functions the agent is allowed to invoke via its JSON protocol.
# process_refund is deliberately NOT in here -- it is called directly by
# tool_node once check_refund_policy returns an approved/partial decision,
# using the exact amount from that result. The LLM never supplies
# refund_amount, even indirectly.

REASON_KEYWORDS = [
    "wrong item", "wrong item shipped", "wrong product", "incorrect item",
    "received wrong item", "wrong product received", "received different item",
    "received shirt", "received tshirt", "received t-shirt", "received jacket",
    "different item",
    "damaged", "defective", "broken", "faulty", "not working",
    "does not work", "doesn't work",
    "wrong size", "size issue", "too big", "too small", "doesn't fit",
    "changed mind", "change of mind",
    "wrong colour", "wrong color",
    "not as described",
]


# ── Agent node ───────────────────────────────────────────────────────────────

def make_agent_node(llm):
    """
    Returns a node function bound to the given LLM instance (plain Ollama
    `mistral`, no bind_tools()).

    Each call:
      1. Auto-fills customer_id / order_id / refund_reason slots from the
         latest human message.
      2. If we have an order but still no refund reason, asks for it once
         and stops -- deterministically, without calling the LLM.
      3. Otherwise invokes the LLM, which follows the STRICT WORKFLOW in
         the system prompt and emits either a JSON tool call or a
         <final_answer>.
      4. Parses the response accordingly.
    """
    def agent_node(state: AgentState) -> dict:
        session_id = state["session_id"]
        updates: dict = {}

        last_human = _last_human_text(state["messages"])

        if last_human:
            cid, oid = _extract_ids(last_human)
            if cid and not state.get("customer_id"):
                updates["customer_id"] = cid
            if oid and not state.get("order_id"):
                updates["order_id"] = oid

            if not state.get("refund_reason") and _has_reason(last_human):
                updates["refund_reason"] = last_human
                log_step(session_id, "refund_reason_detected",
                         reasoning=f"Detected refund reason: {last_human}",
                         status="success")

        have_order = bool(state.get("order_data"))
        have_reason = bool(state.get("refund_reason") or updates.get("refund_reason"))

        # Deterministic short-circuit: order known, reason still missing ->
        # ask once and stop. This is the ONLY place that asks for a reason
        # in the whole file -- once refund_reason lands in state (next
        # turn), have_reason becomes True and this branch never fires again.
        if have_order and not have_reason:
            order = state["order_data"]
            text = (
                f"I found your order:\n\n"
                f"Product: {order.get('product_name', 'N/A')}\n"
                f"Amount: \u20b9{order.get('amount', 'N/A')}\n\n"
                f"Please provide the reason for the refund."
            )
            updates["final_answer"] = text
            updates["messages"] = [AIMessage(content=text)]
            return updates

        system = SystemMessage(content=build_system_prompt())
        messages = [system] + state["messages"]

        response = llm.invoke(messages)
        raw = _clean(response.content if hasattr(response, "content") else str(response))

        log_step(session_id, "agent_node",
                 output_summary=raw[:200],
                 reasoning=f"LLM turn: {raw[:150]}",
                 status="running")

        tool_call = _parse_tool_call(raw)

        if tool_call:
            updates["messages"] = [AIMessage(
                content=raw,
                additional_kwargs={"parsed_tool_call": tool_call},
            )]
            updates["final_answer"] = None
            return updates

        final = _extract_final_answer(raw) or raw
        updates["messages"] = [AIMessage(content=final)]
        updates["final_answer"] = final
        return updates

    return agent_node


# ── Tool node ────────────────────────────────────────────────────────────────

def make_tool_node(get_session_id):
    """
    Returns a node function that:
      1. Reads the parsed tool call off the last AIMessage.
      2. Runs the corresponding Python tool.
      3. If the tool was check_refund_policy and it approved/partial-approved,
         calls process_refund directly with the EXACT amount from the policy
         result -- the LLM never sees or supplies refund_amount.
      4. Feeds the tool result back in as a HumanMessage labeled as a tool
         result (Mistral has no native ToolMessage handling), and caches
         structured results onto state for later use / final-answer grounding.
    """
    def tool_node(state: AgentState) -> dict:
        session_id = get_session_id(state)
        last_msg = state["messages"][-1]
        tool_call = last_msg.additional_kwargs.get("parsed_tool_call", {})
        tool_name = tool_call.get("tool", "")
        tool_args = dict(tool_call.get("args", {}))

        # Backfill args from state slot-memory if the model omitted them.
        tool_args.setdefault("customer_id", state.get("customer_id"))
        tool_args.setdefault("order_id", state.get("order_id"))
        tool_args.setdefault("refund_reason", state.get("refund_reason"))

        count = state.get("tool_call_count", 0) + 1

        if count > MAX_TOOL_CALLS:
            log_step(session_id, "tool_limit_reached", status="error",
                     reasoning="MAX_TOOL_CALLS exceeded; forcing safe stop.")
            return {
                "messages": [HumanMessage(
                    content="[SYSTEM]: Tool call limit reached. "
                            "You must respond now with a <final_answer> "
                            "telling the customer to contact support@shopease.com."
                )],
                "tool_call_count": count,
            }

        log_step(session_id, f"tool_call:{tool_name}",
                 tool_called=tool_name,
                 input_summary=str(tool_args)[:200],
                 reasoning=f"Running {tool_name}({tool_args})",
                 status="running")

        result = _execute_tool(tool_name, tool_args)

        state_updates = {"tool_call_count": count}

        if "error" not in result:
            if tool_name == "look_up_customer":
                state_updates["customer_data"] = result
                state_updates["customer_id"] = result.get("customer_id", state.get("customer_id"))

            elif tool_name == "look_up_order":
                state_updates["order_data"] = result
                state_updates["order_id"] = result.get("order_id", state.get("order_id"))
                # Auto-fill customer_id from the order record too, since the
                # customer often only gives an order_id, not a customer_id.
                state_updates["customer_id"] = result.get("customer_id", state.get("customer_id"))

            elif tool_name == "check_refund_policy":
                state_updates["policy_result"] = result

                if result.get("eligible") and result.get("recommendation") in ("APPROVE", "PARTIAL"):
                    # CRITICAL: the refund amount comes from the policy tool's
                    # own float, never from anything the LLM wrote in its JSON.
                    exact_amount = float(result["refund_amount"])
                    refund_reason = (
                        tool_args.get("refund_reason")
                        or state.get("refund_reason")
                        or "Customer request"
                    )
                    refund_result = process_refund.invoke({
                        "order_id":      state_updates.get("order_id") or state.get("order_id") or tool_args.get("order_id", ""),
                        "customer_id":   state_updates.get("customer_id") or state.get("customer_id") or tool_args.get("customer_id", ""),
                        "refund_reason": refund_reason,
                        "refund_amount": exact_amount,
                        "refund_type":   result["refund_type"],
                        "agent_notes":   f"Auto-{result.get('recommendation')} per policy engine.",
                    })
                    state_updates["refund_result"] = refund_result
                    result = {**result, "refund_result": refund_result}

                    log_step(session_id, "refund_processed",
                             tool_called="process_refund",
                             output_summary=str(refund_result)[:200],
                             reasoning=(f"Refund {refund_result.get('refund_id')} "
                                        f"processed for an exact amount computed by "
                                        f"Python, not the LLM."),
                             status="success")

        log_step(session_id, f"tool_result:{tool_name}",
                 tool_called=tool_name,
                 output_summary=str(result)[:250],
                 reasoning=f"Result: {str(result)[:200]}",
                 status="success" if "error" not in result else "error")

        state_updates["messages"] = [HumanMessage(
            content=f"[TOOL RESULT: {tool_name}]\n{json.dumps(result, default=str)}"
        )]
        return state_updates

    return tool_node


# ── Conditional routing ──────────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    """
    Reads the last message. If the agent node attached a parsed tool call,
    route to "tools". Otherwise the agent produced a final answer -> "end".
    """
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.additional_kwargs.get("parsed_tool_call"):
        return "tools"
    return "end"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _last_human_text(messages) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and not msg.content.startswith("[TOOL RESULT"):
            return msg.content
    return ""


def _has_reason(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in REASON_KEYWORDS)


def _extract_ids(text: str):
    cid_match = re.search(r"\b(C\d{3})\b", text, re.IGNORECASE)
    oid_match = re.search(r"\b(ORD-\d{3,6})\b", text, re.IGNORECASE)
    cid = cid_match.group(1).upper() if cid_match else None
    oid = oid_match.group(1).upper() if oid_match else None
    return cid, oid


def _execute_tool(tool_name: str, tool_args: dict) -> dict:
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool '{tool_name}'. Valid: {list(TOOL_REGISTRY.keys())}"}
    try:
        return TOOL_REGISTRY[tool_name](tool_args)
    except Exception as e:
        return {"error": f"{tool_name} failed: {str(e)}"}


def _clean(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"Assisted by [^\n]+\n*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*Assistant:\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _parse_tool_call(text: str) -> dict | None:
    """Extracts a {"tool": ..., "args": {...}} JSON object from raw LLM text."""
    if not text:
        return None

    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(1))
            if "tool" in d:
                return d
        except Exception:
            pass

    m = re.search(r'\{[^{}]*"tool"\s*:\s*"[^"]+?"[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            if "tool" in d:
                return d
        except Exception:
            pass

    for block in re.findall(r"\{(?:[^{}]|\{[^{}]*\})*\}", text, re.DOTALL):
        try:
            d = json.loads(block)
            if "tool" in d and isinstance(d.get("args"), dict):
                return d
        except Exception:
            pass

    return None


def _extract_final_answer(text: str) -> str | None:
    """Extracts customer-facing text from the LLM's response, if present."""
    if not text:
        return None

    m = re.search(r"<final_answer>(.*?)</final_answer>", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    if "**Decision:**" in text and "**Refund Amount:**" in text:
        return text.strip()

    return None
