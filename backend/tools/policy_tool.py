"""
policy_tool.py  (FIXED)
========================
BUGS FIXED IN THIS VERSION:

BUG 1 — Food/perishable reason handling:
  OLD: If reason didn't match any keyword list → defaulted to "partial_50"
       This wrongly approved partial refunds for food items with vague reasons.
  FIX: Food category only accepts damage/quality/wrong-item reasons for full refund.
       "Changed mind" on food = DENIED (perishable, cannot be resold).

BUG 2 — 72-hour defective check was too strict:
  OLD: days_since_delivery > 3 → denied (so day 3 itself was blocked)
  FIX: days_since_delivery > 3 only (day 3 is still within 72 hours window).
       This is correct — policy says "within 72 hours" = days 0, 1, 2, 3.

BUG 3 — Food window boundary:
  OLD: days_since_delivery > effective_window → denied
       For food (window=3): day 3 > 3 = False → passes (correct per policy)
       But then reason check would incorrectly allow partial refund for food.
  FIX: Explicit food-category reason validation prevents wrong approvals.

BUG 4 — Missing "quality" and "spoiled" keywords for food:
  FIX: Added food-specific keywords: spoiled, rotten, expired, bad quality,
       wrong item, not fresh — these map to full refund for food.
"""

"""
tools/policy_tool.py  — FIXED for INR + correct policy rules
=============================================================
Changes from previous version:
  - Amount thresholds updated to INR:
      Minimum:   ₹500  (was $10)
      Manager:   ₹41,500  (was $500)
      Executive: ₹83,000  (was $1000)
  - Food category: only damage/quality/wrong-item → full refund
    Change of mind on food = DENIED
  - Defective report window: strictly > 3 days since delivery
  - Vague reasons default to partial_50 (changed mind equivalent)
  - Returns plain denial_reason string (not a list) so LLM can read it easily
"""

"""
tools/policy_tool.py  — FINAL VERSION
=======================================
Enforces ALL rules from refund_policy.txt (Version 3.3 INR).

INR Thresholds (from your refund_policy.txt):
  Minimum:   ₹800
  Manager:   ₹40,000
  Executive: ₹80,000

Category windows:
  digital:      0 days (non-refundable)
  food:         3 days
  electronics: 15 days
  clothing:    30 days
  standard:    30 days
  bundle:      30 days
  personalized: 0 days (non-refundable unless damaged/defective)
"""

from langchain_core.tools import tool
from services.db_service import execute_query
from datetime import date
from typing import Optional

CATEGORY_WINDOWS = {
    "digital":      0,
    "food":         3,
    "electronics":  15,
    "clothing":     30,
    "standard":     30,
    "bundle":       30,
    "personalized": 0,
}

MIN_AMOUNT   = 800.00
MGR_LIMIT    = 40000.00
EXEC_LIMIT   = 80000.00


@tool
def check_refund_policy(
    customer_id: str,
    order_id: str,
    refund_reason: str,
    days_since_delivery: Optional[int] = None,
) -> dict:
    """
    Check ShopEase refund policy and return eligibility decision.

    Args:
        customer_id: e.g. 'C007'
        order_id:    e.g. 'ORD-1007'
        refund_reason: what the customer said
        days_since_delivery: auto-calculated if not passed

    Returns dict with:
        eligible, refund_type, refund_amount (exact INR float),
        recommendation (APPROVE/PARTIAL/DENY/ESCALATE),
        denial_reason (string), product_name, order_amount
    """
    # ── Fetch customer ─────────────────────────────────────────────────────
    rows = execute_query("SELECT * FROM customers WHERE customer_id = ?", [customer_id])
    if not rows:
        return _deny(f"Customer ID '{customer_id}' not found.")
    c = rows[0]

    # ── Fetch order ────────────────────────────────────────────────────────
    rows = execute_query("SELECT * FROM orders WHERE order_id = ?", [order_id])
    if not rows:
        return _deny(f"Order ID '{order_id}' not found.")
    o = rows[0]

    amount   = float(o["amount"])
    category = str(o["category"]).lower().strip()
    reason   = refund_reason.lower().strip()

    # ── 1. Banned account ──────────────────────────────────────────────────
    if c["account_status"] == "banned":
        return _deny("This account is permanently suspended. Refund requests cannot be processed.")

    # ── 2. Flagged / repeat fraud → escalate ──────────────────────────────
    requires_approval = None
    if c["account_status"] == "flagged" or int(c.get("refund_count_90d", 0)) >= 3:
        requires_approval = "manager"

    # ── 3. Digital = non-refundable ───────────────────────────────────────
    if category == "digital":
        return _deny("Digital products and software licences are non-refundable once activated.")

    # ── 4. Personalised — only refundable if damaged/defective ────────────
    damage_words = ["damaged", "defective", "broken", "wrong item", "incorrect"]
    if category == "personalized" and not any(w in reason for w in damage_words):
        return _deny(
            "Personalised/custom-made items are non-refundable unless they arrive "
            "damaged or defective."
        )

    # ── 5. Minimum amount ─────────────────────────────────────────────────
    if amount < MIN_AMOUNT:
        return _deny(
            f"Orders under ₹{MIN_AMOUNT:,.0f} are not eligible for a refund. "
            f"Order value: ₹{amount:,.2f}."
        )

    # ── 6. Calculate days since delivery ──────────────────────────────────
    if days_since_delivery is None:
        raw = o.get("delivery_date")
        if raw:
            try:
                days_since_delivery = (date.today() - date.fromisoformat(str(raw))).days
            except Exception:
                days_since_delivery = None

    # ── 7. VIP / Premium window extension ─────────────────────────────────
    base_window = CATEGORY_WINDOWS.get(category, 30)
    bonus       = 15 if c["membership_tier"] in ("vip", "premium") else 0
    eff_window  = base_window + bonus

    # ── 8. Eligibility window check ────────────────────────────────────────
    if days_since_delivery is not None and days_since_delivery > eff_window:
        vip_note = f" (+{bonus} VIP days = {eff_window} total)" if bonus else ""
        return _deny(
            f"The refund window has expired. Your item was delivered {days_since_delivery} "
            f"days ago. The {category} policy window is {base_window} days{vip_note}."
        )

    # ── 9. Non-delivery with signed confirmation = deny ────────────────────
    no_delivery = ["never arrived", "not delivered", "didn't receive", "not received"]
    if any(w in reason for w in no_delivery) and o.get("delivery_signed"):
        return _deny(
            "Delivery was confirmed with a recipient signature. "
            "Non-delivery claims cannot be approved when delivery is confirmed."
        )

    # ── 10. Customer-caused damage ─────────────────────────────────────────
    cust_fault = ["i dropped", "i broke", "i spilled", "my fault", "used it", "already used"]
    if any(w in reason for w in cust_fault):
        return _deny("Damage caused by the customer is not covered under our refund policy.")

    # ── 11. Food category — strict reason rules ───────────────────────────
    if category == "food":
        food_ok = [
            "damaged", "defective", "spoiled", "rotten", "expired", "wrong item",
            "incorrect item", "not fresh", "mouldy", "contaminated", "bad quality",
            "foreign object", "quality issue",
        ]
        if not any(w in reason for w in food_ok):
            return _deny(
                "For food/perishable items, refunds are only approved for damaged, spoiled, "
                "expired, or incorrect items. Change of mind is not accepted for food."
            )
        if days_since_delivery is not None and days_since_delivery > 3:
            return _deny(
                f"Food quality issues must be reported within 3 days of delivery. "
                f"Your item was delivered {days_since_delivery} days ago."
            )
        refund_type   = "full"
        refund_amount = amount

    # ── 12. All other categories ──────────────────────────────────────────
    else:
        full_words = [
            "damaged", "defective", "broken", "wrong item", "incorrect item",
            "never arrived", "not delivered", "not as described", "wrong product",
            "description mismatch",
        ]
        partial_words = [
            "changed mind", "changed my mind", "don't want", "no longer need",
            "size", "doesn't fit", "too big", "too small", "fit issue",
        ]

        if any(w in reason for w in full_words):
            refund_type = "full"
            is_damage = any(w in reason for w in ["damaged", "defective", "broken"])
            if is_damage and days_since_delivery is not None and days_since_delivery > 3:
                return _deny(
                    f"Damaged or defective items must be reported within 72 hours of delivery. "
                    f"Your item was delivered {days_since_delivery} days ago."
                )
        elif any(w in reason for w in partial_words):
            # Size/fit only for clothing
            is_size = any(w in reason for w in ["size", "fit", "too big", "too small"])
            if is_size and category not in ("clothing",):
                return _deny(
                    f"Size/fit refunds only apply to clothing. "
                    f"This order is '{category}' category."
                )
            refund_type = "partial_50"
        else:
            # Vague reason → partial (changed mind equivalent)
            refund_type = "partial_50"

        refund_amount = amount if refund_type == "full" else round(amount * 0.50, 2)

    # ── 13. High-value approval gates ─────────────────────────────────────
    if refund_amount > EXEC_LIMIT:
        requires_approval = "executive"
    elif refund_amount > MGR_LIMIT and requires_approval != "executive":
        requires_approval = "manager"

    # ── 14. Build result ───────────────────────────────────────────────────
    if requires_approval:
        recommendation = "ESCALATE"
    elif refund_type == "partial_50":
        recommendation = "PARTIAL"
    else:
        recommendation = "APPROVE"

    return {
        "eligible":            True,
        "refund_type":         refund_type,
        "refund_amount":       float(refund_amount),   # EXACT amount — Python uses this directly
        "requires_approval":   requires_approval,
        "denial_reason":       None,
        "recommendation":      recommendation,
        "days_since_delivery": days_since_delivery,
        "effective_window":    eff_window,
        "category":            category,
        "order_amount":        float(amount),
        "product_name":        str(o.get("product_name", "")),
        "customer_name":       str(c.get("full_name", "")),
    }


def _deny(reason: str) -> dict:
    return {
        "eligible":          False,
        "refund_type":       "denied",
        "refund_amount":     0.0,
        "requires_approval": None,
        "denial_reason":     reason,
        "recommendation":    "DENY",
    }



# from langchain_core.tools import tool
# from services.db_service import execute_query
# from datetime import date
# from typing import Optional

# # ── Category refund windows (days) ────────────────────────────────────────────
# CATEGORY_WINDOWS = {
#     "digital":     0,
#     "food":        3,
#     "electronics": 15,
#     "clothing":    30,
#     "standard":    30,
#     "bundle":      30,
# }

# MIN_REFUND_AMOUNT   = 10.00
# MANAGER_THRESHOLD   = 500.00
# EXECUTIVE_THRESHOLD = 1000.00


# @tool
# def check_refund_policy(
#     customer_id: str,
#     order_id: str,
#     refund_reason: str,
#     days_since_delivery: Optional[int] = None,
# ) -> dict:
#     """
#     Apply ShopEase refund policy rules and return an eligibility decision.

#     Args:
#         customer_id: Customer ID (e.g. 'C001')
#         order_id: Order ID (e.g. 'ORD-1011')
#         refund_reason: What the customer said (e.g. 'item arrived damaged')
#         days_since_delivery: Optional override; calculated from DB if not given

#     Returns:
#         dict with: eligible, refund_type, refund_amount, requires_approval,
#                    denial_reasons, policy_rules_checked, recommendation
#     """
#     denial_reasons = []
#     rules_checked = []
#     requires_approval = None

#     # ── 1. Fetch customer ──────────────────────────────────────────────────
#     customer_rows = execute_query(
#         "SELECT * FROM customers WHERE customer_id = ?", [customer_id]
#     )
#     if not customer_rows:
#         return _deny([f"Customer ID '{customer_id}' not found."], [])
#     customer = customer_rows[0]

#     # ── 2. Fetch order ─────────────────────────────────────────────────────
#     order_rows = execute_query(
#         "SELECT * FROM orders WHERE order_id = ?", [order_id]
#     )
#     if not order_rows:
#         return _deny([f"Order ID '{order_id}' not found."], [])
#     order = order_rows[0]
#     amount = float(order["amount"])
#     category = str(order["category"]).lower().strip()

#     # ── 3. Banned account ─────────────────────────────────────────────────
#     rules_checked.append("account_status")
#     if customer["account_status"] == "banned":
#         return _deny(
#             ["Your account has been permanently suspended. All refund requests are denied."],
#             rules_checked
#         )

#     # ── 4. Flagged account → escalate ─────────────────────────────────────
#     if customer["account_status"] == "flagged":
#         requires_approval = "manager"
#         rules_checked.append("flagged_account_escalate")

#     # ── 5. Repeat claim fraud ──────────────────────────────────────────────
#     rules_checked.append("fraud_check")
#     refund_count = int(customer.get("refund_count_90d", 0))
#     if refund_count >= 3 and customer["account_status"] != "flagged":
#         requires_approval = "manager"
#         rules_checked.append("repeat_claim_escalate")

#     # ── 6. Digital = non-refundable ────────────────────────────────────────
#     rules_checked.append("digital_check")
#     if category == "digital":
#         return _deny(
#             ["Digital products and software licenses are non-refundable once activated."],
#             rules_checked
#         )

#     # ── 7. Minimum amount ─────────────────────────────────────────────────
#     rules_checked.append("minimum_amount")
#     if amount < MIN_REFUND_AMOUNT:
#         return _deny(
#             [f"Orders under ${MIN_REFUND_AMOUNT:.2f} are non-refundable. Order value: ${amount:.2f}."],
#             rules_checked
#         )

#     # ── 8. Calculate days since delivery ──────────────────────────────────
#     rules_checked.append("window_check")
#     if days_since_delivery is None and order.get("delivery_date"):
#         delivery_str = order["delivery_date"]
#         if hasattr(delivery_str, "isoformat"):
#             delivery_str = delivery_str.isoformat()
#         try:
#             days_since_delivery = (date.today() - date.fromisoformat(str(delivery_str))).days
#         except Exception:
#             days_since_delivery = None

#     # ── 9. VIP/Premium window extension ───────────────────────────────────
#     base_window = CATEGORY_WINDOWS.get(category, 30)
#     bonus_days = 15 if customer["membership_tier"] in ("vip", "premium") else 0
#     effective_window = base_window + bonus_days
#     if bonus_days:
#         rules_checked.append("vip_window_extended")

#     # ── 10. Eligibility window expired ────────────────────────────────────
#     if days_since_delivery is not None and days_since_delivery > effective_window:
#         window_msg = f"Policy window for {category} is {base_window} days"
#         if bonus_days:
#             window_msg += f" (+{bonus_days} VIP days = {effective_window} total)"
#         return _deny(
#             [f"Refund window has expired. Delivered {days_since_delivery} days ago. {window_msg}."],
#             rules_checked
#         )

#     # ── 11. Non-delivery contradiction ────────────────────────────────────
#     rules_checked.append("delivery_check")
#     reason_lower = refund_reason.lower()
#     nondelivery = any(kw in reason_lower for kw in
#                       ["never arrived", "not delivered", "didn't receive", "not received"])
#     if nondelivery and order.get("delivery_signed"):
#         return _deny(
#             ["Delivery confirmed with signature. Non-delivery claim cannot be approved."],
#             rules_checked
#         )

#     # ── 12. Customer-caused damage → deny ─────────────────────────────────
#     rules_checked.append("customer_damage_check")
#     customer_fault = any(kw in reason_lower for kw in
#                          ["i dropped", "i spilled", "i broke", "my fault",
#                           "already used", "used it", "used and"])
#     if customer_fault:
#         return _deny(
#             ["Damage caused by the customer is not covered under our refund policy."],
#             rules_checked
#         )

#     # ── 13. FOOD category — special rules ─────────────────────────────────
#     # Food: only accepts damage/quality/wrong item. No "changed mind" refunds.
#     if category == "food":
#         rules_checked.append("food_category_rules")
#         food_full_keywords = [
#             "damaged", "defective", "spoiled", "rotten", "expired",
#             "bad quality", "wrong item", "incorrect item", "not fresh",
#             "mouldy", "mold", "foreign object", "contaminated",
#         ]
#         if not any(kw in reason_lower for kw in food_full_keywords):
#             return _deny(
#                 [
#                     "For food/perishable items, refunds are only approved for "
#                     "damaged, spoiled, expired, or incorrect items. "
#                     "Change of mind is not an accepted reason for food category."
#                 ],
#                 rules_checked
#             )
#         # Food + valid reason: must also be within 3 days (already checked above)
#         # Check 72-hour rule for defect/spoilage
#         if days_since_delivery is not None and days_since_delivery > 3:
#             return _deny(
#                 [f"Food quality issues must be reported within 3 days of delivery. "
#                  f"Delivered {days_since_delivery} days ago."],
#                 rules_checked
#             )
#         rules_checked.append("food_full_refund_approved")
#         refund_type = "full"
#         refund_amount = amount

#     # ── 14. Standard reason classification ────────────────────────────────
#     else:
#         full_keywords = [
#             "damaged", "defective", "broken", "wrong item", "incorrect item",
#             "never arrived", "not delivered", "not as described",
#             "description mismatch", "wrong product", "different from",
#         ]
#         partial_keywords = [
#             "changed mind", "don't want", "no longer need",
#             "don't need", "size", "doesn't fit", "too big", "too small",
#             "fit issue", "buyer's remorse", "changed my mind",
#         ]

#         if any(kw in reason_lower for kw in full_keywords):
#             rules_checked.append("full_refund_reason")
#             refund_type = "full"

#             # Defective/damaged items: must report within 72 hours
#             is_damage = any(kw in reason_lower for kw in
#                             ["damaged", "defective", "broken"])
#             if is_damage and days_since_delivery is not None and days_since_delivery > 3:
#                 return _deny(
#                     [f"Damage or defects must be reported within 72 hours of delivery. "
#                      f"Delivered {days_since_delivery} days ago."],
#                     rules_checked
#                 )

#         elif any(kw in reason_lower for kw in partial_keywords):
#             rules_checked.append("partial_refund_reason")
#             # Size issues only for clothing
#             is_size = any(kw in reason_lower for kw in ["size", "fit", "too big", "too small"])
#             if is_size and category not in ("clothing",):
#                 return _deny(
#                     [f"Size/fit refunds only apply to clothing. This order is '{category}'."],
#                     rules_checked
#                 )
#             refund_type = "partial_50"

#         else:
#             # Vague reason — default to partial (changed mind equivalent)
#             rules_checked.append("vague_reason_partial")
#             refund_type = "partial_50"

#         # Calculate amount
#         refund_amount = amount if refund_type == "full" else round(amount * 0.50, 2)

#     # ── 15. High value approval gates ─────────────────────────────────────
#     rules_checked.append("high_value_check")
#     if refund_amount > EXECUTIVE_THRESHOLD:
#         requires_approval = "executive"
#     elif refund_amount > MANAGER_THRESHOLD and requires_approval != "executive":
#         requires_approval = "manager"

#     # ── 16. Final result ──────────────────────────────────────────────────
#     recommendation = (
#         "ESCALATE" if requires_approval else
#         "PARTIAL"  if refund_type == "partial_50" else
#         "APPROVE"
#     )

#     return {
#         "eligible": True,
#         "refund_type": refund_type,
#         "refund_amount": float(refund_amount),
#         "requires_approval": requires_approval,
#         "denial_reasons": [],
#         "policy_rules_checked": rules_checked,
#         "recommendation": recommendation,
#         "days_since_delivery": days_since_delivery,
#         "effective_window_days": effective_window,
#         "category": category,
#         "order_amount": float(amount),
#     }


# def _deny(denial_reasons: list, rules_checked: list) -> dict:
#     """Helper: build a clean denial result."""
#     return {
#         "eligible": False,
#         "refund_type": "denied",
#         "refund_amount": 0.0,
#         "requires_approval": None,
#         "denial_reasons": denial_reasons,
#         "policy_rules_checked": rules_checked,
#         "recommendation": "DENY",
#     }