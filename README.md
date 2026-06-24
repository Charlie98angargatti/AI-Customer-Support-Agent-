# AI Customer Support Agent

## Overview

AI Customer Support Agent is an intelligent refund-processing system designed for e-commerce platforms. The application uses LangGraph, Large Language Models (LLMs), and a CRM database to automate customer support interactions while enforcing strict refund policies.

The system can:

* Verify customers and orders
* Validate refund eligibility using business rules
* Approve, deny, or escalate refund requests
* Maintain complete reasoning logs
* Provide an Admin Dashboard for monitoring customer activity and refund decisions

---

## Features

### Customer Chat Interface

Customers can:

* Request refunds
* Submit refund reasons
* Receive approval or denial decisions

### CRM Database

Contains:

* 15 Mock Customer Profiles
* Customer Membership Tiers
* Refund History

### Refund Policy Engine

Supports:

* Refund Window Validation
* Digital Product Restrictions
* Food Item Restrictions
* Personalized Product Rules
* VIP Customer Extensions

### Admin Dashboard

Administrators can monitor:

* Customer Accounts
* Refund Activity
* Flagged Customers
* Banned Customers
* Reasoning Logs
* Agent Sessions

### Reasoning Logs

Every refund request is tracked through:

1. Customer Lookup
2. Order Lookup
3. Refund Policy Validation
4. Refund Processing
5. Final Decision

---

## Architecture

Customer
↓
Chat UI
↓
LangGraph Agent
↓
Customer Lookup Tool
↓
Order Lookup Tool
↓
Refund Policy Tool
↓
Refund Processing Tool
↓
Final Response

Admin Dashboard
↓
Customer Management
↓
Refund Monitoring
↓
Reasoning Logs

---

## Technology Stack

### Backend

* Python
* LangGraph
* LangChain
* Ollama
* Mistral

### Database

* DuckDB

### Frontend

* HTML
* CSS
* JavaScript

### AI Components

* Tool Calling
* Policy Validation
* State Management
* Agent Workflow Orchestration

---

## Project Structure

backend/
├── agent/
├── tools/
├── services/
├── Models/
├── data/
├── app.py

frontend/
├── customer/
├── admin/

---

## Refund Workflow

### Step 1

Customer provides:

* Order ID

Example:

"I want a refund for order ORD-1004"

### Step 2

Agent retrieves:

* Customer Information
* Product Details
* Order Amount

### Step 3

Agent asks for refund reason.

Examples:

* Wrong Item
* Defective Product
* Damaged Item
* Size Issue
* Changed Mind

### Step 4

Refund Policy Engine evaluates:

* Refund Window
* Product Category
* Customer Status
* Fraud Rules

### Step 5

Agent returns:

* Approved
* Denied
* Escalated

---

## Sample Scenarios

### Approved Refund

Order ID: ORD-1004

Product: Cotton T-Shirt

Reason: Size Issue

Result:

Refund Approved

Refund Amount: ₹1049.50

Timeline:

3–5 Business Days

---

### Denied Refund

Order ID: ORD-1007

Product: Winter Jacket

Reason: Wrong Item

Result:

Refund Denied

Reason:

Refund window expired.

Order delivered 42 days ago.

Allowed refund period: 30 days.

---

## Running the Project

### Install Dependencies

pip install -r backend/requirements.txt

### Start Backend

python backend/app.py

### Open Customer UI

frontend/customer/index.html

### Open Admin Dashboard

frontend/admin/index.html

---

## Future Improvements

* Voice Support Integration
* Multi-Language Support
* Real-Time Notifications
* Advanced Fraud Detection
* Human Agent Escalation
* Production Database Integration

---

## Author

Karthik

AI Engineer Assignment Submission

Built using LangGraph, Ollama, Mistral, DuckDB, and Python.
