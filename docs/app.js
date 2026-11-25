/* TTJ oshxona hisobi — Telegram Mini App (serversiz).
 * Hisob-kitob: logic.js, Telegram bulutiga saqlash: store.js. */
(() => {
  'use strict';

  const BOT_LINK = 'https://t.me/oshpazhisob_bot';
  const tg = window.Telegram && window.Telegram.WebApp;
  const inTG = !!(tg && tg.initData);
  const tgAtLeast = v => inTG && tg.isVersionAtLeast && tg.isVersionAtLeast(v);
  if (tg) {
    try { tg.ready(); tg.expand(); } catch (e) { /* brauzerda */ }
    if (tgAtLeast('6.1')) try { tg.setHeaderColor('secondary_bg_color'); } catch (e) {}
    if (tgAtLeast('7.7')) try { tg.disableVerticalSwipes(); } catch (e) {}
  }

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const view = $('#view');
  const S = { tab: 'pay', st: null, floor: 'all', filter: 'all', q: '', rep: { k: 'w', o: 0 },
              expCat: null, openId: null, feeWhen: 'now', sync: 'synced', savedAt: null, user: null };
  let db, store, sync, mirror;

  // ------------------------------------------------------------ yordamchilar
  const fmt = n => (n < 0 ? '-' : '') + Math.abs(Math.round(n)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const money = n => fmt(n) + " so'm";
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const STATUS_TXT = { ok: "to'lagan", part: 'qisman', bad: "to'lamagan", exempt: 'bu hafta ozod', left: 'chiqib ketgan' };
  const field = (label, input) => `<div class="field grow"><label>${label}</label>${input}</div>`;
  const hhmm = d => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  const safeStorage = (() => { try { const s = window.localStorage; s.setItem('osh_t', '1'); s.removeItem('osh_t'); return s; } catch (e) { return null; } })();

  function haptic(type) { try { if (tgAtLeast('6.1')) tg.HapticFeedback.notificationOccurred(type); } catch (e) {} }

  /** Server versiyasidagi API bilan bir xil, lekin hammasi telefonda hisoblanadi. */
  async function api(method, path, body) {
    return db.api(method, path, body);
  }

  let toastTimer;
  function toast(text, { undo, error, long } = {}) {
    $('#toast-text').textContent = text;
    const ub = $('#toast-undo');
    ub.classList.toggle('hidden', !undo);
    ub.onclick = undo ? async () => { hideToast(); await undo(); } : null;
    $('#toast').classList.toggle('err', !!error);
    $('#toast').classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, long ? 9000 : undo ? 6000 : 3200);
  }
  function hideToast() { $('#toast').classList.add('hidden'); }
  function fail(e) { haptic('error'); toast(e.message || String(e), { error: true }); }

  function confirmBox(msg) {
    return new Promise(res => {
      if (tgAtLeast('6.2')) tg.showConfirm(msg, ok => res(!!ok));
      else res(window.confirm(msg));
    });
  }

  async function busy(btn, fn) {
    if (btn) btn.disabled = true;
    try { return await fn(); } catch (e) { fail(e); } finally { if (btn) btn.disabled = false; }
  }

  async function copyText(text, title) {
    try {
      // ba'zi telefonlarda clipboard javob bermay qoladi — 1.5 soniyada qo'lda nusxalashga o'tamiz
      await Promise.race([
        navigator.clipboard.writeText(text),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1500)),
      ]);
      haptic('success');
      toast('📋 Nusxalandi — istalgan chatga joylashtiring');
      return;
    } catch (e) { /* quyida qo'lda nusxalash */ }
    S.openId = null;
    openSheet(title, `<div class="card"><div class="hint" style="margin-bottom:8px">Matnni belgilab, nusxa oling:</div>
      <textarea class="input copy-area" id="copy-area" readonly>${esc(text)}</textarea></div>`);
    const ta = $('#copy-area');
    ta.focus();
    ta.select();
    try { if (document.execCommand('copy')) toast('📋 Nusxalandi'); } catch (e) { /* qo'lda */ }
  }

  // pul kiritiladigan maydonlar: "90000" -> "90 000"
  document.addEventListener('input', e => {
    const inp = e.target;
    if (!inp.classList || !inp.classList.contains('money')) return;
    const neg = inp.dataset.neg && inp.value.trim().startsWith('-');
    const digits = inp.value.replace(/\D/g, '');
    inp.value = (neg ? '-' : '') + (digits ? fmt(+digits) : '');
  });

  // ------------------------------------------------------------ bulut bilan sinxronlash
  const SYNC_TXT = {   // [tepadagi qisqa yozuv, sozlamadagi to'liq yozuv]
    synced: () => ['☁️', "Bulut bilan bir xil"],
    saved: () => ['☁️ Saqlandi', `Saqlandi (${hhmm(S.savedAt)})`],
    pending: () => ['⏳', 'Saqlanmoqda…'],
    saving: () => ['⏳', 'Saqlanmoqda…'],
    error: () => ['⚠️ Saqlanmadi', 'Saqlanmadi — internet qaytishi bilan o\'zi qayta urinadi'],
  };
  function setSync(status, info) {
    S.sync = status;
    if (status === 'saved') S.savedAt = new Date();
    const el = $('#sync');
    el.textContent = SYNC_TXT[status]()[0];
    el.className = 'sync ' + status;
    if (status === 'error' && info) el.title = info.message || String(info);
    if (tgAtLeast('6.2')) {   // saqlanmagan o'zgarish bor paytda ilovani yopishdan oldin so'raydi
      try { if (status === 'saved' || status === 'synced') tg.disableClosingConfirmation(); else tg.enableClosingConfirmation(); } catch (e) {}
    }
    const live = $('#sync-full');
    if (live) live.textContent = SYNC_TXT[status]()[1];
  }
  $('#sync').addEventListener('click', () => {
    if (S.sync === 'error') { toast('Qayta urinilmoqda…'); sync.flush(); }
  });

  async function adoptCloud(idx, data) {
    db.load(data);
    store.adopt(idx);
    mirror.save(data, idx.cid, false);
  }

  /** Ochilganda: bulut indeksi + telefondagi nusxa -> qaysi ma'lumot to'g'ri? */
  async function initialLoad() {
    const idx = await store.serial(() => store.loadIndex());
    const m = mirror.read();
    if (m && m.streams && m.cid === idx.cid && (m.pending || idx.cid)) {
      try {
        db.load(m.streams);           // telefondagi nusxa bulut bilan bir xil (yoki undan yangi) — tez ochiladi
        store.adopt(idx);
        if (m.pending) sync.markDirty();
        return;
      } catch (e) { /* nusxa buzilgan — bulutdan olamiz */ }
    }
    const data = await store.serial(() => store.loadData(idx));
    await adoptCloud(idx, data);
    if (m && m.pending) {
      toast("⚠️ Oxirgi o'zgarishlar saqlanmay qolgan edi, bu orada ma'lumot boshqa qurilmada o'zgargan. Tekshirib chiqing.", { error: true, long: true });
    }
  }

  async function onConflict() {
    const idx = await store.serial(() => store.loadIndex());
    const data = await store.serial(() => store.loadData(idx));
    await adoptCloud(idx, data);
    setSync('synced');
    await reload();
    toast("⚠️ Ma'lumot boshqa qurilmada o'zgartirilgan edi — yangisi yuklandi. Oxirgi amalingizni tekshiring.", { error: true, long: true });
  }

  /** Boshqa qurilmada (masalan kompyuterda) o'zgargan bo'lsa — yangisini olish. */
  async function pullIfChanged(manual) {
    if (sync.busy()) { if (manual) toast('Hozir saqlanmoqda, biroz kuting'); return; }
    const idx = await store.serial(() => store.loadIndex());
    if (idx.cid === store.cid()) { if (manual) toast("✓ Ma'lumot yangi"); return; }
    const data = await store.serial(() => store.loadData(idx));
    if (sync.busy()) return;          // shu orada nimadir kiritildi — keyinroq
    await adoptCloud(idx, data);
    setSync('synced');
    await reload();
    toast('🔄 Boshqa qurilmadagi o\'zgarishlar yuklandi');
  }

  // ------------------------------------------------------------ holat va bo'limlar
  async function loadState() {
    S.st = await api('GET', '/state');
    $('#top-sub').textContent = `${S.st.week} · haftalik ${money(S.st.fee)}`;
  }
  async function reload() { await loadState(); render(); if (S.openId) await openStudent(S.openId, true); }
  function showError(e) { view.innerHTML = `<div class="card empty">⚠️ ${esc(e.message)}</div>`; }

  function switchTab(tab) {
    S.tab = tab;
    $$('#tabs button').forEach(x => x.classList.toggle('active', x.dataset.tab === tab));
    window.scrollTo(0, 0);
    render();
  }
  $('#tabs').addEventListener('click', e => {
    const b = e.target.closest('button[data-tab]');
    if (b && S.st) switchTab(b.dataset.tab);
  });
  $('#refresh').addEventListener('click', async () => {
    if (!S.st) return;
    try { await pullIfChanged(true); } catch (e) { fail(e); }
  });

  function render() {
    if (!S.st) return;
    ({ pay: renderPay, exp: renderExp, rep: renderRep, kids: renderKids, set: renderSet })[S.tab]();
  }

  // ------------------------------------------------------------ 💵 TO'LOV
  function filteredStudents() {
    const q = S.q.trim().toLowerCase();
    return S.st.students.filter(s => s.active
      && (S.floor === 'all' || s.floor_id === S.floor)
      && (S.filter === 'all' || s.status === S.filter)
      && (!q || s.name.toLowerCase().includes(q) || (s.room || '').toLowerCase() === q));
  }

  function studentRow(s) {
    let right;
    if (s.debt > 0) {
      right = `<span class="amt bad">${fmt(s.debt)}</span>`
        + `<button class="mini" data-act="quickpay" data-id="${s.id}">+${fmt(S.st.fee)}</button>`;
    } else if (s.status === 'exempt') {
      right = '<span class="amt gray">💤</span>';
    } else if (s.debt < 0) {
      right = `<span class="amt ok">+${fmt(-s.debt)}</span>`;
    } else {
      right = '<span class="amt ok">✓</span>';
    }
    const sub = (s.room ? esc(s.room) + '-xona · ' : '') + STATUS_TXT[s.status];
    return `<div class="item" data-act="open" data-id="${s.id}"><span class="dot ${s.status}"></span>`
      + `<div class="grow"><div class="name">${esc(s.name)}</div><div class="sub">${sub}</div></div>${right}</div>`;
  }

  function studentList() {
    const list = filteredStudents();
    if (!list.length) {
      return `<div class="empty">${S.q || S.filter !== 'all' ? 'Hech kim topilmadi' : "Bu etajda hali bola yo'q"}</div>`;
    }
    if (S.floor !== 'all') return `<div class="list">${list.map(studentRow).join('')}</div>`;
    const groups = [];
    for (const s of list) {
      const g = groups[groups.length - 1];
      if (g && g.id === s.floor_id) g.items.push(s);
      else groups.push({ id: s.floor_id, name: s.floor, items: [s] });
    }
    return groups.map(g => `<div class="list"><div class="group-head"><span>${esc(g.name)}</span>`
      + `<span>${g.items.length} ta</span></div>${g.items.map(studentRow).join('')}</div>`).join('');
  }

  function renderPay() {
    const st = S.st, c = st.counts;
    if (!st.floors.length) {
      view.innerHTML = `<div class="card"><h3>👋 Xush kelibsiz!</h3>
        <p class="hint">Boshlash uchun «Bolalar» bo'limida avval etajlarni, keyin bolalarni qo'shing.</p>
        <p class="hint">Ma'lumotlar sizning Telegram akkauntingizda saqlanadi — telefon almashsa ham yo'qolmaydi.</p>
        <button class="btn" data-act="gotab" data-tab="kids">👥 Bolalar bo'limiga o'tish</button></div>`;
      return;
    }
    const stat = (key, n, label) => `<button class="stat ${S.filter === key ? 'sel' : ''}" data-act="filter" data-f="${key}">`
      + `<b class="${key === 'exempt' ? 'gray' : key}">${n}</b><span>${label}</span></button>`;
    view.innerHTML = `
      <div class="card">
        <div class="row between">
          <div><div class="hint">Jami qarz (faol bolalar)</div><div class="big ${c.debt > 0 ? 'bad' : 'ok'}">${money(c.debt)}</div></div>
          <div class="hint" style="text-align:right">${c.total} ta bola</div>
        </div>
        <div class="stats">${stat('ok', c.ok, "to'lagan")}${stat('part', c.part, 'qisman')}${stat('bad', c.bad, "to'lamagan")}${stat('exempt', c.exempt, 'ozod')}</div>
      </div>
      <input class="input search" id="q" type="search" placeholder="🔍 Ism yoki xona raqami" value="${esc(S.q)}">
      <div class="chips">
        <button class="chip ${S.floor === 'all' ? 'sel' : ''}" data-act="floor" data-id="all">Hammasi</button>
        ${st.floors.map(f => `<button class="chip ${S.floor === f.id ? 'sel' : ''}" data-act="floor" data-id="${f.id}">${esc(f.name)} · ${f.cnt}</button>`).join('')}
      </div>
      <div id="plist">${studentList()}</div>`;
    const q = $('#q');
    q.addEventListener('input', () => { S.q = q.value; $('#plist').innerHTML = studentList(); });
  }

  async function payNow(id, amount, btn) {
    return busy(btn, async () => {
      const r = await api('POST', '/pay', { student_id: id, amount });
      haptic('success');
      await reload();
      const tail = r.debt > 0 ? ` · qolgan qarz ${fmt(r.debt)}` : '';
      toast(`✅ ${r.name}: ${fmt(r.amount)} so'm${tail}`, {
        undo: async () => {
          try {
            await api('DELETE', `/payment/${r.payment_id}`);
            toast('↩️ Bekor qilindi');
            await reload();
          } catch (e) { fail(e); }
        },
      });
    });
  }

  // ------------------------------------------------------------ pastdan chiqadigan oyna
  function openSheet(title, html, keepScroll) {
    const body = $('#sheet-body');
    const top = keepScroll ? body.scrollTop : 0;
    $('#sheet-title').textContent = title;
    body.innerHTML = html;
    $('#sheet').classList.remove('hidden');
    $('#sheet-bg').classList.remove('hidden');
    body.scrollTop = top;
    document.body.style.overflow = 'hidden';
    if (tgAtLeast('6.1')) try { tg.BackButton.show(); } catch (e) {}
  }
  function closeSheet() {
    $('#sheet').classList.add('hidden');
    $('#sheet-bg').classList.add('hidden');
    document.body.style.overflow = '';
    S.openId = null;
    if (tgAtLeast('6.1')) try { tg.BackButton.hide(); } catch (e) {}
  }
  $('#sheet-close').addEventListener('click', closeSheet);
  $('#sheet-bg').addEventListener('click', closeSheet);
  if (tgAtLeast('6.1')) try { tg.BackButton.onClick(closeSheet); } catch (e) {}

  // ------------------------------------------------------------ bola kartochkasi
  async function openStudent(id, keepScroll) {
    let d;
    try { d = await api('GET', `/student/${id}`); } catch (e) { fail(e); return; }
    S.openId = id;
    const fee = S.st.fee;
    let status;
    if (d.debt > 0) status = `<div class="big ${d.status === 'part' ? 'part' : 'bad'}">Qarz: ${money(d.debt)}</div>`;
    else if (d.debt < 0) status = `<div class="big ok">Oldindan: ${money(-d.debt)}</div>`;
    else status = `<div class="big ok">Qarzi yo'q ✓</div>`;

    let h = `<div class="card status-box">${status}
      <div class="hint">${esc(d.floor)}${d.room ? ' · ' + esc(d.room) + '-xona' : ''}${d.phone ? ` · <a href="tel:${esc(d.phone)}">${esc(d.phone)}</a>` : ''}</div>
      <div class="hint">Bu hafta: ${money(d.paid_week)} · Jami: ${money(d.paid)}</div>
      ${d.exempt && d.active ? '<div class="hint">💤 Bu hafta ozod — to\'lov hisoblanmaydi</div>' : ''}
      ${!d.active ? `<div class="hint">🚶 Chiqib ketgan (${esc(d.left || '')})</div>` : ''}
    </div><div class="card">`;
    if (d.active) h += `<button class="btn ok" data-act="pay" data-id="${id}" data-amt="${fee}">✅ ${fmt(fee)} to'ladi</button>`;
    if (d.debt > 0 && d.debt !== fee) {
      h += `<button class="btn secondary" data-act="pay" data-id="${id}" data-amt="${d.debt}">Qarzini to'liq to'ladi: ${fmt(d.debt)}</button>`;
    }
    h += `<div class="btn-row" style="margin-top:8px">
        <input class="input money" id="cust" inputmode="numeric" placeholder="Boshqa summa">
        <button class="btn" style="width:auto" data-act="paycustom" data-id="${id}">Yozish</button></div>`;
    if (d.active) {
      h += `<button class="btn secondary" style="margin-top:8px" data-act="exempt" data-id="${id}">`
        + `${d.exempt ? '↩️ Ozodlikni bekor qilish' : '💤 Bu hafta ozod (uyga ketgan)'}</button>`;
    }
    h += '</div><div class="section-title">To\'lovlar tarixi</div>';
    h += d.payments.length
      ? `<div class="list">${d.payments.map(p => `<div class="item"><div class="grow"><div class="name">${money(p.amount)}</div>`
        + `<div class="sub">${esc(p.at)}${p.note ? ' · ' + esc(p.note) : ''}</div></div>`
        + `<button class="mini del" data-act="delpay" data-id="${p.id}" aria-label="O'chirish">🗑</button></div>`).join('')}</div>`
      : '<div class="card hint">Hali to\'lov yo\'q</div>';
    if (d.exemptions.length) h += `<div class="hint" style="margin:0 4px 12px">💤 Ozod haftalar: ${d.exemptions.map(esc).join(', ')}</div>`;
    h += `<div class="section-title">Ma'lumotlar</div><div class="card">
      ${field('Ism-familiya', `<input class="input" id="e-name" value="${esc(d.name)}">`)}
      <div class="btn-row">
        ${field('Xona', `<input class="input" id="e-room" value="${esc(d.room || '')}">`)}
        ${field('Telefon', `<input class="input" id="e-phone" inputmode="tel" value="${esc(d.phone || '')}">`)}
      </div>
      ${field('Etaj', `<select class="input" id="e-floor">${S.st.floors.map(f => `<option value="${f.id}" ${f.id === d.floor_id ? 'selected' : ''}>${esc(f.name)}</option>`).join('')}</select>`)}
      ${field("Daftardagi eski qarz (oldindan to'lagan bo'lsa minus bilan)", `<input class="input money" data-neg="1" id="e-debt" value="${fmt(d.opening_debt || 0)}">`)}
      <button class="btn secondary" data-act="save" data-id="${id}">💾 Saqlash</button>
    </div>`;
    if (d.active) h += `<button class="btn danger" data-act="leave" data-id="${id}">🚶 TTJdan chiqib ketdi</button>`;
    else {
      h += `<button class="btn" data-act="return" data-id="${id}">↩️ Qaytib keldi</button>`;
      if (d.can_delete) h += `<button class="btn danger" data-act="delstudent" data-id="${id}">🗑 Butunlay o'chirish</button>`;
    }
    openSheet(d.name, h, keepScroll);
  }

  // ------------------------------------------------------------ 🛒 XARAJAT
  async function renderExp() {
    let d;
    try { d = await api('GET', '/expenses'); } catch (e) { showError(e); return; }
    const cats = S.st.categories;
    let h = `<div class="kpis">
        <div class="kpi"><div class="label">Bu hafta</div><div class="value">${money(d.week)}</div></div>
        <div class="kpi"><div class="label">Bu oy</div><div class="value">${money(d.month)}</div></div>
      </div>
      <div class="card"><h3>➕ Yangi xarajat</h3>
        <div class="chips wrap">${cats.map((c, i) => `<button class="chip ${S.expCat === c ? 'sel' : ''}" data-act="cat" data-i="${i}">${esc(c)}</button>`).join('')}</div>
        ${field('Summa', '<input class="input money" id="x-amt" inputmode="numeric" placeholder="masalan 350 000">')}
        ${field('Nima olindi', '<input class="input" id="x-desc" maxlength="200" placeholder="masalan 5 kg mol go\'shti">')}
        ${field('Sana', `<input class="input" id="x-date" type="date" value="${d.today}" max="${d.today}">`)}
        <button class="btn" data-act="addexp">Saqlash</button>
      </div>
      <div class="section-title">Oxirgi xarajatlar</div>`;
    h += d.items.length
      ? `<div class="list">${d.items.map(e => `<div class="item"><div class="grow"><div class="name">${esc(e.category)}</div>`
        + `<div class="sub">${esc(e.date)}${e.description ? ' · ' + esc(e.description) : ''}</div></div>`
        + `<span class="amt">${fmt(e.amount)}</span><button class="mini del" data-act="delexp" data-id="${e.id}" aria-label="O'chirish">🗑</button></div>`).join('')}</div>`
      : '<div class="card hint">Hali xarajat yozilmagan</div>';
    view.innerHTML = h;
  }

  // ------------------------------------------------------------ 📊 HISOBOT
  async function renderRep() {
    let d;
    try { d = await api('GET', `/report?k=${S.rep.k}&o=${S.rep.o}`); } catch (e) { showError(e); return; }
    const maxCat = Math.max(1, ...d.by_cat.map(x => x.total));
    let h = `<div class="seg">
        <button class="${d.kind === 'w' ? 'sel' : ''}" data-act="repk" data-k="w">Hafta</button>
        <button class="${d.kind === 'm' ? 'sel' : ''}" data-act="repk" data-k="m">Oy</button>
      </div>
      <div class="period">
        <button class="icon-btn" data-act="repo" data-d="-1" aria-label="Oldingi">◀</button>
        <b>${esc(d.label)}</b>
        <button class="icon-btn" data-act="repo" data-d="1" aria-label="Keyingi" ${d.offset >= 0 ? 'style="visibility:hidden"' : ''}>▶</button>
      </div>
      <div class="kpis">
        <div class="kpi"><div class="label">💰 Kirim · ${d.n_pay} ta</div><div class="value ok">${fmt(d.income)}</div></div>
        <div class="kpi"><div class="label">🛒 Chiqim · ${d.n_exp} ta</div><div class="value bad">${fmt(d.expense)}</div></div>
        <div class="kpi wide"><div class="label">${d.diff >= 0 ? '📈' : '📉'} Farq (kirim − chiqim)</div>
          <div class="value ${d.diff >= 0 ? 'ok' : 'bad'}">${d.diff > 0 ? '+' : ''}${money(d.diff)}</div></div>
      </div>`;
    if (d.by_cat.length) {
      h += `<div class="card"><h3>Xarajatlar toifalar bo'yicha</h3>${d.by_cat.map(c => `<div class="bar-row">`
        + `<div class="row between"><span>${esc(c.name)}</span><b>${fmt(c.total)}</b></div>`
        + `<div class="bar"><i style="width:${Math.max(2, Math.round(c.total / maxCat * 100))}%"></i></div></div>`).join('')}</div>`;
    }
    if (d.by_floor.length) {
      h += `<div class="card"><h3>Kirim etajlar bo'yicha</h3>${d.by_floor.map(f => `<div class="kv"><span>${esc(f.name)}</span><b>${fmt(f.total)}</b></div>`).join('')}</div>`;
    }
    if (d.status) {
      const s = d.status;
      h += `<div class="card"><h3>Hozirgi holat · ${s.total} ta bola</h3>
        <div class="kv"><span class="ok">● To'lagan</span><b>${s.ok}</b></div>
        <div class="kv"><span class="part">● Qisman</span><b>${s.part}</b></div>
        <div class="kv"><span class="bad">● To'lamagan</span><b>${s.bad}</b></div>
        <div class="kv"><span class="gray">● Ozod</span><b>${s.exempt}</b></div>
        <div class="kv"><span>Faol bolalar qarzi</span><b class="bad">${money(s.debt)}</b></div></div>`;
    }
    const k = d.kassa;
    h += `<div class="card"><h3>🏦 Kassa (umumiy)</h3>
        <div class="kv"><span>Boshlang'ich (daftardan)</span><b>${fmt(k.opening)}</b></div>
        <div class="kv"><span>Jami kirim</span><b class="ok">${fmt(k.income)}</b></div>
        <div class="kv"><span>Jami chiqim</span><b class="bad">${fmt(k.expense)}</b></div>
        <div class="kv"><span><b>Kassada bo'lishi kerak</b></span><b>${money(k.balance)}</b></div>
        <div class="kv"><span>Qarzdorlar: ${k.debtors} ta</span><b class="bad">${fmt(k.debt)}</b></div>
        <div class="kv"><span>Oldindan to'langan</span><b>${fmt(k.prepaid)}</b></div>
      </div>
      <button class="btn" data-act="debtors">❗ Qarzdorlar ro'yxati</button>
      <div class="btn-row" style="margin-top:8px">
        <button class="btn secondary" data-act="copyrep">📋 Hisobotni nusxalash</button>
        <button class="btn secondary" data-act="copydebt">📋 Qarzdorlarni nusxalash</button>
      </div>
      <div class="hint" style="margin:8px 4px 0">Nusxalangan matnni istalgan chatga (masalan, rahbarga) yuborishingiz mumkin.</div>`;
    view.innerHTML = h;
  }

  const debtRow = i => `<div class="item" data-act="open" data-id="${i.id}"><span class="dot ${i.status}"></span>`
    + `<div class="grow"><div class="name">${esc(i.name)}</div><div class="sub">${i.room ? esc(i.room) + '-xona' : esc(i.floor)}</div></div>`
    + `<span class="amt bad">${fmt(i.debt)}</span></div>`;

  async function openDebtors() {
    let d;
    try { d = await api('GET', '/debtors'); } catch (e) { fail(e); return; }
    let h = '';
    if (!d.count) h = '<div class="empty">🎉 Hamma to\'lagan! Qarzdor yo\'q.</div>';
    else h = `<div class="card"><div class="hint">Jami ${d.count} ta bola</div><div class="big bad">${money(d.total)}</div></div>`;
    for (const g of d.groups) {
      h += `<div class="list"><div class="group-head"><span>${esc(g.floor)}</span><span>${g.items.length} ta</span></div>${g.items.map(debtRow).join('')}</div>`;
    }
    if (d.left.length) {
      h += `<div class="list"><div class="group-head"><span>🚶 Chiqib ketganlar</span><span>${d.left.length} ta</span></div>${d.left.map(debtRow).join('')}</div>`;
    }
    if (d.count) h += '<button class="btn secondary" data-act="copydebt">📋 Ro\'yxatni nusxalash</button>';
    S.openId = null;
    openSheet('❗ Qarzdorlar', h);
  }

  // ------------------------------------------------------------ 👥 BOLALAR
  function renderKids() {
    const st = S.st;
    const inactive = st.students.filter(s => !s.active);
    let h = `<div class="btn-row">
        <button class="btn" data-act="addkids">➕ Bola qo'shish</button>
        <button class="btn secondary" data-act="addfloors">🏢 Etaj qo'shish</button>
      </div><div class="section-title">Etajlar</div>`;
    h += st.floors.length
      ? `<div class="list">${st.floors.map(f => `<div class="item" data-act="floorgo" data-id="${f.id}">`
        + `<div class="grow"><div class="name">🏢 ${esc(f.name)}</div><div class="sub">${f.cnt} ta bola</div></div>`
        + `<button class="mini ghost" data-act="renfloor" data-id="${f.id}" aria-label="Nomini o'zgartirish">✏️</button>`
        + `<button class="mini del" data-act="delfloor" data-id="${f.id}" aria-label="O'chirish">🗑</button></div>`).join('')}</div>`
      : '<div class="card hint">Hali etaj yo\'q. Avval «🏢 Etaj qo\'shish» ni bosing.</div>';
    h += `<div class="section-title">Chiqib ketganlar (${inactive.length})</div>`;
    h += inactive.length
      ? `<div class="list">${inactive.map(s => `<div class="item" data-act="open" data-id="${s.id}"><span class="dot left"></span>`
        + `<div class="grow"><div class="name">${esc(s.name)}</div><div class="sub">${esc(s.floor)}</div></div>`
        + `${s.debt > 0 ? `<span class="amt bad">${fmt(s.debt)}</span>` : ''}</div>`).join('')}</div>`
      : '<div class="card hint">Yo\'q</div>';
    view.innerHTML = h;
  }

  function openAddKids() {
    if (!S.st.floors.length) { toast("Avval etaj qo'shing", { error: true }); return; }
    const sel = S.floor === 'all' ? S.st.floors[0].id : S.floor;
    S.openId = null;
    openSheet("➕ Bola qo'shish", `<div class="card">
      ${field('Etaj', `<select class="input" id="k-floor">${S.st.floors.map(f => `<option value="${f.id}" ${f.id === sel ? 'selected' : ''}>${esc(f.name)}</option>`).join('')}</select>`)}
      ${field("Ism-familiyalar — har biri yangi qatordan. Xona raqamini vergul bilan yozing",
        '<textarea class="input" id="k-text" placeholder="Aliyev Vali, 305&#10;Karimov Sardor, 305&#10;Toshmatov Jasur"></textarea>')}
      <button class="btn" data-act="addkidsgo">Qo'shish</button></div>`);
  }

  function openAddFloors() {
    S.openId = null;
    openSheet("🏢 Etaj qo'shish", `<div class="card">
      ${field("Etaj nomlari — har biri yangi qatordan. Faqat raqam yozsangiz ham bo'ladi: 1 → «1-etaj»",
        '<textarea class="input" id="f-text" placeholder="1&#10;2&#10;3&#10;4"></textarea>')}
      <button class="btn" data-act="addfloorsgo">Qo'shish</button></div>`);
  }

  function openRenameFloor(id) {
    const f = S.st.floors.find(x => x.id === id);
    if (!f) return;
    S.openId = null;
    openSheet('✏️ Etaj nomi', `<div class="card">
      ${field('Yangi nom', `<input class="input" id="f-name" value="${esc(f.name)}">`)}
      <button class="btn" data-act="renfloorgo" data-id="${id}">Saqlash</button></div>`);
  }

  // ------------------------------------------------------------ ⚙️ SOZLAMALAR
  async function renderSet() {
    let d;
    try { d = await api('GET', '/settings'); } catch (e) { showError(e); return; }
    S.feeWhen = 'now';
    const u = store.usage();
    const who = S.user && S.user.name ? `<b>${esc(S.user.name)}</b>` : 'shu';
    view.innerHTML = `
      <div class="card"><h3>💵 Haftalik to'lov</h3>
        <div class="big">${money(d.fee)}</div>
        ${d.next_fee !== d.fee ? `<div class="hint">Keyingi haftadan: ${money(d.next_fee)}</div>` : ''}
        <div style="margin-top:10px">
          ${field('Yangi summa', '<input class="input money" id="s-fee" inputmode="numeric" placeholder="masalan 100 000">')}
          <div class="chips wrap">
            <button class="chip sel" data-act="feewhen" data-w="now">Shu haftadan (${esc(d.this_week)})</button>
            <button class="chip" data-act="feewhen" data-w="next">Keyingi haftadan (${esc(d.next_week)})</button>
          </div>
          <button class="btn" data-act="setfee">O'zgartirish</button>
        </div>
        <div class="hint" style="margin-top:8px">O'tgan haftalar eski summa bilan qoladi.</div>
      </div>
      <div class="card"><h3>📒 Boshlang'ich kassa</h3>
        <div class="hint">Ilovadan foydalanishdan oldin qo'lingizda (daftarda) qancha pul bor edi.</div>
        <div class="btn-row" style="margin-top:8px">
          <input class="input money" id="s-cash" inputmode="numeric" value="${fmt(d.opening_cash)}">
          <button class="btn" style="width:auto" data-act="setcash">Saqlash</button>
        </div>
      </div>
      <div class="card"><h3>☁️ Ma'lumotlar qayerda saqlanadi</h3>
        <div class="hint">Hammasi ${who} Telegram akkauntida, Telegram bulutida saqlanadi. Telefon almashsa yoki buzilsa ham
          yo'qolmaydi — shu akkaunt bilan botni ochsangiz kifoya. Kompyuterdagi Telegram'dan ham ochsa bo'ladi.
          Boshqa odamlar bu ma'lumotni ko'ra olmaydi.</div>
        <div class="kv" style="margin-top:8px"><span>Holat</span><b id="sync-full">${esc(SYNC_TXT[S.sync]()[1])}</b></div>
        <div class="kv"><span>Telegram xotirasi</span><b>${u.percent ? u.percent + '% band' : "1% dan kam band"}</b></div>
        <div class="bar"><i style="width:${Math.max(2, u.percent)}%"></i></div>
        <div class="hint" style="margin-top:6px">300 ta bolaning 2 yillik hisobi taxminan 20% joy oladi.</div>
        <button class="btn secondary" style="margin-top:10px" data-act="pull">🔄 Bulutdan qayta yuklash</button>
      </div>`;
  }

  // ------------------------------------------------------------ tugmalar
  const ACT = {
    gotab: el => switchTab(el.dataset.tab),
    filter: el => { S.filter = S.filter === el.dataset.f ? 'all' : el.dataset.f; render(); },
    floor: el => { S.floor = el.dataset.id === 'all' ? 'all' : +el.dataset.id; render(); },
    floorgo: el => { S.floor = +el.dataset.id; S.filter = 'all'; S.q = ''; switchTab('pay'); },

    open: el => openStudent(+el.dataset.id),
    quickpay: el => payNow(+el.dataset.id, S.st.fee, el),
    pay: el => payNow(+el.dataset.id, +el.dataset.amt, el),
    paycustom: el => {
      const v = $('#cust').value.trim();
      if (!v) { toast('Summani yozing', { error: true }); return; }
      payNow(+el.dataset.id, v, el);
    },
    exempt: el => busy(el, async () => {
      const r = await api('POST', '/exempt', { student_id: +el.dataset.id });
      haptic('success');
      toast(r.exempt ? '💤 Bu hafta ozod qilindi' : '↩️ Ozodlik bekor qilindi');
      await reload();
    }),
    delpay: async el => {
      if (!await confirmBox("Bu to'lovni o'chirasizmi?")) return;
      busy(el, async () => { await api('DELETE', `/payment/${el.dataset.id}`); toast("🗑 To'lov o'chirildi"); await reload(); });
    },
    save: el => busy(el, async () => {
      await api('PATCH', `/student/${el.dataset.id}`, {
        name: $('#e-name').value, room: $('#e-room').value, phone: $('#e-phone').value,
        floor_id: +$('#e-floor').value, opening_debt: $('#e-debt').value,
      });
      haptic('success'); toast('✅ Saqlandi'); await reload();
    }),
    leave: async el => {
      if (!await confirmBox("TTJdan chiqib ketdimi? Keyingi haftadan to'lov hisoblanmaydi, qarzi saqlanadi.")) return;
      busy(el, async () => {
        await api('POST', `/student/${el.dataset.id}/leave`);
        toast("🚶 Ro'yxatdan chiqarildi"); closeSheet(); await reload();
      });
    },
    return: el => busy(el, async () => {
      await api('POST', `/student/${el.dataset.id}/return`); toast('↩️ Qaytib keldi'); await reload();
    }),
    delstudent: async el => {
      if (!await confirmBox("Butunlay o'chirilsinmi? Qaytarib bo'lmaydi.")) return;
      busy(el, async () => { await api('DELETE', `/student/${el.dataset.id}`); toast("🗑 O'chirildi"); closeSheet(); await reload(); });
    },

    cat: el => {
      S.expCat = S.st.categories[+el.dataset.i];
      $$('[data-act="cat"]').forEach(b => b.classList.toggle('sel', b === el));
    },
    addexp: el => {
      if (!S.expCat) { toast("Toifani tanlang (go'sht, non...)", { error: true }); return; }
      busy(el, async () => {
        await api('POST', '/expenses', {
          category: S.expCat, amount: $('#x-amt').value, description: $('#x-desc').value, date: $('#x-date').value,
        });
        haptic('success'); toast('✅ Xarajat yozildi'); S.expCat = null; await renderExp();
      });
    },
    delexp: async el => {
      if (!await confirmBox("Bu xarajatni o'chirasizmi?")) return;
      busy(el, async () => { await api('DELETE', `/expense/${el.dataset.id}`); toast("🗑 O'chirildi"); await renderExp(); });
    },

    repk: el => { S.rep = { k: el.dataset.k, o: 0 }; renderRep(); },
    repo: el => { S.rep.o = Math.min(0, S.rep.o + +el.dataset.d); renderRep(); },
    debtors: () => openDebtors(),
    copyrep: () => copyText(db.reportText(S.rep.k, S.rep.o), '📋 Hisobot'),
    copydebt: () => copyText(db.debtorsText(), '📋 Qarzdorlar'),

    addkids: () => openAddKids(),
    addkidsgo: el => busy(el, async () => {
      const r = await api('POST', '/students', { floor_id: +$('#k-floor').value, text: $('#k-text').value });
      haptic('success');
      let msg = `✅ ${r.floor}: ${r.added.length} ta bola qo'shildi`;
      if (r.bad.length) msg += ` · ${r.bad.length} qator tushunilmadi`;
      if (r.dup.length) msg += ` · ⚠️ takroriy ism: ${r.dup.join(', ')}`;
      toast(msg);
      $('#k-text').value = '';
      await loadState(); render();
    }),
    addfloors: () => openAddFloors(),
    addfloorsgo: el => busy(el, async () => {
      const r = await api('POST', '/floors', { text: $('#f-text').value });
      let msg = r.added.length ? `✅ Qo'shildi: ${r.added.join(', ')}` : '';
      if (r.exists.length) msg += `${msg ? ' · ' : ''}⚠️ Avvaldan bor: ${r.exists.join(', ')}`;
      toast(msg);
      closeSheet(); await loadState(); render();
    }),
    renfloor: el => openRenameFloor(+el.dataset.id),
    renfloorgo: el => busy(el, async () => {
      await api('PATCH', `/floor/${el.dataset.id}`, { name: $('#f-name').value });
      toast('✅ Saqlandi'); closeSheet(); await loadState(); render();
    }),
    delfloor: async el => {
      if (!await confirmBox("Etaj o'chirilsinmi?")) return;
      busy(el, async () => { await api('DELETE', `/floor/${el.dataset.id}`); toast("🗑 O'chirildi"); await loadState(); render(); });
    },

    feewhen: el => {
      S.feeWhen = el.dataset.w;
      $$('[data-act="feewhen"]').forEach(b => b.classList.toggle('sel', b === el));
    },
    setfee: el => busy(el, async () => {
      const r = await api('POST', '/settings/fee', { amount: $('#s-fee').value, when: S.feeWhen });
      haptic('success'); toast(`✅ Yangi summa ${r.from} haftasidan`);
      await loadState(); renderSet();
    }),
    setcash: el => busy(el, async () => {
      await api('POST', '/settings/cash', { amount: $('#s-cash').value });
      haptic('success'); toast('✅ Saqlandi');
    }),
    pull: el => busy(el, () => pullIfChanged(true)),
  };

  document.addEventListener('click', e => {
    const el = e.target.closest('[data-act]');
    if (!el || el.disabled) return;
    e.stopPropagation();
    const fn = ACT[el.dataset.act];
    if (fn) fn(el, e);
  });

  // ------------------------------------------------------------ ishga tushirish
  function outside(html) {
    $('#top-sub').textContent = '';
    $('#tabs').classList.add('hidden');
    view.innerHTML = `<div class="card"><h3>📱 Oshxona hisobi</h3>${html}</div>`;
  }

  function environment() {
    const dev = !inTG && ['localhost', '127.0.0.1'].includes(location.hostname);
    if (dev) {
      $('#dev-banner').classList.remove('hidden');
      return {
        backend: OshStore.memoryBackend({ latency: 250, persist: safeStorage }),
        user: { id: 1, name: 'Sinov' },
      };
    }
    if (!inTG) return null;
    if (!tgAtLeast('6.9') || !tg.CloudStorage) return { old: true };
    const u = tg.initDataUnsafe && tg.initDataUnsafe.user;
    return {
      backend: OshStore.telegramBackend(tg.CloudStorage),
      user: { id: u ? u.id : 0, name: u ? [u.first_name, u.last_name].filter(Boolean).join(' ') : '' },
    };
  }

  async function boot() {
    const env = environment();
    if (!env) {
      outside(`<p class="hint">Bu ilova Telegram ichida ishlaydi.</p>
        <a class="btn" href="${BOT_LINK}">Telegram'da ochish</a>`);
      return;
    }
    if (env.old) {
      outside('<p class="hint">Telegram ilovangiz eski. Uni Play Market yoki App Store\'dan yangilab, qayta oching.</p>');
      return;
    }
    S.user = env.user;
    db = OshLogic.createDb();
    db.setUser(env.user);
    store = OshStore.createStore(env.backend, { kv: safeStorage });
    mirror = OshStore.localMirror(safeStorage, env.user.id || 'anon');
    sync = OshStore.createSync({ store, db, mirror, onStatus: setSync, onConflict });
    try {
      await initialLoad();
    } catch (e) {
      $('#top-sub').textContent = '';
      view.innerHTML = `<div class="card"><h3>⚠️ Ma'lumot yuklanmadi</h3><p class="hint">${esc(e.message)}</p>
        <button class="btn" id="retry">Qayta urinish</button></div>`;
      $('#retry').onclick = () => { view.innerHTML = '<div class="empty">Yuklanmoqda…</div>'; boot(); };
      return;
    }
    db.setOnChange(() => sync.markDirty());
    if (!sync.busy()) setSync('synced');
    await loadState();
    render();

    // eski, uzilib qolgan yozuvlardan qolgan bo'laklarni tinch tozalash
    setTimeout(() => store.serial(() => store.gc()).catch(() => {}), 4000);
    // ilovaga qaytilganda boshqa qurilmadagi o'zgarishlarni olish
    const onBack = () => { pullIfChanged(false).catch(() => {}); };
    if (tgAtLeast('8.0')) try { tg.onEvent('activated', onBack); } catch (e) {}
    document.addEventListener('visibilitychange', () => { if (!document.hidden) onBack(); });
  }

  boot();
})();
