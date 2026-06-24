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


