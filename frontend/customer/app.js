/**
 * Customer Chat Frontend
 * ======================
 * ONLY talks to PUBLIC endpoints:
 *   POST /api/session/new
 *   POST /api/chat
 *   GET  /health
 *
 * This file has NO admin token, NO log fetching, NO CRM access.
 * A customer opening DevTools will find nothing useful here.
 */
// cat > /home/claude/ai-support-agent/frontend/customer/app.js << 'EOF'
/**
 * Customer Chat Frontend
 * Only talks to PUBLIC endpoints - no admin token, no logs access.
 * POST /api/session/new
 * POST /api/chat
 * GET  /health
 */

const API = "http://localhost:8000";
let session = { id: null, loading: false };

const $ = id => document.getElementById(id);
const msgs      = $("messages");
const input     = $("chatInput");
const sendBtn   = $("sendBtn");
const sessionEl = $("sessionId");
const statusDot = $("statusDot");
const statusTxt = $("statusText");
const overlay   = $("loadingOverlay");
const loadFill  = $("loadingFill");
const loadMsg   = $("loadingMsg");

document.addEventListener("DOMContentLoaded", async () => {

  console.log("overlay =", overlay);
  console.log("loadFill =", loadFill);
  console.log("loadMsg =", loadMsg);

  if (loadFill) {
    setTimeout(() => { loadFill.style.width = "30%"; }, 200);
    setTimeout(() => { loadFill.style.width = "60%"; }, 8000);
    setTimeout(() => { loadFill.style.width = "85%"; }, 30000);
  }

  await waitForAgent();
  await startSession();
  bindEvents();
});

async function waitForAgent() {
  setStatus("loading", "Agent loading...");

  // Poll up to 20 minutes (Qwen on CPU can take a while on first load)
  // Every 4 seconds, check if backend is ready
  for (let attempt = 0; attempt < 300; attempt++) {
    try {
      const res = await fetch(`${API}/health`, {
        signal: AbortSignal.timeout(3000)
      });

      if (res.ok) {
        const data = await res.json();

        if (data.agent_ready === true) {
          // Agent is fully loaded and ready
        if (loadFill) {
          loadFill.style.width = "100%";
          loadFill.style.transition = "width 0.3s";
}

        await sleep(400);

        if (overlay) {
          overlay.classList.add("hidden");
}
          setStatus("online", "Agent ready");
          return;
        }

        if (data.agent_error) {
          // Something went wrong loading the model
          loadMsg.innerHTML = `
            <strong style="color:#ef4444">Agent failed to load:</strong><br>
            ${data.agent_error}<br><br>
            Check your terminal for details.
          `;
          setStatus("offline", "Agent error");
          return;
        }

        // Still loading - update message with time elapsed
        const elapsed = attempt * 4;
        if (elapsed < 30) {
          loadMsg.textContent = "Loading model weights... (first run takes 1-3 minutes)";
        } else if (elapsed < 90) {
          loadMsg.textContent = `Still loading... ${elapsed}s elapsed. Qwen on CPU is slow but getting there.`;
        } else if (elapsed < 180) {
          loadMsg.textContent = `Almost there... ${Math.floor(elapsed/60)}m ${elapsed%60}s elapsed.`;
        } else {
          loadMsg.textContent = `Loading for ${Math.floor(elapsed/60)} minutes. Check terminal for errors if this seems stuck.`;
        }

      } else {
        loadMsg.textContent = `Server responded with error ${res.status}. Check terminal.`;
      }

    } catch (err) {
      // Network error - server not reachable yet (still starting)
      const elapsed = attempt * 4;
      if (attempt === 0) {
        loadMsg.textContent = "Connecting to backend server...";
      } else if (elapsed < 15) {
        loadMsg.textContent = `Waiting for server to start... (${elapsed}s)`;
      } else {
        loadMsg.textContent = `Cannot reach server after ${elapsed}s. Is "python app.py" running in your terminal?`;
      }
    }

    await sleep(4000); // check every 4 seconds
  }

  // Timed out after 20 minutes
  loadMsg.textContent = "Timed out after 20 minutes. Please restart the backend and reload this page.";
  setStatus("offline", "Timed out");
}

function setStatus(cls, text) {
  statusDot.className = `status-dot ${cls}`;
  statusTxt.textContent = text;
}

// ── Session ─────────────────────────────────────────────────────────────────
async function startSession() {
  try {
    const res  = await fetch(`${API}/api/session/new`, { method: "POST" });
    const data = await res.json();
    session.id = data.session_id;
    sessionEl.textContent = session.id;
    renderWelcome();
  } catch (e) {
    console.error("Session creation failed:", e);
  }
}

// ── Send message ─────────────────────────────────────────────────────────────
async function send(text) {
  if (!text.trim() || session.loading) return;

  msgs.querySelector(".welcome")?.remove();
  appendMsg("user", text.trim());
  input.value = "";
  input.style.height = "auto";
  updateUI();
  showTyping();

  session.loading = true;
  updateUI();

  try {
    const res = await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: session.id, message: text.trim() }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    const data = await res.json();
    removeTyping();
    appendMsg("agent", data.response);

  } catch (err) {
    removeTyping();
    appendMsg("agent", `Sorry, something went wrong:\n${err.message}\n\nPlease try again.`);
  } finally {
    session.loading = false;
    updateUI();
  }
}

// ── Render messages ──────────────────────────────────────────────────────────
function appendMsg(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;

  const av = document.createElement("div");
  av.className = "avatar";
  av.textContent = role === "agent" ? "AI" : "You";

  const bub = document.createElement("div");
  bub.className = "bubble";

  if (role === "agent") {
    const { html, badge } = formatAgent(text);
    bub.innerHTML = html;
    if (badge) bub.insertAdjacentHTML("beforeend", badge);
  } else {
    bub.textContent = text;
  }

  div.appendChild(av);
  div.appendChild(bub);
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function formatAgent(text) {
  // Detect decision line for badge
  const dm = text.match(/\*\*Decision:\*\*\s*(APPROVED|PARTIALLY APPROVED|DENIED|UNDER REVIEW)/i);
  let badge = "";
  if (dm) {
    const d = dm[1].toUpperCase();
    const cls = d.includes("PARTIAL") ? "partial"
              : d.includes("APPROVE") ? "approved"
              : d.includes("DENIED")  ? "denied"
              : "escalated";
    const ico = { approved:"✓", partial:"⚑", denied:"✕", escalated:"⟳" };
    badge = `<div class="decision ${cls}">${ico[cls]} ${d}</div>`;
  }
  const html = esc(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
  return { html, badge };
}

function renderWelcome() {
  msgs.innerHTML = `
    <div class="welcome">
      <div class="w-icon">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/>
        </svg>
      </div>
      <h2>How can I help you?</h2>
      <p>I handle refunds, order issues, and general support for ShopEase customers.</p>
      <div class="quick-actions">
        <button class="qbtn" data-msg="My customer ID is C001 and order ORD-1001 arrived damaged. I need a refund.">Item arrived damaged</button>
        <button class="qbtn" data-msg="I am C002 and I changed my mind about order ORD-1002. Can I return it?">Changed my mind</button>
        <button class="qbtn" data-msg="I am customer C008, order ORD-1008. I want a refund on my software license.">Refund digital product</button>
        <button class="qbtn" data-msg="What is your refund policy?">Refund policy info</button>
      </div>
    </div>`;
  msgs.querySelectorAll(".qbtn").forEach(b =>
    b.addEventListener("click", () => {
      input.value = b.dataset.msg;
      updateUI();
      input.focus();
    })
  );
}

function showTyping() {
  const clone = document.getElementById("typingTpl").content.cloneNode(true);
  msgs.appendChild(clone);
  msgs.scrollTop = msgs.scrollHeight;
}

function removeTyping() {
  document.getElementById("typingIndicator")?.remove();
}

// ── Events ───────────────────────────────────────────────────────────────────
function bindEvents() {
  sendBtn.addEventListener("click", () => send(input.value));

  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input.value);
    }
  });

  input.addEventListener("input", () => {
    autoSize(input);
    updateUI();
  });

  $("newSessionBtn").addEventListener("click", async () => {
    msgs.innerHTML = "";
    session.id = null;
    await startSession();
  });

  $("ctxFillBtn").addEventListener("click", () => {
    const cid = $("ctxCid").value.trim();
    const oid = $("ctxOid").value.trim();
    if (!cid && !oid) return;
    let msg = "I need help.";
    if (cid && oid) msg = `My customer ID is ${cid} and my order ID is ${oid}. I would like a refund.`;
    else if (cid)   msg = `My customer ID is ${cid}. I need help with a refund.`;
    else if (oid)   msg = `My order ID is ${oid}. I need help with a refund.`;
    input.value = msg;
    updateUI();
    input.focus();
  });
}

function updateUI() {
  const hasText = input.value.trim().length > 0;
  sendBtn.disabled = !hasText || session.loading;
  $("charCount").textContent = `${input.value.length} / 1000`;
}

function autoSize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 140) + "px";
}

function esc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}
// const API = "http://localhost:8000";

// let session = { id: null, loading: false };

// // ── DOM ───────────────────────────────────────────────────────────────────────
// const $ = id => document.getElementById(id);
// const msgs       = $("messages");
// const input      = $("chatInput");
// const sendBtn    = $("sendBtn");
// const sessionEl  = $("sessionId");
// const statusDot  = $("statusDot");
// const statusText = $("statusText");
// const overlay    = $("loadingOverlay");
// const loadFill   = $("loadingFill");
// const loadMsg    = $("loadingMsg");

// // ── Startup ───────────────────────────────────────────────────────────────────
// document.addEventListener("DOMContentLoaded", async () => {
//   // Animate loading bar
//   setTimeout(() => { loadFill.style.width = "70%"; }, 100);

//   await waitForAgent();
//   await startSession();
//   bindEvents();
// });

// async function waitForAgent() {
//   statusDot.className = "status-dot loading";
//   statusText.textContent = "Agent loading…";

//   for (let attempt = 0; attempt < 60; attempt++) {
//     try {
//       const res = await fetch(`${API}/health`);
//       const data = await res.json();
//       if (data.agent_ready) {
//         loadFill.style.width = "100%";
//         await sleep(300);
//         overlay.classList.add("hidden");
//         setStatus("online", "Agent ready");
//         return;
//       }
//       if (data.agent_error) {
//         loadMsg.textContent = `Error: ${data.agent_error}`;
//         setStatus("offline", "Agent failed to start");
//         return;
//       }
//       loadMsg.textContent = `Still loading… (${attempt * 3}s elapsed)`;
//     } catch {
//       loadMsg.textContent = "Cannot reach server. Is backend running?";
//     }
//     await sleep(3000);
//   }
//   setStatus("offline", "Timeout — reload the page");
// }

// function setStatus(cls, text) {
//   statusDot.className = `status-dot ${cls}`;
//   statusText.textContent = text;
// }

// // ── Session ───────────────────────────────────────────────────────────────────
// async function startSession() {
//   try {
//     const res  = await fetch(`${API}/api/session/new`, { method: "POST" });
//     const data = await res.json();
//     session.id = data.session_id;
//     sessionEl.textContent = session.id;
//     renderWelcome();
//   } catch (e) {
//     console.error("Session error:", e);
//   }
// }

// // ── Send ──────────────────────────────────────────────────────────────────────
// async function send(text) {
//   if (!text.trim() || session.loading) return;
//   msgs.querySelector(".welcome")?.remove();
//   appendMsg("user", text.trim());
//   input.value = "";
//   input.style.height = "auto";
//   updateUI();
//   showTyping();
//   session.loading = true;
//   updateUI();

//   try {
//     const res = await fetch(`${API}/api/chat`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({ session_id: session.id, message: text.trim() }),
//     });

//     if (!res.ok) {
//       const err = await res.json().catch(() => ({}));
//       throw new Error(err.detail || `HTTP ${res.status}`);
//     }

//     const data = await res.json();
//     removeTyping();
//     appendMsg("agent", data.response);
//   } catch (err) {
//     removeTyping();
//     appendMsg("agent", `⚠️ ${err.message}\n\nPlease try again in a moment.`);
//   } finally {
//     session.loading = false;
//     updateUI();
//   }
// }

// // ── Render ────────────────────────────────────────────────────────────────────
// function appendMsg(role, text) {
//   const div = document.createElement("div");
//   div.className = `message ${role}`;

//   const av = document.createElement("div");
//   av.className = "avatar";
//   av.textContent = role === "agent" ? "AI" : "You";

//   const bub = document.createElement("div");
//   bub.className = "bubble";

//   if (role === "agent") {
//     const { html, badge } = format(text);
//     bub.innerHTML = html;
//     if (badge) bub.insertAdjacentHTML("beforeend", badge);
//   } else {
//     bub.textContent = text;
//   }

//   div.appendChild(av);
//   div.appendChild(bub);
//   msgs.appendChild(div);
//   msgs.scrollTop = msgs.scrollHeight;
// }

// function format(text) {
//   const dm = text.match(/\*\*Decision:\*\*\s*(APPROVED|PARTIALLY APPROVED|DENIED|UNDER REVIEW)/i);
//   let badge = "";
//   if (dm) {
//     const d = dm[1].toUpperCase();
//     const cls = d.includes("PARTIAL") ? "partial" : d.includes("APPROVE") ? "approved" : d.includes("DENIED") ? "denied" : "escalated";
//     const ico = { approved:"✓", partial:"⚑", denied:"✕", escalated:"⟳" };
//     badge = `<div class="decision ${cls}">${ico[cls]} ${d}</div>`;
//   }
//   const html = esc(text)
//     .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
//     .replace(/\n/g, "<br>");
//   return { html, badge };
// }

// function renderWelcome() {
//   msgs.innerHTML = `
//     <div class="welcome">
//       <div class="w-icon">
//         <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
//           <circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/>
//         </svg>
//       </div>
//       <h2>How can I help you?</h2>
//       <p>I handle refunds, order issues, and general support for ShopEase customers.</p>
//       <div class="quick-actions">
//         <button class="qbtn" data-msg="My customer ID is C001 and order ORD-1001 arrived damaged. I need a refund.">Item arrived damaged</button>
//         <button class="qbtn" data-msg="I'm C002 and I changed my mind about order ORD-1002. Can I return it?">Changed my mind</button>
//         <button class="qbtn" data-msg="I'm customer C008, order ORD-1008. I want a refund on my software license.">Refund digital product</button>
//         <button class="qbtn" data-msg="What is your refund policy?">Refund policy info</button>
//       </div>
//     </div>`;
//   msgs.querySelectorAll(".qbtn").forEach(b =>
//     b.addEventListener("click", () => {
//       input.value = b.dataset.msg;
//       updateUI();
//       input.focus();
//     })
//   );
// }

// function showTyping() {
//   const t = document.getElementById("typingTpl").content.cloneNode(true);
//   msgs.appendChild(t);
//   msgs.scrollTop = msgs.scrollHeight;
// }

// function removeTyping() {
//   document.getElementById("typingIndicator")?.remove();
// }

// // ── Events ────────────────────────────────────────────────────────────────────
// function bindEvents() {
//   sendBtn.addEventListener("click", () => send(input.value));
//   input.addEventListener("keydown", e => {
//     if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); }
//   });
//   input.addEventListener("input", () => { autoSize(input); updateUI(); });
//   $("newSessionBtn").addEventListener("click", async () => {
//     msgs.innerHTML = "";
//     await startSession();
//   });
//   $("ctxFillBtn").addEventListener("click", () => {
//     const cid = $("ctxCid").value.trim();
//     const oid = $("ctxOid").value.trim();
//     if (cid || oid) {
//       input.value = `I need help with${cid ? " customer ID " + cid : ""}${oid ? " order " + oid : ""}.`;
//       updateUI();
//       input.focus();
//     }
//   });
// }

// function updateUI() {
//   const has = input.value.trim().length > 0;
//   sendBtn.disabled = !has || session.loading;
//   $("charCount").textContent = `${input.value.length} / 1000`;
// }

// function autoSize(el) {
//   el.style.height = "auto";
//   el.style.height = Math.min(el.scrollHeight, 140) + "px";
// }

// function esc(s) {
//   return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
// }

// function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }