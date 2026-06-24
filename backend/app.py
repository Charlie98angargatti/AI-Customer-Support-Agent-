"""
app.py  (REWRITTEN)
===================
FastAPI backend with PROPER security separation:

PUBLIC ROUTES  (no auth needed — customer-facing):
  POST /api/chat
  POST /api/session/new
  GET  /health

ADMIN ROUTES  (require X-Admin-Token header):
  GET  /admin/logs/{session_id}
  GET  /admin/sessions
  GET  /admin/customers
  GET  /admin/orders/{customer_id}
  GET  /admin/refunds

Serving:
  GET  /          → frontend/customer/index.html  (customer UI)
  GET  /admin     → frontend/admin/index.html     (admin UI — separate page)

WHY SEPARATE ROUTES:
  - Customer chat endpoint (/api/chat) is PUBLIC — no token needed
  - All reasoning logs, CRM data, refund records are ADMIN-ONLY
  - The customer browser NEVER receives a token → can never call /admin/*
  - Even if a customer knows the URL, they get 401 Unauthorized

ADMIN TOKEN:
  Set ADMIN_SECRET_TOKEN in .env (any strong random string).
  The admin frontend sends this as: X-Admin-Token: <token>
  In production: replace with proper JWT / OAuth2.
"""

"""
app.py — updated to use new graph.py custom agent loop
=======================================================
Only change from previous version:
  - build_graph() now just loads the LLM (no LangGraph StateGraph needed)
  - run_agent() uses the custom JSON tool-calling loop
  - All other endpoints unchanged
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from contextlib import asynccontextmanager
import uuid, os, logging

# NEW: import from the rewritten graph.py
from agent.graph import build_graph, run_agent
from services.log_service import get_logs, clear_logs, get_all_sessions, log_step
from services.db_service import execute_query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ── Admin token auth ───────────────────────────────────────────────────────────
ADMIN_TOKEN    = os.getenv("ADMIN_SECRET_TOKEN", "shopease-admin-dev-token-2025")
admin_key_hdr  = APIKeyHeader(name="X-Admin-Token", auto_error=False)

async def require_admin(token: str = Depends(admin_key_hdr)):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized.")
    return token

# ── Agent readiness ────────────────────────────────────────────────────────────
agent_ready = False
agent_error = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_ready, agent_error
    logger.info("Starting ShopEase AI Support Agent...")
    try:
        build_graph()
        agent_ready = True
        logger.info("Agent ready.")
    except Exception as e:
        agent_error = str(e)
        logger.error(f"Agent failed to start: {e}")
    yield

app = FastAPI(title="ShopEase AI Support", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request/Response models ────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    session_id: str
    response: str

class NewSessionResponse(BaseModel):
    session_id: str
    welcome: str

# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES — customer facing
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "status": "healthy" if agent_ready else "starting",
        "agent_ready": agent_ready,
        "agent_error": agent_error,
    }

@app.post("/api/session/new", response_model=NewSessionResponse)
async def new_session():
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    clear_logs(session_id)
    log_step(session_id, "session_start",
             reasoning="New session created.", status="success")
    return NewSessionResponse(
        session_id=session_id,
        welcome="Welcome to ShopEase support! How can I help you today?"
    )

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not agent_ready:
        msg = agent_error or "Agent is still loading. Please wait and try again."
        raise HTTPException(status_code=503, detail=msg)

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    log_step(request.session_id, "user_message_received",
             input_summary=request.message[:150],
             reasoning=f"Customer: {request.message[:100]}",
             status="running")
    try:
        response_text = run_agent(request.session_id, request.message)
        return ChatResponse(session_id=request.session_id, response=response_text)
    except Exception as e:
        logger.exception(f"Agent error session={request.session_id}: {e}")
        log_step(request.session_id, "agent_error", reasoning=str(e), status="error")
        raise HTTPException(status_code=500, detail=str(e))

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES — require X-Admin-Token header
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/logs/{session_id}", dependencies=[Depends(require_admin)])
async def admin_logs(session_id: str, since: int = 0):
    logs = get_logs(session_id, since_index=since)
    return {"session_id": session_id, "logs": logs, "total": since + len(logs)}

@app.get("/admin/sessions", dependencies=[Depends(require_admin)])
async def admin_sessions():
    return {"sessions": get_all_sessions()}

@app.get("/admin/customers", dependencies=[Depends(require_admin)])
async def admin_customers():
    rows = execute_query(
        "SELECT customer_id, full_name, email, membership_tier, "
        "account_status, refund_count_90d FROM customers ORDER BY customer_id"
    )
    return {"customers": rows}

@app.get("/admin/orders/{customer_id}", dependencies=[Depends(require_admin)])
async def admin_orders(customer_id: str):
    rows = execute_query("""
        SELECT order_id, product_name, category,
               CAST(amount AS DOUBLE) AS amount,
               CAST(order_date AS VARCHAR) AS order_date,
               CAST(delivery_date AS VARCHAR) AS delivery_date, status
        FROM orders WHERE customer_id = ? ORDER BY order_date DESC
    """, [customer_id])
    return {"orders": rows}

@app.get("/admin/refunds", dependencies=[Depends(require_admin)])
async def admin_refunds():
    rows = execute_query("""
        SELECT r.refund_id, r.order_id, c.full_name AS customer_name,
               o.product_name, CAST(r.amount AS DOUBLE) AS amount,
               r.reason, r.status,
               CAST(r.requested_at AS VARCHAR) AS requested_at,
               r.agent_notes
        FROM refunds r
        JOIN customers c ON r.customer_id = c.customer_id
        JOIN orders    o ON r.order_id    = o.order_id
        ORDER BY r.requested_at DESC LIMIT 50
    """)
    return {"refunds": rows}

# ── Serve frontends ────────────────────────────────────────────────────────────
BASE = os.path.dirname(__file__)

CUSTOMER_DIR = os.path.join(BASE, "..", "frontend", "customer")
ADMIN_DIR    = os.path.join(BASE, "..", "frontend", "admin")

if os.path.exists(CUSTOMER_DIR):
    app.mount("/static/customer", StaticFiles(directory=CUSTOMER_DIR), name="customer")
if os.path.exists(ADMIN_DIR):
    app.mount("/static/admin",    StaticFiles(directory=ADMIN_DIR),    name="admin_static")

@app.get("/")
async def serve_customer():
    f = os.path.join(CUSTOMER_DIR, "index.html")
    return FileResponse(f) if os.path.exists(f) else JSONResponse({"msg": "frontend not found"})

@app.get("/admin-panel")
async def serve_admin():
    f = os.path.join(ADMIN_DIR, "index.html")
    return FileResponse(f) if os.path.exists(f) else JSONResponse({"msg": "admin not found"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True, log_level="info")


# from fastapi import FastAPI, HTTPException, Depends, Request
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from fastapi.responses import FileResponse, JSONResponse
# from fastapi.security import APIKeyHeader
# from pydantic import BaseModel
# from contextlib import asynccontextmanager
# import uuid, os, logging

# from agent.graph import build_graph, run_agent
# from services.log_service import get_logs, clear_logs, get_all_sessions, log_step
# from services.db_service import execute_query

# # ─── Logging ──────────────────────────────────────────────────────────────────
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
# )
# logger = logging.getLogger(__name__)

# # ─── Admin Token Auth ──────────────────────────────────────────────────────────
# ADMIN_TOKEN = os.getenv("ADMIN_SECRET_TOKEN", "shopease-admin-dev-token-2025")
# admin_key_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)

# async def require_admin(token: str = Depends(admin_key_header)):
#     """
#     FastAPI dependency — injected into every /admin/* route.
#     Returns 401 if token is missing or wrong.
#     The customer frontend never has this token, so it can never
#     access admin routes even if it knows the URL.
#     """
#     if token != ADMIN_TOKEN:
#         raise HTTPException(
#             status_code=401,
#             detail="Unauthorized. Valid X-Admin-Token header required.",
#             headers={"WWW-Authenticate": "ApiKey"},
#         )
#     return token

# # ─── Agent readiness flag ──────────────────────────────────────────────────────
# agent_ready = False
# agent_error = None

# # ─── Startup ──────────────────────────────────────────────────────────────────
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global agent_ready, agent_error
#     logger.info("Starting ShopEase AI Support Agent...")
#     try:
#         build_graph()
#         agent_ready = True
#         logger.info("LangGraph agent compiled and ready")
#     except Exception as e:
#         agent_error = str(e)
#         logger.error(f"Failed to build graph: {e}")
#     yield
#     logger.info("Shutting down...")

# # ─── App ──────────────────────────────────────────────────────────────────────
# app = FastAPI(
#     title="ShopEase AI Support API",
#     version="2.0.0",
#     lifespan=lifespan,
#     # Hide admin routes from public OpenAPI docs
#     openapi_url="/api/openapi.json",
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # ─── Models ───────────────────────────────────────────────────────────────────
# class ChatRequest(BaseModel):
#     session_id: str
#     message: str

# class ChatResponse(BaseModel):
#     session_id: str
#     response: str

# class NewSessionResponse(BaseModel):
#     session_id: str
#     welcome: str

# # ═══════════════════════════════════════════════════════════════════════════════
# # PUBLIC ROUTES — No authentication required
# # These are the ONLY routes the customer frontend uses
# # ═══════════════════════════════════════════════════════════════════════════════

# @app.get("/health")
# async def health_check():
#     """Public health check."""
#     return {
#         "status": "healthy" if agent_ready else "starting",
#         "agent_ready": agent_ready,
#         "agent_error": agent_error,
#     }

# @app.post("/api/session/new", response_model=NewSessionResponse)
# async def new_session():
#     """
#     PUBLIC: Creates a new customer chat session.
#     Returns only a session_id and welcome message — no sensitive data.
#     """
#     session_id = f"sess-{uuid.uuid4().hex[:12]}"
#     clear_logs(session_id)
#     log_step(session_id, "session_start",
#              reasoning="New customer session initialized.",
#              status="success")
#     return NewSessionResponse(
#         session_id=session_id,
#         welcome="Welcome to ShopEase support! How can I help you today?"
#     )

# @app.post("/api/chat", response_model=ChatResponse)
# async def chat(request: ChatRequest):
#     """
#     PUBLIC: Accepts a customer message and returns the agent's response.
    
#     SECURITY: This endpoint returns ONLY the agent's final text response.
#     The customer NEVER sees:
#       - Internal reasoning logs
#       - Raw tool outputs
#       - Other customers' data
#       - Policy rule evaluation details
    
#     Reasoning logs are written to log_service (server memory) and are
#     ONLY accessible via the protected /admin/logs/{session_id} route.
#     """
#     if not agent_ready:
#         msg = agent_error or "Agent is still loading. Please wait 30–60 seconds and try again."
#         raise HTTPException(status_code=503, detail=msg)

#     if not request.message.strip():
#         raise HTTPException(status_code=400, detail="Message cannot be empty")

#     log_step(
#         request.session_id,
#         step="user_message_received",
#         input_summary=request.message[:200],
#         reasoning=f"Customer sent: '{request.message[:100]}'",
#         status="running"
#     )

#     try:
#         response_text = run_agent(request.session_id, request.message)
#         return ChatResponse(session_id=request.session_id, response=response_text)

#     except ConnectionRefusedError:
#         raise HTTPException(status_code=503, detail="AI service unavailable.")
#     except Exception as e:
#         logger.exception(f"Agent error for session {request.session_id}: {e}")
#         log_step(request.session_id, "agent_error", reasoning=str(e), status="error")
#         raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

# # ═══════════════════════════════════════════════════════════════════════════════
# # ADMIN ROUTES — Require X-Admin-Token header
# # The customer frontend NEVER sends this header → 401 if customer tries to access
# # ═══════════════════════════════════════════════════════════════════════════════

# @app.get("/admin/logs/{session_id}", dependencies=[Depends(require_admin)])
# async def admin_get_logs(session_id: str, since: int = 0):
#     """
#     ADMIN ONLY: Returns reasoning logs for a session.
#     Customer can never access this — no token in customer browser.
#     """
#     logs = get_logs(session_id, since_index=since)
#     return {"session_id": session_id, "logs": logs, "total": since + len(logs)}

# @app.get("/admin/sessions", dependencies=[Depends(require_admin)])
# async def admin_list_sessions():
#     """ADMIN ONLY: All active sessions overview."""
#     return {"sessions": get_all_sessions()}

# @app.get("/admin/customers", dependencies=[Depends(require_admin)])
# async def admin_list_customers():
#     """ADMIN ONLY: Full CRM customer list."""
#     rows = execute_query("""
#         SELECT customer_id, full_name, email, membership_tier,
#                account_status, refund_count_90d
#         FROM customers ORDER BY customer_id
#     """)
#     return {"customers": rows}

# @app.get("/admin/orders/{customer_id}", dependencies=[Depends(require_admin)])
# async def admin_get_orders(customer_id: str):
#     """ADMIN ONLY: Orders for a specific customer."""
#     rows = execute_query("""
#         SELECT order_id, product_name, category,
#                CAST(amount AS DOUBLE) AS amount,
#                CAST(order_date AS VARCHAR) AS order_date,
#                CAST(delivery_date AS VARCHAR) AS delivery_date,
#                status
#         FROM orders WHERE customer_id = ?
#         ORDER BY order_date DESC
#     """, [customer_id])
#     return {"orders": rows}

# @app.get("/admin/refunds", dependencies=[Depends(require_admin)])
# async def admin_get_refunds():
#     """ADMIN ONLY: Recent refund decisions with full details."""
#     rows = execute_query("""
#         SELECT r.refund_id, r.order_id, c.full_name AS customer_name,
#                o.product_name,
#                CAST(r.amount AS DOUBLE) AS amount,
#                r.reason, r.status,
#                CAST(r.requested_at AS VARCHAR) AS requested_at,
#                r.agent_notes
#         FROM refunds r
#         JOIN customers c ON r.customer_id = c.customer_id
#         JOIN orders o ON r.order_id = o.order_id
#         ORDER BY r.requested_at DESC LIMIT 50
#     """)
#     return {"refunds": rows}

# # ─── Serve Frontends ──────────────────────────────────────────────────────────
# BASE = os.path.dirname(__file__)
# CUSTOMER_DIR = os.path.join(BASE, "..", "frontend", "customer")
# ADMIN_DIR    = os.path.join(BASE, "..", "frontend", "admin")

# if os.path.exists(CUSTOMER_DIR):
#     app.mount("/static/customer", StaticFiles(directory=CUSTOMER_DIR), name="customer")

# if os.path.exists(ADMIN_DIR):
#     app.mount("/static/admin", StaticFiles(directory=ADMIN_DIR), name="admin_static")

# @app.get("/")
# async def serve_customer():
#     f = os.path.join(CUSTOMER_DIR, "index.html")
#     return FileResponse(f) if os.path.exists(f) else JSONResponse({"msg": "Customer frontend not found"})

# @app.get("/admin-panel")
# async def serve_admin():
#     """
#     Serves the admin panel HTML.
#     NOTE: The HTML itself is public — security comes from the API token,
#     not from hiding the URL. Anyone who opens /admin-panel sees a login form.
#     Data is only loaded after they provide the correct token.
#     """
#     f = os.path.join(ADMIN_DIR, "index.html")
#     return FileResponse(f) if os.path.exists(f) else JSONResponse({"msg": "Admin frontend not found"})

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("app:app", host="0.0.0.0", port=8000, log_level="info")



# """
# app.py
# ======
# FastAPI backend server — the HTTP interface between the frontend and the agent.

# ENDPOINTS:
#   POST /api/chat          → Send a message to the agent, get a response
#   GET  /api/logs/{sid}    → Poll agent reasoning logs for the admin panel
#   GET  /api/sessions      → List active sessions (admin overview)
#   POST /api/session/new   → Create a new chat session
#   GET  /api/customers     → List all customers (admin view)
#   GET  /api/orders/{cid}  → Get orders for a customer
#   GET  /api/refunds       → Recent refunds (admin dashboard)
#   GET  /health            → Health check

# CORS:
#   Enabled for all origins in development. In production, restrict to your domain.

# STARTUP:
#   On startup, the graph is pre-built (warms up the LLM connection)
#   and the database is verified to exist.

# How it connects:
#   Frontend (app.js) → HTTP requests → app.py → agent/graph.py → tools → DB
#   Frontend admin panel → GET /api/logs/{session_id} (polling every 2s)
# """

# from fastapi import FastAPI, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from fastapi.responses import FileResponse
# from pydantic import BaseModel
# from contextlib import asynccontextmanager
# import uuid
# import os
# import logging

# from agent.graph import build_graph, run_agent
# from services.log_service import get_logs, clear_logs, get_all_sessions, log_step
# from services.db_service import execute_query

# print("App started loading...")
# # ─── Logging ──────────────────────────────────────────────────────────────────
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
# )
# logger = logging.getLogger(__name__)



# # ─── Startup / Shutdown ────────────────────────────────────────────────────────
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """
#     Runs on startup: pre-build the graph (warms up LLM connection).
#     This prevents the first user from experiencing a cold-start delay.
#     """
#     logger.info("🚀 Starting ShopEase AI Support Agent...")
#     try:
#         build_graph()
#         logger.info("✅ LangGraph agent compiled and ready")
#     except Exception as e:
#         logger.error(f"❌ Failed to build graph: {e}")
#         logger.error("Make sure Ollama is running: `ollama serve`")
#     yield
#     logger.info("🛑 Shutting down...")


# # ─── App initialization ────────────────────────────────────────────────────────
# app = FastAPI(
#     title="ShopEase AI Customer Support Agent",
#     description="AI-powered refund processing agent with policy enforcement",
#     version="1.0.0",
#     lifespan=lifespan,
# )

# # ── CORS — allow frontend to call the API ─────────────────────────────────────
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],          # In production: ["https://yourdomain.com"]
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# # ─── Request/Response Models ───────────────────────────────────────────────────
# class ChatRequest(BaseModel):
#     """Incoming message from the customer chat UI."""
#     session_id: str
#     message: str


# class ChatResponse(BaseModel):
#     """Response from the agent."""
#     session_id: str
#     response: str
#     log_count: int  # Frontend uses this to know how many logs to fetch


# class NewSessionResponse(BaseModel):
#     session_id: str
#     message: str


# # ─── ENDPOINTS ────────────────────────────────────────────────────────────────

# @app.get("/health")
# async def health_check():
#     """Simple health check — used by monitoring and Docker healthchecks."""
#     return {"status": "healthy", "service": "ShopEase AI Support Agent"}


# @app.post("/api/session/new", response_model=NewSessionResponse)
# async def new_session():
#     """
#     Creates a new chat session with a unique session_id.
#     The frontend calls this when the user clicks "New Conversation".
#     """
#     session_id = f"sess-{uuid.uuid4().hex[:12]}"
#     clear_logs(session_id)
#     log_step(
#         session_id,
#         step="session_start",
#         reasoning="New customer session initialized. Waiting for customer input.",
#         status="success"
#     )
#     return NewSessionResponse(
#         session_id=session_id,
#         message="Welcome to ShopEase support! How can I help you today?"
#     )


# @app.post("/api/chat", response_model=ChatResponse)
# async def chat(request: ChatRequest):
#     """
#     Main chat endpoint. Receives a customer message and returns the agent's response.

#     Flow:
#       1. Receive message + session_id
#       2. Log the incoming message
#       3. Run the agent (which may call multiple tools internally)
#       4. Return the agent's text response
#       5. Include log_count so the frontend knows logs are ready to fetch

#     Error handling:
#       - LLM connection errors (Ollama not running)
#       - Database errors (DB not seeded)
#       - Agent errors (tool failures)
#     """
#     if not request.message.strip():
#         raise HTTPException(status_code=400, detail="Message cannot be empty")

#     session_id = request.session_id

#     # Log the user's input for the admin panel
#     log_step(
#         session_id,
#         step="user_message_received",
#         input_summary=request.message[:200],
#         reasoning=f"Customer sent: '{request.message[:100]}...' — beginning agent processing.",
#         status="running"
#     )

#     try:
#         # ── Run the agent ────────────────────────────────────────────────
#         response_text = run_agent(session_id, request.message)

#         # ── Count logs for this session ───────────────────────────────
#         log_count = len(get_logs(session_id))

#         return ChatResponse(
#             session_id=session_id,
#             response=response_text,
#             log_count=log_count,
#         )

#     except ConnectionRefusedError:
#         logger.error("Ollama connection refused")
#         raise HTTPException(
#             status_code=503,
#             detail="AI service unavailable. Please ensure Ollama is running (`ollama serve`)."
#         )
#     except Exception as e:
#         logger.exception(f"Agent error for session {session_id}: {e}")
#         log_step(session_id, "agent_error", reasoning=str(e), status="error")
#         raise HTTPException(
#             status_code=500,
#             detail=f"Agent processing error: {str(e)}"
#         )


# @app.get("/api/logs/{session_id}")
# async def get_session_logs(session_id: str, since: int = 0):
#     """
#     Returns reasoning logs for a session starting from index `since`.
#     The frontend polls this endpoint every 2 seconds.

#     Args:
#         session_id: The session to fetch logs for
#         since: Return only logs after this index (for incremental updates)
#     """
#     logs = get_logs(session_id, since_index=since)
#     return {
#         "session_id": session_id,
#         "logs": logs,
#         "total": since + len(logs)
#     }


# @app.get("/api/sessions")
# async def list_sessions():
#     """Admin endpoint: lists all active sessions."""
#     return {"sessions": get_all_sessions()}


# @app.get("/api/customers")
# async def list_customers():
#     """Admin endpoint: returns all customer profiles for the dashboard."""
#     rows = execute_query("""
#         SELECT customer_id, full_name, email, membership_tier,
#                account_status, refund_count_90d
#         FROM customers
#         ORDER BY customer_id
#     """)
#     return {"customers": rows}


# @app.get("/api/orders/{customer_id}")
# async def get_orders(customer_id: str):
#     """Returns all orders for a given customer."""
#     rows = execute_query("""
#         SELECT order_id, product_name, category,
#                CAST(amount AS DOUBLE) AS amount,
#                CAST(order_date AS VARCHAR) AS order_date,
#                CAST(delivery_date AS VARCHAR) AS delivery_date,
#                status
#         FROM orders
#         WHERE customer_id = ?
#         ORDER BY order_date DESC
#     """, [customer_id])
#     return {"orders": rows}


# @app.get("/api/refunds")
# async def get_recent_refunds():
#     """Admin dashboard: returns recent refund decisions."""
#     rows = execute_query("""
#         SELECT r.refund_id, r.order_id, c.full_name AS customer_name,
#                o.product_name,
#                CAST(r.amount AS DOUBLE) AS amount,
#                r.reason, r.status,
#                CAST(r.requested_at AS VARCHAR) AS requested_at,
#                r.agent_notes
#         FROM refunds r
#         JOIN customers c ON r.customer_id = c.customer_id
#         JOIN orders o ON r.order_id = o.order_id
#         ORDER BY r.requested_at DESC
#         LIMIT 20
#     """)
#     return {"refunds": rows}


# # ── Serve the frontend (production mode) ──────────────────────────────────────
# # In development, open frontend/index.html directly in the browser.
# # In production, this serves the frontend as static files.
# FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
# if os.path.exists(FRONTEND_DIR):
#     app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

#     @app.get("/")
#     async def serve_frontend():
#         return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# print("Reached end of file")
# # ─── Main entry point ─────────────────────────────────────────────────────────
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(
#         "app:app",
#         host="0.0.0.0",
#         port=8000,
#         reload=True,       # Auto-reload on code changes (dev mode)
#         log_level="info",
#     )