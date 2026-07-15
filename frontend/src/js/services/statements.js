/* ---------------- Statements — printed letterhead document ---------------- */
async function renderStatements() {
  const main = document.getElementById("main");
  const mine = await myAccountOrNull();
  main.innerHTML = pageHeader("Statements", "Your account activity") + (mine ? `
    <div class="card fade-in">
      <div class="split" style="gap:10px;">
        <div><label>From</label><input id="st_from" type="date" /></div>
        <div><label>To</label><input id="st_to" type="date" /></div>
        <button class="btn" onclick="loadStatement()" style="align-self:flex-end;">Run</button>
      </div>
    </div>
    <div class="letterhead fade-in" style="margin-top:16px;">
      <div class="letterhead-head">
        <div class="lh-brand">VeeraBank</div>
        <div class="lh-acct">${mine.account_number}<br/>${mine.owner_name}</div>
      </div>
      <div id="st_totals"></div>
      <div class="letterhead-body" id="st_list"><div class="empty">Loading…</div></div>
    </div>
  ` : noAccountCard("statements"));
  if (mine) loadStatement();
}
async function loadStatement() {
  const mine = cachedAccounts[0];
  const box = document.getElementById("st_list"), sum = document.getElementById("st_totals");
  try {
    const from = document.getElementById("st_from").value, to = document.getElementById("st_to").value;
    const q = new URLSearchParams(); if (from) q.set("from_date", from); if (to) q.set("to_date", to);
    const s = await api(`/statements/${mine.account_id}?${q}`);
    sum.innerHTML = `<div class="letterhead-totals">
      <div><div class="t-lbl">Credits</div><div class="t-val" style="color:#177a53;">+$${fmtMoney(s.total_credits)}</div></div>
      <div><div class="t-lbl">Debits</div><div class="t-val" style="color:#b3392f;">−$${fmtMoney(s.total_debits)}</div></div>
      <div><div class="t-lbl">Balance</div><div class="t-val">$${fmtMoney(s.current_balance)}</div></div>
    </div>`;
    box.innerHTML = s.lines.length ? s.lines.map(l => `
      <div class="letterhead-row"><span class="desc">${l.description}</span><span>${l.amount<0?'−':'+'}$${fmtMoney(Math.abs(l.amount))} <span class="dt">${fmtWhen(l.date)}</span></span></div>
    `).join("") : `<div class="empty" style="color:#7a7460;">No activity in this period.</div>`;
  } catch (e) { box.innerHTML = `<div class="empty">${e.message}</div>`; }
}
