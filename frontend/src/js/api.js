/* =========================================================================
   Config — each microservice is reached via its own ingress path prefix.
   ========================================================================= */
const GENERIC_SERVICES = [
  "cards","loans","payments","beneficiaries","statements",
  "notifications","kyc","fixed-deposits","cheques","disputes",
  "audit-log","fraud-detection","support-tickets","rewards","admin","reports"
];
const SERVICE_ICONS = {
  cards:"▭", loans:"⌘", payments:"◈", beneficiaries:"◎",
  statements:"▤", notifications:"◔", kyc:"✓", "fixed-deposits":"◒",
  cheques:"▥", disputes:"!", "audit-log":"≡", "fraud-detection":"◭",
  "support-tickets":"?", rewards:"★", admin:"⚙", reports:"▦"
};

let currentUser = JSON.parse(localStorage.getItem("veera_user") || "null");
let currentTab = "dashboard";
let authTab = "login";
let cachedAccounts = [];

/* ---------------------------------------------------------------------- */
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.statusText || "Request failed");
  return body;
}
/* VeeraBank is one-account-per-person: this returns [] or [theirAccount],
   never the whole bank's accounts, so every screen that used to say
   "your accounts" (plural, from a naive /accounts list-all) now shows
   only what's actually theirs. */
async function fetchMyAccounts() {
  try {
    const acct = await api(`/accounts/by-user/${currentUser.user_id}`);
    return [acct];
  } catch (e) {
    return [];
  }
}
async function myAccountOrNull() {
  const accts = await fetchMyAccounts();
  cachedAccounts = accts;
  return accts[0] || null;
}
function toast(text, ok = true) {
  const wrap = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = "toast" + (ok ? "" : " err");
  el.textContent = text;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}
function fmtMoney(n) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString(undefined, { month:"short", day:"numeric", hour:"2-digit", minute:"2-digit" });
}
function initials(name) {
  return (name || "?").trim().split(/\s+/).slice(0,2).map(w => w[0]?.toUpperCase() || "").join("");
}
function setUser(u) {
  currentUser = u;
  if (u) localStorage.setItem("veera_user", JSON.stringify(u));
  else localStorage.removeItem("veera_user");
}

/* ---------------- Shared helpers for the service pages ---------------- */
function row(left, right, sub) {
  return `<div class="split" style="justify-content:space-between; padding:10px 0; border-bottom:1px solid var(--line);">
    <div><div style="font-size:13px; font-weight:600;">${left}</div>${sub ? `<div class="when">${sub}</div>` : ""}</div>
    <div>${right}</div>
  </div>`;
}
function badge(text, tone) {
  const colors = { open:"var(--gold)", active:"var(--ledger)", pending:"var(--gold)", pending_review:"var(--gold)",
    verified:"var(--ledger)", cleared:"var(--ledger)", resolved:"var(--ledger)", completed:"var(--ledger)", closed:"var(--muted-2)",
    rejected:"var(--danger)", bounced:"var(--danger)", frozen:"var(--danger)", matured:"var(--ledger)", closed_early:"var(--muted-2)" };
  return `<span class="badge" style="border-color:${colors[tone]||'var(--line)'}; color:${colors[tone]||'var(--text)'}">${(tone||'').replace('_',' ')}</span>`;
}
function noAccountCard(serviceLabel) {
  return `<div class="card fade-in"><div class="empty"><div class="big">No account yet</div>Open your VeeraBank account first to use ${serviceLabel}.</div></div>`;
}
function renderLedgerTable(rows, showOwner, clickable) {
  if (!rows.length) return `<div class="empty"><div class="big">Nothing here yet</div>Transactions will appear as soon as they post.</div>`;
  return `
    <table class="ledger">
      <thead><tr><th>Transaction</th>${showOwner ? "<th>Account</th>" : ""}<th>Amount</th><th>Balance after</th><th>When</th></tr></thead>
      <tbody>
        ${rows.map((t,i) => `
          <tr class="${clickable ? 'clickable' : ''}" ${clickable ? `onclick='openReceipt(${JSON.stringify(t).replace(/'/g,"&apos;")})'` : ""}>
            <td><div class="tcell"><div class="tick ${t.type==='withdrawal'?'neg':''}"></div><div><div style="font-weight:600; font-size:12.5px; text-transform:capitalize;">${t.type}</div><div class="idcell">${(t.transaction_id||'').slice(0,8)}</div></div></div></td>
            ${showOwner ? `<td>${t.owner || ''}</td>` : ""}
            <td class="amt ${t.type==='withdrawal'?'neg':'pos'}">${t.type==='withdrawal'?'−':'+'}$${fmtMoney(t.amount)}</td>
            <td class="amt">$${fmtMoney(t.balance_after)}</td>
            <td class="when">${fmtWhen(t.created_at)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}
