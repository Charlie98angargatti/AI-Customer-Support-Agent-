"""
tools/order_tool.py
====================
Tool: look_up_order
Queries order details from the database to validate refund eligibility.

The agent uses this to determine:
  1. Order amount (threshold checks: <$10 = deny; >$500 = manager approval)
  2. Category (electronics=15d, food=3d, digital=non-refundable, standard=30d)
  3. Delivery date (used to calculate if still within the refund window)
  4. Whether the item was delivered and if delivery required a signature
     (signed delivery with customer claiming non-receipt → policy denial)
  5. Current order status (shipped/pending cannot be "refund for damage" yet)

How it connects:
  agent/nodes.py → calls this after look_up_customer
  → result fed into state['order_details']
  → policy_tool uses the order details to evaluate eligibility
"""

from langchain_core.tools import tool
from services.db_service import execute_query
from datetime import date


@tool
def look_up_order(order_id: str) -> dict:
    """
    Retrieve full order details by order ID, including the customer's name
    for cross-validation.

    Args:
        order_id: The order identifier (e.g., 'ORD-1001')

    Returns:
        dict with order details including category, amount, delivery_date,
        status, and customer info. Returns error dict if not found.
    """
    rows = execute_query(
        """
        SELECT o.order_id,
               o.customer_id,
               c.full_name      AS customer_name,
               o.product_name,
               o.category,
               CAST(o.amount AS DOUBLE) AS amount,
               CAST(o.order_date AS VARCHAR) AS order_date,
               CAST(o.delivery_date AS VARCHAR) AS delivery_date,
               o.status,
               o.tracking_number,
               o.delivery_signed
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        WHERE o.order_id = ?
        """,
        [order_id],
    )

    if not rows:
        return {"error": f"No order found with ID '{order_id}'"}

    order = rows[0]

    # ── Calculate days since delivery (for window checks) ──────────────────
    if order.get("delivery_date"):
        delivery = date.fromisoformat(order["delivery_date"])
        days_since_delivery = (date.today() - delivery).days
        order["days_since_delivery"] = days_since_delivery
    else:
        order["days_since_delivery"] = None  # Not yet delivered

    return order


@tool
def get_customer_orders(customer_id: str) -> list:
    """
    Get all orders for a specific customer.
    Useful for giving the customer a summary of eligible orders.

    Args:
        customer_id: The customer's ID (e.g., 'C001')

    Returns:
        List of order dicts, most recent first.
    """
    rows = execute_query(
        """
        SELECT order_id, product_name, category,
               CAST(amount AS DOUBLE) AS amount,
               CAST(order_date AS VARCHAR) AS order_date,
               CAST(delivery_date AS VARCHAR) AS delivery_date,
               status
        FROM orders
        WHERE customer_id = ?
        ORDER BY order_date DESC
        """,
        [customer_id],
    )

    return rows if rows else []