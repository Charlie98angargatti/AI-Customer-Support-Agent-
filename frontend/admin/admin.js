/**
 * Admin Dashboard JavaScript
 * ===========================
 * COMPLETELY SEPARATE from customer/app.js.
 *
 * Security model:
 * 1. User lands on /admin-panel → sees login form (no data, no token yet)
 * 2. User enters admin token → stored in memory (sessionStorage only)
 * 3. Every API call sends: X-Admin-Token: <token> header
 * 4. Backend rejects (401) if token is wrong or missing
 * 5. Customer browser never loads this file → never has token
 *
 * Why sessionStorage not localStorage:
 *   sessionStorage is cleared when the browser tab closes.
 *   localStorage persists forever — a security risk on shared machines.
 *
 * All /admin/* endpoints are used here.
 * No /api/chat is used here — this is purely operational monitoring.
 */

const API = "http://localhost:8000";

let adminToken = null;
let watchedSession = null;
let logCount = 0;
let pollTimer = null;

// ── DOM ───────────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Entry point ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Check if already logged in this browser session
  const saved = sessionStorage.getItem("shopease_admin_token");
  if (saved) {
    adminToken = saved;
    showDashboard();
  }
  bindLogin();
  bindDashboard();
});

// ═══════════════════════════════════════════════════════════════════════════════
// LOGIN
// ═══════════════════════════════════════════════════════════════════════════════

function bindLogin() {
  $("loginBtn").addEventListener("click", attemptLogin);
  $("tokenInput").addEventListener("keydown", e => {
    if (e.key === "Enter") attemptLogin();
  });
}

async function attemptLogin() {
  const token = $("tokenInput").value.trim();
  if (!token) return;

  // Validate token by calling a protected endpoint
  try {
    const res = await fetch(`${API}/admin/sessions`, {
      headers: { "X-Admin-Token": token }
    });

    if (res.ok) {
      // Token is valid
      adminToken = token;
      sessionStorage.setItem("shopease_admin_token", token); // persists for tab session
      $("loginError").classList.add("hidden");
      showDashboard();
    } else {
      $("loginError").classList.remove("hidden");
      $("tokenInput").value = "";
      $("tokenInput").focus();
    }
  } catch {
    $("loginError").textContent = "Cannot reach the backend server.";
    $("loginError").classList.remove("hidden");
  }
}

function showDashboard() {
  $("loginScreen").classList.add("hidden");
  $("dashboard").classList.remove("hidden");
  loadSessions();
  startLogPolling();
}

// ── Auth header helper ────────────────────────────────────────────────────────
function authHeader() {
  return { "X-Admin-Token": adminToken };
}

// ── Authenticated fetch ───────────────────────────────────────────────────────
async function adminFetch(path) {
  const res = await fetch(`${API}${path}`, { headers: authHeader() });
  if (res.status === 401) {
    // Token expired or revoked
    sessionStorage.removeItem("shopease_admin_token");
    adminToken = null;
    $("dashboard").classList.add("hidden");
    $("loginScreen").classList.remove("hidden");
    throw new Error("Session expired");
  }
  return res;
}

// ═══════════════════════════════════════════════════════════════════════════════
// DASHBOARD BINDING
// ═══════════════════════════════════════════════════════════════════════════════

function bindDashboard() {
  // Tab switching
  document.querySelectorAll(".dtab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".dtab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".view").forEach(v => {
        v.classList.toggle("active", false);
        v.classList.add("hidden");
      });
      const view = $(`view-${tab.dataset.view}`);
      view.classList.remove("hidden");
      view.classList.add("active");
      // Load data for the newly shown tab
      if (tab.dataset.view === "customers") loadCustomers();
      if (tab.dataset.view === "refunds") loadRefunds();
      if (tab.dataset.view === "sessions") loadAllSessions();
    });
  });

  // Logout
  $("logoutBtn").addEventListener("click", () => {
    sessionStorage.removeItem("shopease_admin_token");
    adminToken = null;
    clearInterval(pollTimer);
    $("dashboard").classList.add("hidden");
    $("loginScreen").classList.remove("hidden");
    $("tokenInput").value = "";
  });

  // Session picker (logs view)
  $("sessionSelect").addEventListener("change", e => {
    watchedSession = e.target.value || null;
    logCount = 0;
    $("logStream").innerHTML = watchedSession
      ? `<div class="empty-state"><p>Waiting for log entries for session <code>${watchedSession}</code>…</p></div>`
      : `<div class="empty-state"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><p>Select a session above to watch its reasoning logs.</p></div>`;
  });

  $("refreshSessionsBtn").addEventListener("click", loadSessions);
  $("clearLogsBtn").addEventListener("click", () => {
    logCount = 0;
    $("logStream").innerHTML = `<div class="empty-state"><p>Log display cleared. New entries will appear below.</p></div>`;
  });
  $("refreshCustomersBtn").addEventListener("click", loadCustomers);
  $("refreshRefundsBtn").addEventListener("click", loadRefunds);
  $("refreshAllSessionsBtn").addEventListener("click", loadAllSessions);
}

// ═══════════════════════════════════════════════════════════════════════════════
// LOG POLLING  (real-time reasoning trace)
// ═══════════════════════════════════════════════════════════════════════════════

function startLogPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(fetchLogs, 2000);
}

async function fetchLogs() {
  if (!watchedSession || !adminToken) return;

  try {
    const res = await adminFetch(`/admin/logs/${watchedSession}?since=${logCount}`);
    const data = await res.json();
    if (data.logs?.length > 0) {
      renderLogs(data.logs);
      logCount = data.total;
    }
  } catch (e) {
    if (e.message !== "Session expired") console.warn("Log poll error:", e);
  }
}

function renderLogs(logs) {
  const stream = $("logStream");
  stream.querySelector(".empty-state")?.remove();

  logs.forEach(log => {
    const entry = document.createElement("div");
    entry.className = `log-entry status-${log.status}`;

    const step = log.step || "";
    let chipClass = "";
    if (step.includes("tool") || step.includes("executing")) chipClass = "tool";
    else if (step.includes("policy")) chipClass = "policy";
    else if (step.includes("error")) chipClass = "error";
    else if (step.includes("result") || step.includes("respond") || step.includes("success")) chipClass = "success";
    else if (step.includes("session")) chipClass = "session";

    const ts = new Date(log.timestamp).toLocaleTimeString("en-GB", { hour12: false });

    entry.innerHTML = `
      <div class="log-header">
        <span class="chip ${chipClass}">${esc(step)}</span>
        <span class="log-ts">${ts}</span>
      </div>
      ${log.tool_called ? `<div class="log-tool">⚙ ${esc(log.tool_called)}</div>` : ""}
      ${log.reasoning ? `<div class="log-text">${esc(log.reasoning).slice(0,400)}</div>` : ""}
      ${log.output_summary ? `<div class="log-io">↳ ${esc(log.output_summary).slice(0,250)}</div>` : ""}
    `;
    stream.appendChild(entry);

    // Cap at 80 entries to prevent DOM bloat
    while (stream.children.length > 80) stream.removeChild(stream.firstChild);
  });

  stream.scrollTop = stream.scrollHeight;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SESSIONS
// ═══════════════════════════════════════════════════════════════════════════════

async function loadSessions() {
  try {
    const res  = await adminFetch("/admin/sessions");
    const data = await res.json();
    const sessions = data.sessions || [];

    // Populate the dropdown in the logs view
    const sel = $("sessionSelect");
    const prev = sel.value;
    sel.innerHTML = '<option value="">— select session —</option>';
    sessions.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.session_id;
      opt.textContent = `${s.session_id}  (${s.log_count} logs)`;
      sel.appendChild(opt);
    });
    if (prev) sel.value = prev; // restore selection
  } catch (e) {
    console.error("Sessions error:", e);
  }
}

async function loadAllSessions() {
  try {
    const res  = await adminFetch("/admin/sessions");
    const data = await res.json();
    const sessions = data.sessions || [];
    const tbody = $("sessionsTbody");

    if (!sessions.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="loading-cell">No active sessions yet</td></tr>';
      return;
    }

    tbody.innerHTML = sessions.map(s => `
      <tr>
        <td><span class="mono">${esc(s.session_id)}</span></td>
        <td>${s.log_count}</td>
        <td style="color:var(--text-2);font-size:12px">${s.last_activity ? new Date(s.last_activity).toLocaleString() : "—"}</td>
        <td><button class="watch-btn" onclick="watchSession('${s.session_id}')">Watch logs</button></td>
      </tr>
    `).join("");
  } catch (e) {
    $("sessionsTbody").innerHTML = '<tr><td colspan="4" class="loading-cell">Error loading sessions</td></tr>';
  }
}

window.watchSession = function(sessionId) {
  // Switch to logs tab and select this session
  document.querySelector('[data-view="logs"]').click();
  $("sessionSelect").value = sessionId;
  $("sessionSelect").dispatchEvent(new Event("change"));
};

// ═══════════════════════════════════════════════════════════════════════════════
// CUSTOMERS
// ═══════════════════════════════════════════════════════════════════════════════

async function loadCustomers() {
  try {
    const res  = await adminFetch("/admin/customers");
    const data = await res.json();
    const tbody = $("customersTbody");

    tbody.innerHTML = (data.customers || []).map(c => `
      <tr>
        <td><span class="mono">${esc(c.customer_id)}</span></td>
        <td>${esc(c.full_name)}</td>
        <td style="color:var(--text-2);font-size:12px">${esc(c.email)}</td>
        <td><span class="badge badge-${c.membership_tier}">${esc(c.membership_tier)}</span></td>
        <td><span class="badge badge-${c.account_status}">${esc(c.account_status)}</span></td>
        <td style="text-align:center;color:${c.refund_count_90d >= 3 ? 'var(--red)' : 'var(--text)'}">
          ${c.refund_count_90d}${c.refund_count_90d >= 3 ? ' ⚠' : ''}
        </td>
      </tr>
    `).join("") || '<tr><td colspan="6" class="loading-cell">No customers — run seed_data.py</td></tr>';
  } catch (e) {
    $("customersTbody").innerHTML = '<tr><td colspan="6" class="loading-cell">Error loading customers</td></tr>';
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// REFUNDS
// ═══════════════════════════════════════════════════════════════════════════════

async function loadRefunds() {
  try {
    const res  = await adminFetch("/admin/refunds");
    const data = await res.json();
    const tbody = $("refundsTbody");

    tbody.innerHTML = (data.refunds || []).map(r => `
      <tr>
        <td><span class="mono">${esc(r.refund_id)}</span></td>
        <td>${esc(r.customer_name)}</td>
        <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.product_name)}</td>
        <td style="font-weight:600">$${Number(r.amount||0).toFixed(2)}</td>
        <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-2);font-size:12px">${esc(r.reason)}</td>
        <td><span class="badge badge-${r.status}">${esc(r.status)}</span></td>
        <td style="color:var(--text-2);font-size:12px">${r.requested_at ? new Date(r.requested_at).toLocaleDateString() : "—"}</td>
      </tr>
    `).join("") || '<tr><td colspan="7" class="loading-cell">No refunds yet</td></tr>';
  } catch (e) {
    $("refundsTbody").innerHTML = '<tr><td colspan="7" class="loading-cell">Error loading refunds</td></tr>';
  }
}

// ─── Utility ──────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}