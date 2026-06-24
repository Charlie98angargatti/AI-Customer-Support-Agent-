"""
services/log_service.py
========================
Manages real-time agent reasoning logs for the admin dashboard.

Architecture:
  - Logs are stored in an in-memory list (per conversation session)
  - The frontend polls GET /api/logs/{session_id} to fetch new logs
  - Server-Sent Events (SSE) are used for real-time streaming

Each log entry has:
  - session_id: ties log to a conversation
  - step: the agent node name (e.g., "classify_intent", "lookup_customer")
  - tool_called: which tool was invoked (if any)
  - input_summary: what the node received
  - output_summary: what the node returned
  - reasoning: the LLM's chain-of-thought for this step
  - timestamp: ISO 8601 string
  - status: "running" | "success" | "error"

How it connects:
  agent/nodes.py → calls log_step() after each node execution
  app.py (GET /api/logs/{session_id}) → calls get_logs() → streams to frontend
  frontend/app.js → polls the logs endpoint and renders the reasoning timeline
"""

import time
from datetime import datetime
from typing import Optional
from collections import defaultdict
import threading

# ─── In-memory log store ───────────────────────────────────────────────────────
# dict: { session_id: [log_entry, ...] }
_logs: dict[str, list] = defaultdict(list)
_lock = threading.Lock()

# Maximum logs to keep per session (prevents memory bloat in long sessions)
MAX_LOGS_PER_SESSION = 100


def log_step(
    session_id: str,
    step: str,
    tool_called: Optional[str] = None,
    input_summary: Optional[str] = None,
    output_summary: Optional[str] = None,
    reasoning: Optional[str] = None,
    status: str = "success",
) -> dict:
    """
    Records a single agent reasoning step.

    Called by every node in the LangGraph agent after it completes work.
    This creates the "reasoning trace" visible in the admin dashboard.
    """
    entry = {
        "id": f"{session_id}-{int(time.time() * 1000)}",
        "session_id": session_id,
        "step": step,
        "tool_called": tool_called,
        "input_summary": input_summary or "",
        "output_summary": output_summary or "",
        "reasoning": reasoning or "",
        "status": status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    with _lock:
        logs = _logs[session_id]
        logs.append(entry)
        # Rolling window — drop oldest if over limit
        if len(logs) > MAX_LOGS_PER_SESSION:
            _logs[session_id] = logs[-MAX_LOGS_PER_SESSION:]

    return entry


def get_logs(session_id: str, since_index: int = 0) -> list:
    """
    Returns all logs for a session starting from since_index.
    The frontend sends its current count so we only return new entries.
    """
    with _lock:
        all_logs = _logs.get(session_id, [])
        return all_logs[since_index:]


def clear_logs(session_id: str):
    """Clears logs for a session (called when a new conversation starts)."""
    with _lock:
        _logs[session_id] = []


def get_all_sessions() -> list:
    """Returns a summary of all active sessions for the admin overview."""
    with _lock:
        return [
            {
                "session_id": sid,
                "log_count": len(logs),
                "last_activity": logs[-1]["timestamp"] if logs else None,
            }
            for sid, logs in _logs.items()
        ]
    

if __name__ == "__main__":
    log_step(
        session_id="test-session",
        step="test_step",
        reasoning="Testing log service"
    )

    print(get_logs("test-session"))