"""
seed_data.py
============
Populates the DuckDB database (crm.duckdb) with:
  - 15 customer profiles (CRM table)
  - 20 orders (various statuses, categories, amounts) — amounts in INR (₹)
  - 5 existing refund records (to simulate repeat-claimers)

All order categories map 1:1 onto the categories enforced in
tools/policy_tool.py and described in refund_policy.txt:
  standard | electronics | clothing | food | digital | bundle | personalized

Run this ONCE before starting the backend:
    python backend/data/seed_data.py
"""

import duckdb
import os
from datetime import datetime, timedelta
import random

# ─── Path to the database file ────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "crm.duckdb")


def seed():
    con = duckdb.connect(DB_PATH)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. CUSTOMERS TABLE
    #    Stores 15 mock customer profiles with membership tier & refund history.
    # ──────────────────────────────────────────────────────────────────────────
    con.execute("DROP TABLE IF EXISTS refunds")
    con.execute("DROP TABLE IF EXISTS orders")
    con.execute("DROP TABLE IF EXISTS customers")

    con.execute("""
        CREATE TABLE customers (
            customer_id     VARCHAR PRIMARY KEY,
            full_name       VARCHAR NOT NULL,
            email           VARCHAR UNIQUE NOT NULL,
            phone           VARCHAR,
            membership_tier VARCHAR DEFAULT 'standard',   -- standard | vip | premium
            account_status  VARCHAR DEFAULT 'active',     -- active | flagged | banned
            refund_count_90d INTEGER DEFAULT 0,           -- refunds in last 90 days
            join_date       DATE,
            address         VARCHAR
        )
    """)

    customers = [
        # (id, name, email, phone, tier, status, refund_count_90d, join_date, address)
        ("C001", "Aditi Sharma",     "aditi.sharma@email.com",   "98100-10101", "standard", "active",  0, "2022-03-15", "12 MG Road, Bengaluru, KA"),
        ("C002", "Rohan Mehta",      "rohan.mehta@email.com",    "98200-10202", "vip",      "active",  1, "2021-07-20", "45 Linking Road, Mumbai, MH"),
        ("C003", "Kavya Reddy",      "kavya.reddy@email.com",    "98300-10303", "premium",  "active",  0, "2020-01-10", "78 Jubilee Hills, Hyderabad, TS"),
        ("C004", "Aarav Patel",      "aarav.patel@email.com",    "98400-10404", "standard", "active",  2, "2023-05-05", "23 SG Highway, Ahmedabad, GJ"),
        ("C005", "Sneha Iyer",       "sneha.iyer@email.com",     "98500-10505", "standard", "flagged", 4, "2022-09-18", "65 Anna Salai, Chennai, TN"),   # repeat claimant
        ("C006", "Vikram Singh",     "vikram.singh@email.com",   "98600-10606", "vip",      "active",  0, "2021-02-28", "98 Civil Lines, Jaipur, RJ"),
        ("C007", "Priya Nair",       "priya.nair@email.com",     "98700-10707", "standard", "active",  1, "2023-11-01", "14 MG Marg, Kochi, KL"),
        ("C008", "Karan Gupta",      "karan.gupta@email.com",    "98800-10808", "standard", "active",  0, "2022-06-14", "25 Sector 17, Chandigarh, CH"),
        ("C009", "Ishaan Verma",     "ishaan.verma@email.com",   "98900-10909", "premium",  "active",  0, "2020-08-22", "36 Park Street, Kolkata, WB"),
        ("C010", "Manoj Kumar",      "manoj.kumar@email.com",    "99000-11010", "standard", "banned",  8, "2021-12-03", "74 Brigade Road, Bengaluru, KA"),  # banned
        ("C011", "Anjali Desai",     "anjali.desai@email.com",   "99100-11111", "vip",      "active",  0, "2022-04-17", "85 FC Road, Pune, MH"),
        ("C012", "Rahul Joshi",      "rahul.joshi@email.com",    "99200-11212", "standard", "active",  3, "2023-02-09", "96 Sector 62, Noida, UP"),
        ("C013", "Meera Pillai",     "meera.pillai@email.com",   "99300-11313", "standard", "active",  0, "2023-07-30", "17 Residency Road, Bengaluru, KA"),
        ("C014", "Arjun Rao",        "arjun.rao@email.com",      "99400-11414", "premium",  "active",  0, "2019-11-25", "28 Banjara Hills, Hyderabad, TS"),
        ("C015", "Divya Menon",      "divya.menon@email.com",    "99500-11515", "standard", "active",  0, "2024-01-15", "39 Koramangala, Bengaluru, KA"),
    ]

    con.executemany("""
        INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, customers)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. ORDERS TABLE
    #    Each order has a category, amount (INR), delivery date, and status.
    #    Categories are exactly: standard | electronics | clothing | food |
    #    digital | bundle | personalized — matching CATEGORY_WINDOWS in
    #    tools/policy_tool.py and the windows defined in refund_policy.txt.
    # ──────────────────────────────────────────────────────────────────────────
    con.execute("""
        CREATE TABLE orders (
            order_id          VARCHAR PRIMARY KEY,
            customer_id       VARCHAR REFERENCES customers(customer_id),
            product_name      VARCHAR NOT NULL,
            category          VARCHAR NOT NULL,   -- electronics | clothing | food | digital | standard | bundle | personalized
            amount            DECIMAL(10,2) NOT NULL,  -- INR
            order_date        DATE NOT NULL,
            delivery_date     DATE,
            status            VARCHAR DEFAULT 'delivered',  -- pending | shipped | delivered | cancelled
            tracking_number   VARCHAR,
            delivery_signed   BOOLEAN DEFAULT FALSE
        )
    """)

    today = datetime.now().date()

    orders = [
        # ── Normal delivered orders within refund window ──
        ("ORD-1001", "C001", "Wireless Headphones",        "electronics",  7499.00, today - timedelta(days=10), today - timedelta(days=7),  "delivered", "TRK100101", False),
        ("ORD-1002", "C002", "Running Shoes",               "clothing",    10799.00, today - timedelta(days=20), today - timedelta(days=17), "delivered", "TRK100201", False),
        ("ORD-1003", "C003", "Smart Watch Ultra",            "electronics", 41499.00, today - timedelta(days=5),  today - timedelta(days=3),  "delivered", "TRK100301", True),
        ("ORD-1004", "C004", "Cotton T-Shirt",               "clothing",    2099.00, today - timedelta(days=12), today - timedelta(days=9),  "delivered", "TRK100401", False),
        ("ORD-1005", "C005", "Bluetooth Speaker",            "electronics", 4999.00, today - timedelta(days=8),  today - timedelta(days=5),  "delivered", "TRK100501", False),

        # ── Orders OUTSIDE refund window ──
        ("ORD-1006", "C006", "Gaming Keyboard",              "electronics", 12499.00, today - timedelta(days=60), today - timedelta(days=57), "delivered", "TRK100601", True),
        ("ORD-1007", "C007", "Winter Jacket",                "clothing",    16599.00, today - timedelta(days=45), today - timedelta(days=42), "delivered", "TRK100701", False),

        # ── Digital product (non-refundable) ──
        ("ORD-1008", "C008", "Adobe CC License 1yr",         "digital",     49999.00, today - timedelta(days=3),  today - timedelta(days=2),  "delivered", "TRK100801", True),

        # ── Very low-value order (under ₹800 threshold) ──
        ("ORD-1009", "C009", "Phone Screen Protector",       "standard",    649.00, today - timedelta(days=6),  today - timedelta(days=4),  "delivered", "TRK100901", False),

        # ── High-value order (needs manager approval > ₹40,000) ──
        ("ORD-1010", "C009", "4K OLED Television",           "electronics", 107999.00, today - timedelta(days=8),  today - timedelta(days=5),  "delivered", "TRK101001", True),

        # ── Food / perishable ──
        ("ORD-1011", "C011", "Organic Grocery Box",          "food",        5399.00, today - timedelta(days=5),  today - timedelta(days=3),  "delivered", "TRK101101", False),
        ("ORD-1012", "C012", "Premium Coffee Sampler",       "food",        3749.00, today - timedelta(days=10), today - timedelta(days=7),  "delivered", "TRK101201", False),

        # ── Bundle order ──
        ("ORD-1013", "C013", "Home Office Bundle",           "bundle",      29099.00, today - timedelta(days=15), today - timedelta(days=12), "delivered", "TRK101301", False),

        # ── Banned customer order ──
        ("ORD-1014", "C010", "Laptop Stand",                 "standard",    4149.00, today - timedelta(days=7),  today - timedelta(days=4),  "delivered", "TRK101401", False),

        # ── Custom / personalized item (own category — non-refundable unless damaged/defective) ──
        ("ORD-1015", "C015", "Custom Engraved Necklace",     "personalized", 7499.00, today - timedelta(days=9),  today - timedelta(days=6),  "delivered", "TRK101501", False),

        # ── Repeat claimant's current order ──
        ("ORD-1016", "C005", "Yoga Mat Premium",             "standard",    4599.00, today - timedelta(days=14), today - timedelta(days=11), "delivered", "TRK101601", False),

        # ── Premium customer within holiday/VIP extension window ──
        ("ORD-1017", "C014", "Noise Cancelling Earbuds",     "electronics", 24999.00, today - timedelta(days=40), today - timedelta(days=37), "delivered", "TRK101701", False),

        # ── Never-arrived order ──
        ("ORD-1018", "C001", "USB-C Hub 7-port",             "standard",    3299.00, today - timedelta(days=18), None,                       "shipped",   "TRK101801", False),

        # ── Standard in-window order ──
        ("ORD-1019", "C002", "Leather Wallet",               "standard",    2899.00, today - timedelta(days=25), today - timedelta(days=22), "delivered", "TRK101901", False),
        ("ORD-1020", "C003", "Desk Lamp LED",                "standard",    4149.00, today - timedelta(days=11), today - timedelta(days=8),  "delivered", "TRK102001", False),

        # ── Personalized item arriving damaged (the one case where it IS refundable) ──
        ("ORD-1021", "C013", "Personalized Photo Frame Set", "personalized", 2599.00, today - timedelta(days=4),  today - timedelta(days=2),  "delivered", "TRK102101", False),
    ]

    con.executemany("""
        INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, orders)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. REFUNDS TABLE
    #    Tracks past refund attempts (approved / denied / pending). Amounts in INR.
    # ──────────────────────────────────────────────────────────────────────────
    con.execute("""
        CREATE TABLE refunds (
            refund_id     VARCHAR PRIMARY KEY,
            order_id      VARCHAR REFERENCES orders(order_id),
            customer_id   VARCHAR REFERENCES customers(customer_id),
            reason        VARCHAR,
            status        VARCHAR DEFAULT 'pending',   -- pending | approved | denied
            amount        DECIMAL(10,2),
            requested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at   TIMESTAMP,
            agent_notes   VARCHAR
        )
    """)

    refunds = [
        ("REF-001", "ORD-1007", "C007", "Changed mind",          "approved", 16599.00, today - timedelta(days=40), today - timedelta(days=38), "Within window, item unused"),
        ("REF-002", "ORD-1006", "C006", "Defective item",        "approved", 12499.00, today - timedelta(days=55), today - timedelta(days=53), "Customer reported defect with photos"),
        ("REF-003", "ORD-1014", "C010", "Wrong item shipped",    "denied",   4149.00,  today - timedelta(days=6),  today - timedelta(days=5),  "Account banned – fraud investigation"),
        ("REF-004", "ORD-1016", "C005", "Defective",             "denied",   4599.00, today - timedelta(days=10), today - timedelta(days=9),  "Flagged account – excessive refund requests"),
        ("REF-005", "ORD-1019", "C002", "Size issue",            "approved", 1449.50,  today - timedelta(days=20), today - timedelta(days=18), "50% partial refund – clothing size mismatch"),
    ]

    con.executemany("""
        INSERT INTO refunds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, refunds)

    con.close()
    print("✅ Database seeded successfully at:", DB_PATH)
    print("   - 15 customers")
    print("   - 21 orders (INR amounts, includes 'personalized' category)")
    print("   - 5 existing refund records")


if __name__ == "__main__":
    seed()