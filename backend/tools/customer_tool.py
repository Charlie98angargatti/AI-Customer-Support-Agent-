"""
tools/customer_tool.py
======================
Tool: look_up_customer
Queries the CRM database to retrieve customer profile information.

The LangGraph agent calls this tool first in any refund request to:
  1. Verify the customer exists
  2. Check their account status (active / flagged / banned)
  3. Determine their membership tier (standard / vip / premium)
     → VIP/Premium customers get extended refund windows per policy
  4. Check their 90-day refund count (fraud detection threshold = 3)

How it connects:
  agent/nodes.py → agent loop decides to call this tool
  → tool runs SQL against crm.duckdb via db_service
  → returns structured dict
  → agent incorporates result into state and reasoning
"""

from langchain_core.tools import tool
from services.db_service import execute_query
from typing import Optional


@tool
def look_up_customer(customer_id: str) -> dict:
    """
    Look up a customer by their customer ID in the CRM database.
    Returns full profile including account status, membership tier,
    and 90-day refund request count.

    Use this tool FIRST before processing any refund request to validate
    the customer's account standing.

    Args:
        customer_id: The customer's unique ID (e.g., 'C001')

    Returns:
        dict with keys: customer_id, full_name, email, membership_tier,
        account_status, refund_count_90d, join_date
        OR dict with key 'error' if not found.
    """
    rows = execute_query(
        """
        SELECT customer_id, full_name, email, phone,
               membership_tier, account_status,
               refund_count_90d, join_date, address
        FROM customers
        WHERE customer_id = ?
        """,
        [customer_id],
    )

    if not rows:
        return {"error": f"No customer found with ID '{customer_id}'"}

    customer = rows[0]
    # Convert date to string for JSON serialization
    if customer.get("join_date"):
        customer["join_date"] = str(customer["join_date"])

    return customer


@tool
def find_customer_by_email(email: str) -> dict:
    """
    Look up a customer by their email address.
    Useful when the customer doesn't know their customer ID.

    Args:
        email: Customer's registered email address

    Returns:
        Customer profile dict or error dict.
    """
    rows = execute_query(
        """
        SELECT customer_id, full_name, email, phone,
               membership_tier, account_status,
               refund_count_90d, join_date
        FROM customers
        WHERE LOWER(email) = LOWER(?)
        """,
        [email],
    )

    if not rows:
        return {"error": f"No customer found with email '{email}'"}

    customer = rows[0]
    if customer.get("join_date"):
        customer["join_date"] = str(customer["join_date"])

    return customer