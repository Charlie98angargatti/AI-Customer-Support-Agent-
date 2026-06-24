/**
 * app.js — ShopEase AI Support Agent Frontend
 * =============================================
 * Manages:
 *  1. Chat UI — sends messages, renders responses, typing indicator
 *  2. Admin Dashboard — live reasoning log polling, customer/refund tables
 *  3. Session management — creates new sessions, tracks session_id
 *  4. Tab navigation — switches between Chat and Admin panels
 *
 * All API calls go to http://localhost:8000/api/*
 * Change API_BASE below if your backend runs on a different port/host.
 */

// ─── Configuration ─────────────────────────────────────────────────────────────
const API_BASE = "http://localhost:8000";
const LOG_POLL_INTERVAL_MS = 2000;   // How often to fetch new reasoning logs
const MAX_LOG_ENTRIES_DISPLAYED = 50; // Cap to prevent DOM overflow

// ─── State ─────────────────────────────────────────────────────────────────────
let state = {
  sessionId: null,
  isLoading: false,
  logCount: 0,         // How many logs we've already fetched (for incremental polling)
  logPollTimer: null,  // setInterval handle
  isOnline: false,
};


// ─── DOM References ─────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const DOM = {
  sessionId:     $("sessionId"),
  newSessionBtn: $("newSessionBtn"),
  ctxCustomerId: $("ctxCustomerId"),
  ctxOrderId:    $("ctxOrderId"),
  ctxFillBtn:    $("ctxFillBtn"),
  messagesArea:  $("messagesArea"),
  chatInput:     $("chatInput"),
  sendBtn:       $("sendBtn"),
  charCount:     $("charCount"),
  statusDot:     $("statusDot"),
  statusText:    $("statusText"),
  chatPanel:     $("chatPanel"),
  adminPanel:    $("adminPanel"),
  logStream:     $("logStream"),
  clearLogsBtn:  $("clearLogsBtn"),
  refreshDataBtn:$("refreshDataBtn"),
  customersTbody:$("customersTbody"),
  refundsTbody:  $("refundsTbody"),
};


// ════════════════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ════════════════════════════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", async () => {
  await checkHealth();
  await startNewSession();
  bindEvents();
  startLogPolling();
});


// ─── Health check ─────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      setStatus("online", "Agent ready");
    } else {
      setStatus("offline", "Service error");
    }
  } catch {
    setStatus("offline", "Cannot connect — is the server running?");
  }
}

function setStatus(status, text) {
  state.isOnline = status === "online";
  DOM.statusDot.className = `status-dot ${status}`;
  DOM.statusText.textContent = text;
}


// ════════════════════════════════════════════════════════════════════════════════
// SESSION MANAGEMENT
// ════════════════════════════════════════════════════════════════════════════════

async function startNewSession() {
  try {
    const res = await fetch(`${API_BASE}/api/session/new`, { method: "POST" });
    const data = await res.json();
    state.sessionId = data.session_id;
    state.logCount = 0;

    DOM.sessionId.textContent = state.sessionId;

    // Clear messages — show welcome card again
    DOM.messagesArea.innerHTML = "";
    renderWelcomeCard();

    // Clear log stream
    DOM.logStream.innerHTML = renderLogEmpty();

    console.log("🆕 New session:", state.sessionId);
  } catch (err) {
    console.error("Failed to create session:", err);
  }
}


// ════════════════════════════════════════════════════════════════════════════════
// CHAT
// ════════════════════════════════════════════════════════════════════════════════

async function sendMessage(text) {
  if (!text.trim() || state.isLoading) return;
  if (!state.sessionId) {
    await startNewSession();
  }

  const userText = text.trim();
  DOM.chatInput.value = "";
  DOM.chatInput.style.height = "auto";
  updateCharCount();
  updateSendBtn();

  // Remove welcome card
  const welcome = DOM.messagesArea.querySelector(".welcome-card");
  if (welcome) welcome.remove();

  // Render user message
  appendMessage("user", userText);

  // Show typing indicator
  showTypingIndicator();

  state.isLoading = true;
  updateSendBtn();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        message: userText,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();

    removeTypingIndicator();
    appendMessage("agent", data.response);

    // Update log count hint so polling fetches new logs immediately
    // (polling will pick them up on next tick anyway)

  } catch (err) {
    removeTypingIndicator();
    appendMessage("agent", `⚠️ Error: ${err.message}\n\nPlease make sure the backend server is running.`);
  } finally {
    state.isLoading = false;
    updateSendBtn();
  }
}


// ── Message rendering ────────────────────────────────────────────────────────

function appendMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role === "agent" ? "agent-message" : "user-message"}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = role === "agent" ? "AI" : "You";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  // Parse the decision block from agent responses
  if (role === "agent") {
    const { bodyHtml, decisionBadge } = parseAgentResponse(text);
    bubble.innerHTML = bodyHtml;
    if (decisionBadge) {
      bubble.insertAdjacentHTML("beforeend", decisionBadge);
    }
  } else {
    bubble.textContent = text;
  }

  div.appendChild(avatar);
  div.appendChild(bubble);
  DOM.messagesArea.appendChild(div);
  DOM.messagesArea.scrollTop = DOM.messagesArea.scrollHeight;
}

/**
 * Parses agent response text to:
 *  1. Escape HTML in the body
 *  2. Extract the ---Decision--- block and render as a badge
 */
function parseAgentResponse(text) {
  // Detect decision line
  const decisionMatch = text.match(/\*\*Decision:\*\*\s*(APPROVED|PARTIALLY APPROVED|DENIED|UNDER REVIEW)/i);
  let decisionBadge = "";

  if (decisionMatch) {
    const decision = decisionMatch[1].toUpperCase();
    const badgeClass =
      decision.includes("APPROVED") && !decision.includes("PARTIAL") ? "approved" :
      decision.includes("PARTIAL") ? "partial" :
      decision.includes("DENIED") ? "denied" : "escalated";

    const icons = {
      approved: "✓", partial: "⚑", denied: "✕", escalated: "⟳"
    };
    decisionBadge = `<div class="decision-badge ${badgeClass}">${icons[badgeClass] || "•"} ${decision}</div>`;
  }

  // Basic formatting: bold, line breaks
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");

  return { bodyHtml: escaped, decisionBadge };
}

function showTypingIndicator() {
  const tpl = document.getElementById("typingTpl");
  const clone = tpl.content.cloneNode(true);
  DOM.messagesArea.appendChild(clone);
  DOM.messagesArea.scrollTop = DOM.messagesArea.scrollHeight;
}

function removeTypingIndicator() {
  const indicator = DOM.messagesArea.querySelector("#typingIndicator");
  if (indicator) indicator.remove();
}

function renderWelcomeCard() {
  DOM.messagesArea.innerHTML = `
    <div class="welcome-card">
      <div class="welcome-icon">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/>
        </svg>
      </div>
      <h2>How can I help you today?</h2>
      <p>I can process refund requests, check order status, and answer questions about your purchases.</p>
      <div class="quick-actions">
        <button class="quick-btn" data-msg="I'd like to request a refund for order ORD-1001. My customer ID is C001. The item arrived damaged.">Request a refund (damaged item)</button>
        <button class="quick-btn" data-msg="My customer ID is C005 and I want a refund for order ORD-1016.">Repeat claimant test</button>
        <button class="quick-btn" data-msg="I need a refund for order ORD-1008, customer C008. I no longer need the software.">Digital product test</button>
        <button class="quick-btn" data-msg="Hello, I'd like to check my order status.">General inquiry</button>
      </div>
    </div>`;
  // Re-bind quick actions
  DOM.messagesArea.querySelectorAll(".quick-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      DOM.chatInput.value = btn.dataset.msg;
      updateSendBtn();
      updateCharCount();
      DOM.chatInput.focus();
    });
  });
}


// ════════════════════════════════════════════════════════════════════════════════
// ADMIN PANEL — REASONING LOG
// ════════════════════════════════════════════════════════════════════════════════

function startLogPolling() {
  if (state.logPollTimer) clearInterval(state.logPollTimer);
  state.logPollTimer = setInterval(fetchNewLogs, LOG_POLL_INTERVAL_MS);
}

async function fetchNewLogs() {
  if (!state.sessionId) return;

  try {
    const res = await fetch(
      `${API_BASE}/api/logs/${state.sessionId}?since=${state.logCount}`
    );
    if (!res.ok) return;

    const data = await res.json();
    if (data.logs && data.logs.length > 0) {
      renderNewLogs(data.logs);
      state.logCount = data.total;
    }
  } catch {
    // Silently fail — server may be restarting
  }
}

function renderNewLogs(logs) {
  // Remove the empty state placeholder if present
  const empty = DOM.logStream.querySelector(".log-empty");
  if (empty) empty.remove();

  logs.forEach(log => {
    const entry = buildLogEntry(log);
    DOM.logStream.appendChild(entry);

    // Cap displayed entries
    while (DOM.logStream.children.length > MAX_LOG_ENTRIES_DISPLAYED) {
      DOM.logStream.removeChild(DOM.logStream.firstChild);
    }
  });

  // Auto-scroll to bottom
  DOM.logStream.scrollTop = DOM.logStream.scrollHeight;
}

function buildLogEntry(log) {
  const div = document.createElement("div");
  div.className = `log-entry status-${log.status}`;

  // Determine chip style by step name
  const step = log.step || "";
  let chipClass = "";
  if (step.includes("tool") || step.includes("executing")) chipClass = "tool";
  else if (step.includes("policy")) chipClass = "policy";
  else if (step.includes("error")) chipClass = "error";
  else if (step.includes("result") || step.includes("success") || step.includes("respond")) chipClass = "success";

  const ts = new Date(log.timestamp).toLocaleTimeString();

  div.innerHTML = `
    <div class="log-header">
      <span class="log-step-chip ${chipClass}">${escHtml(step)}</span>
      <span class="log-ts">${ts}</span>
    </div>
    ${log.tool_called ? `<div class="log-tool-name">⚙ ${escHtml(log.tool_called)}</div>` : ""}
    ${log.reasoning ? `<div class="log-reasoning">${escHtml(log.reasoning).substring(0, 300)}</div>` : ""}
    ${log.output_summary ? `<div class="log-io">↳ ${escHtml(log.output_summary).substring(0, 200)}</div>` : ""}
  `;

  return div;
}

function renderLogEmpty() {
  return `<div class="log-empty">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
      <line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <p>Logs will appear here as the agent processes requests.</p>
  </div>`;
}


// ════════════════════════════════════════════════════════════════════════════════
// ADMIN PANEL — DATA TABLES
// ════════════════════════════════════════════════════════════════════════════════

async function loadCustomers() {
  try {
    const res = await fetch(`${API_BASE}/api/customers`);
    const data = await res.json();
    renderCustomersTable(data.customers || []);
  } catch {
    DOM.customersTbody.innerHTML = `<tr><td colspan="5" class="loading-cell">Failed to load</td></tr>`;
  }
}

function renderCustomersTable(customers) {
  if (!customers.length) {
    DOM.customersTbody.innerHTML = `<tr><td colspan="5" class="loading-cell">No customers found — run seed_data.py</td></tr>`;
    return;
  }

  DOM.customersTbody.innerHTML = customers.map(c => `
    <tr>
      <td><code style="font-family:var(--font-mono);font-size:11px;color:var(--text-code)">${escHtml(c.customer_id)}</code></td>
      <td>${escHtml(c.full_name)}</td>
      <td><span class="badge badge-${c.membership_tier}">${escHtml(c.membership_tier)}</span></td>
      <td><span class="badge badge-${c.account_status}">${escHtml(c.account_status)}</span></td>
      <td style="text-align:center;color:${c.refund_count_90d >= 3 ? 'var(--red)' : 'var(--text-primary)'}">
        ${c.refund_count_90d}
        ${c.refund_count_90d >= 3 ? ' ⚠' : ''}
      </td>
    </tr>
  `).join("");
}

async function loadRefunds() {
  try {
    const res = await fetch(`${API_BASE}/api/refunds`);
    const data = await res.json();
    renderRefundsTable(data.refunds || []);
  } catch {
    DOM.refundsTbody.innerHTML = `<tr><td colspan="5" class="loading-cell">Failed to load</td></tr>`;
  }
}

function renderRefundsTable(refunds) {
  if (!refunds.length) {
    DOM.refundsTbody.innerHTML = `<tr><td colspan="5" class="loading-cell">No refunds yet</td></tr>`;
    return;
  }

  DOM.refundsTbody.innerHTML = refunds.map(r => `
    <tr>
      <td><code style="font-family:var(--font-mono);font-size:11px;color:var(--text-code)">${escHtml(r.refund_id)}</code></td>
      <td>${escHtml(r.customer_name)}</td>
      <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${escHtml(r.product_name)}</td>
      <td style="font-weight:600">$${Number(r.amount).toFixed(2)}</td>
      <td><span class="badge badge-${r.status}">${escHtml(r.status)}</span></td>
    </tr>
  `).join("");
}


// ════════════════════════════════════════════════════════════════════════════════
// EVENT BINDING
// ════════════════════════════════════════════════════════════════════════════════

function bindEvents() {
  // ── Send message ──────────────────────────────────────────────
  DOM.sendBtn.addEventListener("click", () => sendMessage(DOM.chatInput.value));
  DOM.chatInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(DOM.chatInput.value);
    }
  });

  // ── Input state updates ───────────────────────────────────────
  DOM.chatInput.addEventListener("input", () => {
    autoResizeTextarea(DOM.chatInput);
    updateCharCount();
    updateSendBtn();
  });

  // ── New session ───────────────────────────────────────────────
  DOM.newSessionBtn.addEventListener("click", async () => {
    await startNewSession();
  });

  // ── Context fill ──────────────────────────────────────────────
  DOM.ctxFillBtn.addEventListener("click", () => {
    const cid = DOM.ctxCustomerId.value.trim();
    const oid = DOM.ctxOrderId.value.trim();
    if (cid || oid) {
      let fill = "I'd like to request a refund.";
      if (cid) fill += ` My customer ID is ${cid}.`;
      if (oid) fill += ` The order ID is ${oid}.`;
      DOM.chatInput.value = fill;
      updateSendBtn();
      updateCharCount();
      DOM.chatInput.focus();
    }
  });

  // ── Tab navigation ────────────────────────────────────────────
  document.querySelectorAll(".nav-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");

      const target = tab.dataset.tab;
      DOM.chatPanel.classList.toggle("hidden", target !== "chat");
      DOM.adminPanel.classList.toggle("hidden", target !== "admin");

      if (target === "admin") {
        loadCustomers();
        loadRefunds();
      }
    });
  });

  // ── Admin data tabs ───────────────────────────────────────────
  document.querySelectorAll(".data-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".data-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.dataset.dtab;
      $("customersPane").classList.toggle("hidden", target !== "customers");
      $("refundsPane").classList.toggle("hidden", target !== "refunds");
    });
  });

  // ── Clear logs ────────────────────────────────────────────────
  DOM.clearLogsBtn.addEventListener("click", () => {
    DOM.logStream.innerHTML = renderLogEmpty();
    state.logCount = 0;
  });

  // ── Refresh data ──────────────────────────────────────────────
  DOM.refreshDataBtn.addEventListener("click", () => {
    loadCustomers();
    loadRefunds();
  });

  // ── Quick actions (initial welcome card) ─────────────────────
  document.querySelectorAll(".quick-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      DOM.chatInput.value = btn.dataset.msg;
      updateSendBtn();
      updateCharCount();
      DOM.chatInput.focus();
    });
  });
}


// ════════════════════════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ════════════════════════════════════════════════════════════════════════════════

function updateSendBtn() {
  const hasText = DOM.chatInput.value.trim().length > 0;
  DOM.sendBtn.disabled = !hasText || state.isLoading;
}

function updateCharCount() {
  const len = DOM.chatInput.value.length;
  DOM.charCount.textContent = `${len} / 1000`;
  DOM.charCount.style.color = len > 900 ? "var(--red)" : "var(--text-muted)";
}

function autoResizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 150) + "px";
}

function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}