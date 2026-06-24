"""
tools/refund_tool.py
=====================
Tool: process_refund
Writes an approved refund record to the database and updates customer state.

This tool is only called AFTER check_refund_policy returns eligible=True.
It's a "write" action — the terminal step before the agent responds.

What it does:
  1. Inserts a new record into the refunds table
  2. Increments the customer's refund_count_90d
  3. Returns a confirmation with refund ID and expected timeline

Security consideration: In production, this would trigger a payment gateway
API call (Razorpay refund, Stripe refund, etc.). In our mock, it writes to DB.

How it connects:
  agent/nodes.py (finalize_decision) → calls process_refund if approved
  → writes to crm.duckdb
  → agent includes refund_id in the response to the customer (translated into
    plain language — the agent must never mention this tool's name to the customer)
"""

from langchain_core.tools import tool
from services.db_service import execute_write, execute_query
from datetime import datetime
import uuid


@tool
def process_refund(
    order_id: str,
    customer_id: str,
    refund_reason: str,
    refund_amount: float,
    refund_type: str,
    agent_notes: str = "",
) -> dict:
    """
    Record an approved refund in the database.
    Only call this after check_refund_policy confirms the refund is eligible.

    Args:
        order_id: The order being refunded
        customer_id: The customer receiving the refund
        refund_reason: Customer's stated reason
        refund_amount: Exact amount to refund (in INR)
        refund_type: "full" or "partial_50"
        agent_notes: Summary of agent reasoning for the admin log

    Returns:
        dict with refund_id, status, estimated_completion, and message.
    """
    refund_id = f"REF-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.utcnow().isoformat()

    # ── Insert the refund record ───────────────────────────────────────────
    execute_write(
        """
        INSERT INTO refunds
            (refund_id, order_id, customer_id, reason, status, amount,
             requested_at, resolved_at, agent_notes)
        VALUES (?, ?, ?, ?, 'approved', ?, ?, ?, ?)
        """,
        [
            refund_id, order_id, customer_id, refund_reason,
            refund_amount, now, now, agent_notes,
        ],
    )

    # ── Increment the customer's 90-day refund counter ────────────────────
    execute_write(
        """
        UPDATE customers
        SET refund_count_90d = refund_count_90d + 1
        WHERE customer_id = ?
        """,
        [customer_id],
    )

    # Determine estimated timeline based on amount (INR thresholds)
    if refund_amount > 40000:
        timeline = "7–10 business days (manager approval required)"
    else:
        timeline = "5–10 business days to original payment method, or 24 hours as store credit"

    return {
        "success": True,
        "refund_id": refund_id,
        "order_id": order_id,
        "approved_amount": refund_amount,
        "refund_type": refund_type,
        "status": "approved",
        "estimated_completion": timeline,
        "message": (
            f"Refund {refund_id} has been approved and recorded. "
            f"₹{refund_amount:,.2f} will be returned within {timeline}."
        ),
    }


@tool
def get_refund_history(customer_id: str) -> list:
    """
    Retrieve the refund history for a customer.
    Used by the agent to inform the customer of past refund outcomes.

    Args:
        customer_id: Customer ID

    Returns:
        List of refund records (most recent first)
    """
    rows = execute_query(
        """
        SELECT r.refund_id, r.order_id, o.product_name,
               CAST(r.amount AS DOUBLE) AS amount,
               r.reason, r.status,
               CAST(r.requested_at AS VARCHAR) AS requested_at
        FROM refunds r
        JOIN orders o ON r.order_id = o.order_id
        WHERE r.customer_id = ?
        ORDER BY r.requested_at DESC
        LIMIT 10
        """,
        [customer_id],
    )
    return rows if rows else []