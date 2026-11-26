/* TTJ oshxona hisobi — hisob-kitob mantig'i (serversiz versiya).
 *
 * Server versiyasidagi db.py + webserver.py bilan bir xil natija beradi:
 * tests/crosscheck.py ikkalasini bir xil amallar bilan solishtiradi.
 *
 * Ma'lumot bir necha "oqim" (matn) ko'rinishida saqlanadi (store.js ularni Telegram bulutiga yozadi):
 *   c — asosiy: etajlar, bolalar, haftalik to'lov tarixi, boshlang'ich kassa
 *   p — to'lovlar jurnali, har qator:  id,bola_id,summa,vaqt36   yoki  -id (o'chirilgan)
 *   e — xarajatlar jurnali, har qator: [id,"toifa",summa,"YYYY-MM-DD","izoh"]  yoki  -id
 *   o — ovqat belgilari: har kun bitta qator  kun36:1-mahal:2-mahal  (bolalar to'plami ixcham ko'rinishda)
 *   k — ovqat nazorati: keyin yozilgan va o'chirilgan belgilar (vaqti va qurilmasi bilan)
 * Jurnallarga faqat oxiridan qo'shiladi — bulutga har safar faqat oxirgi bo'lak yoziladi.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.OshLogic = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DAY = 86400000;
  const TZ_MS = 5 * 3600000;               // Toshkent vaqti, UTC+5
  const T_EPOCH = Date.UTC(2024, 0, 1);    // ixcham vaqt yozuvi boshlanishi
  const DEFAULT_FEE = 90000;
  const FIRST_WEEK = '2000-01-03';         // dushanba: "boshidan beri shu summa"
  const MONTHS = ['', 'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
    'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'];
  const CATEGORIES = [
    "🥩 Go'sht", '🍚 Guruch, un, don', "🛢 Yog'", '🥕 Sabzavot, meva', '🍞 Non',
    '🧂 Ziravor, tuz, shakar', '🥛 Sut mahsulotlari', '🥚 Tuxum, tovuq',
    "🔥 Gaz, ko'mir, o'tin", "🧽 Xo'jalik buyumlari", "🚕 Yo'l kira", '📦 Boshqa',
  ];
  const ICON = { ok: '✅', part: '🟡', bad: '❌', exempt: '💤' };
  const WEEKDAYS = ['dushanba', 'seshanba', 'chorshanba', 'payshanba', 'juma', 'shanba', 'yakshanba'];
  const WD_SHORT = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'];
  const MEALS_PER_DAY = 2;
  const MEAL_BACK_DAYS = 30;               // necha kun oldingi ovqatni keyin yozish mumkin

  class ApiError extends Error {
    constructor(message, status = 400) { super(message); this.status = status; }
  }

  // ------------------------------------------------------------ vaqt
  let clock = () => Date.now();
  const pad = n => String(n).padStart(2, '0');
  const wallDate = (ms = clock()) => new Date(ms + TZ_MS); // UTC getterlari Toshkent vaqtini beradi
  const fmtWall = d => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} `
    + `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
  const nowStr = () => fmtWall(wallDate());
  const today = () => nowStr().slice(0, 10);
  const isoDay = iso => Math.round(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / DAY);
  const dayIso = n => new Date(n * DAY).toISOString().slice(0, 10);
  const addDays = (iso, n) => dayIso(isoDay(iso) + n);
  const weekStartDay = n => n - ((((n + 3) % 7) + 7) % 7); // 1970-01-01 — payshanba
  const weekStart = iso => dayIso(weekStartDay(isoDay(iso || today())));

  function weekLabel(ws) {
    const we = addDays(ws, 6);
    const m1 = +ws.slice(5, 7), d1 = +ws.slice(8, 10), m2 = +we.slice(5, 7), d2 = +we.slice(8, 10);
    return m1 === m2 ? `${d1}–${d2} ${MONTHS[m1]}` : `${d1} ${MONTHS[m1]} – ${d2} ${MONTHS[m2]}`;
  }
  const monthStart = iso => iso.slice(0, 8) + '01';
  function addMonths(iso, n) {
    const m = +iso.slice(5, 7) - 1 + n;
    return `${+iso.slice(0, 4) + Math.floor(m / 12)}-${pad((((m % 12) + 12) % 12) + 1)}-01`;
  }
  function monthLabel(iso) {
    const m = MONTHS[+iso.slice(5, 7)];
    return m[0].toUpperCase() + m.slice(1) + ' ' + +iso.slice(0, 4);
  }
  function validIso(s) {
    return /^\d{4}-\d{2}-\d{2}$/.test(s) && dayIso(isoDay(s)) === s;
  }
  const weekdayOf = n => (((n + 3) % 7) + 7) % 7;   // 0 — dushanba
  /** '2026-11-26' -> '26-noyabr, payshanba' */
  const dayLabel = iso => `${+iso.slice(8, 10)}-${MONTHS[+iso.slice(5, 7)]}, ${WEEKDAYS[weekdayOf(isoDay(iso))]}`;
  const shortDate = iso => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

  /* Bolalar to'plami -> ixcham matn: har belgi 6 ta bolani bildiradi (bit), boshida nechanchi guruhdan boshlangani.
   * 300 bola ≈ 55 belgi, shuning uchun 2 yillik ovqat hisobi ham Telegram xotirasining oz qismini oladi. */
  const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  function packSet(set) {
    if (!set.size) return '';
    const ids = [...set].sort((a, b) => a - b);
    const start = Math.floor(ids[0] / 6);
    const vals = new Array(Math.floor(ids[ids.length - 1] / 6) - start + 1).fill(0);
    for (const id of ids) vals[Math.floor(id / 6) - start] |= 1 << (id % 6);
    return start.toString(36) + '.' + vals.map(v => B64[v]).join('');
  }
  function unpackSet(str) {
    const out = new Set();
    if (!str) return out;
    const [st, body = ''] = str.split('.');
    const start = parseInt(st, 36);
    for (let i = 0; i < body.length; i++) {
      const v = B64.indexOf(body[i]);
      for (let b = 0; b < 6; b++) if (v & (1 << b)) out.add((start + i) * 6 + b);
    }
    return out;
  }
  function fmtDt(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):\d{2}$/.exec(s || '');
    return m ? `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}` : (s || '');
  }
  function fmtDate(s) {
    const d = String(s || '').slice(0, 10);
    return validIso(d) ? `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}` : (s || '');
  }
  function packTime(s) {
    const ms = Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10),
      +s.slice(11, 13), +s.slice(14, 16), +s.slice(17, 19));
    return Math.round((ms - T_EPOCH) / 1000).toString(36);
  }
  const unpackTime = t => fmtWall(new Date(T_EPOCH + parseInt(t, 36) * 1000));

  // ------------------------------------------------------------ matn va pul
  const num = n => (n < 0 ? '-' : '') + String(Math.abs(Math.trunc(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const money = n => num(n) + " so'm";
  const cpLen = s => Array.from(s).length;
  const cpSlice = (s, n) => Array.from(s).slice(0, n).join('');
  const collapse = s => String(s).split(/\s+/).filter(Boolean).join(' ');
  const LINE_BREAKS = new RegExp('\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]');
  const splitLines = s => String(s).split(LINE_BREAKS);
  const lc = s => String(s || '').toLowerCase();
  const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

  function pyRound(x) {          // Python round(): .5 juftga yaxlitlanadi
    const r = Math.round(x);
    return Math.abs(x % 1) === 0.5 ? 2 * Math.round(x / 2) : r;
  }

  const AMOUNT_RE = /^([\d\s.,]+?)\s*(k|к|ming|минг|тыс|mln|million|млн)?\.?$/u;
  /** '90000', '90 000', '90.000', '90k', '90 ming', '1.5 mln' -> son. Noto'g'ri bo'lsa null. */
  function parseAmount(text) {
    let t = String(text || '').toLowerCase().replace(/ /g, ' ');
    for (const w of ["so'm", 'so‘m', 'soʻm', 'сўм', 'сум', 'som', 'sum']) t = t.split(w).join('');
    t = t.trim();
    const m = AMOUNT_RE.exec(t);
    if (!m) return null;
    let digits = m[1].replace(/ /g, '');
    let n;
    if (m[2]) {
      const mult = ['mln', 'million', 'млн'].includes(m[2]) ? 1000000 : 1000;
      const f = Number(digits.replace(/,/g, '.'));
      if (!digits || Number.isNaN(f)) return null;
      n = pyRound(f * mult);
    } else {
      digits = digits.replace(/[,.]/g, '');
      if (!/^\d+$/.test(digits)) return null;
      n = parseInt(digits, 10);
    }
    return n > 0 && n <= 1000000000 ? n : null;
  }

  function amountArg(value, allowZero = false, allowNegative = false) {
    let text = String(value === undefined || value === null ? '' : value).trim();
    const negative = allowNegative && text.startsWith('-');
    if (negative) text = text.replace(/^-+/, '').trim();
    if (allowZero && (text === '0' || text === '')) return 0;
    const n = parseAmount(text);
    if (n === null) throw new ApiError('Summani tushunmadim. Masalan: 90000');
    return negative ? -n : n;
  }

  function toInt(v, what = 'id') {
    if (typeof v === 'number' && Number.isFinite(v)) return Math.trunc(v);
    if (typeof v === 'boolean') return v ? 1 : 0;
    if (typeof v === 'string' && /^\s*[+-]?\d+\s*$/.test(v)) return parseInt(v, 10);
    throw new ApiError(`Noto'g'ri ${what}`);
  }

  function cleanRoom(room) {
    if (!room) return null;
    return cpSlice(String(room).trim().replace(/[-\s]*xona$/i, '').trim(), 16) || null;
  }

  /** '1. Aliyev Vali, 305-xona' -> ['Aliyev Vali', '305']. Ism bo'lmasa null. */
  function parseStudentLine(raw) {
    const line = String(raw).replace(/^\s*(\d+[.)]|[•\-–—*])\s*/u, '').trim();
    if (!line) return null;
    let name = line, room = null;
    const i = line.lastIndexOf(',');
    if (i >= 0) {
      name = line.slice(0, i).trim();
      room = cleanRoom(line.slice(i + 1).trim());
    }
    name = collapse(name);
    const n = cpLen(name);
    if (n < 2 || n > 64 || !/\p{L}/u.test(name)) return null;
    return [name, room];
  }

  function floorName(raw) {
    const name = cpSlice(collapse(raw), 32);
    return /^\d+$/.test(name) ? `${name}-etaj` : name;
  }
  function floorSortKey(name) {
    const m = /\d+/.exec(name);
    return m ? parseInt(m[0], 10) : 999;
  }

  function statusOf(b, fee) {
    if (b.debt <= 0) return b.exempt_now ? 'exempt' : 'ok';
    return b.debt < fee ? 'part' : 'bad';
  }

  // ------------------------------------------------------------ baza
  /** onePaymentPerWeek: bir bolaga bir haftada bitta to'lov (server versiyasida bu qoida yo'q edi). */
  function createDb({ onePaymentPerWeek = true } = {}) {
    let D;
    let onChange = () => {};
    let user = { id: 0, name: '' };
    let device = '';   // shu qurilma belgisi: platforma harfi + tasodifiy kod (masalan "a3f9k")

    function empty() {
      return {
        cash: 0, fees: [[FIRST_WEEK, DEFAULT_FEE]], floors: [], students: [], seqF: 0, seqS: 0,
        pay: new Map(), exp: new Map(), payLog: [], expLog: [], maxP: 0, maxE: 0, events: [],
        meals: new Map(),     // kun raqami -> [null, Set(1-mahal bolalari), Set(2-mahal bolalari)]
        mealLine: new Map(),  // kun -> saqlanadigan qator (o'zgarmagan kunlar qayta hisoblanmaydi)
        late: new Map(),      // "kun.mahal.bola" -> {at, dev}: keyin yozilgan belgilar
        mealLog: [],          // k oqimi qatorlari
      };
    }
    D = empty();

    const lines = s => (s ? s.split('\n') : []);

    function load(st) {
      const d = empty();
      if (st && st.c) {
        const o = JSON.parse(st.c);
        if (o.v !== 1 && o.v !== 2) throw new Error("Ma'lumot yangi versiyada saqlangan — ilovani yangilang");
        d.cash = o.cash || 0;
        d.fees = o.fees;
        [d.seqF, d.seqS] = o.seq;
        d.floors = o.fl.map(([id, name, sort]) => ({ id, name, sort }));
        d.students = o.st.map(([id, name, fid, room, phone, jw, lw, act, od, ex]) =>
          ({ id, name, fid, room, phone, jw, lw, act: !!act, od, ex }));
      }
      for (const line of lines(st && st.p)) { d.payLog.push(line); applyPay(d, line); }
      for (const line of lines(st && st.e)) { d.expLog.push(line); applyExp(d, line); }
      for (const line of lines(st && st.o)) {
        const [d36, a, b] = line.split(':');
        const day = parseInt(d36, 36);
        if (day > 0) d.meals.set(day, [null, unpackSet(a), unpackSet(b)]);
      }
      for (const line of lines(st && st.k)) { d.mealLog.push(line); applyMealAudit(d, line); }
      D = d;
    }

    /* Ovqat nazorati (k oqimi), har qator bitta voqea:
     *   +bola36,kun36,mahal,vaqt36[,qurilma]   — o'tgan kun uchun keyin yozildi
     *   -bola36,kun36,mahal,vaqt36[,qurilma]   — belgi o'chirildi
     * Belgilarning o'zi o oqimida; bu yerda faqat "kim, qachon, qaysi qurilmadan" saqlanadi. */
    function applyMealAudit(d, line) {
      const [sid36, d36, m, t, dev = ''] = line.slice(1).split(',');
      const sid = parseInt(sid36, 36), day = parseInt(d36, 36), meal = +m;
      if (!(sid > 0 && day > 0 && (meal === 1 || meal === 2) && t)) return;
      const key = `${day}.${meal}.${sid}`;
      const ev = { k: line[0] === '-' ? 'mdel' : 'mlate', s: 'o', n: d.mealLog.length, sid, day, meal, at: unpackTime(t), dev };
      if (ev.k === 'mdel') d.late.delete(key);
      else d.late.set(key, { at: ev.at, dev });
      d.events.push(ev);
    }

    /* To'lovlar jurnali — har qator bitta voqea (o'chirilgan/o'zgartirilgani ham saqlanib qoladi):
     *   id,bola,summa,vaqt[,qurilma]     — yangi to'lov
     *   ~id,yangi_summa,vaqt[,qurilma]   — summa o'zgartirildi
     *   -id[,vaqt[,qurilma]]             — o'chirildi
     * Yuklashda ham, yangi amalda ham shu funksiya ishlaydi — natija doim bir xil. */
    function applyPay(d, line) {
      const f = line.split(',');
      if (line[0] === '-' || line[0] === '~') {
        const id = +f[0].slice(1);
        const p = d.pay.get(id);
        if (!p) return;
        if (line[0] === '-') {
          d.pay.delete(id);
          d.events.push({ k: 'pdel', s: 'p', n: d.payLog.length, id, sid: p.sid, amt: p.amt, pat: p.at, at: f[1] ? unpackTime(f[1]) : null, dev: f[2] || '' });
        } else {
          const ev = { k: 'pedit', s: 'p', n: d.payLog.length, id, sid: p.sid, amt: +f[1], old: p.amt, pat: p.at, at: unpackTime(f[2]), dev: f[3] || '' };
          d.events.push(ev);
          p.edits.push(ev);
          p.amt = ev.amt;
        }
        return;
      }
      const p = { id: +f[0], sid: +f[1], amt: +f[2], at: unpackTime(f[3]), dev: f[4] || '', edits: [] };
      d.pay.set(p.id, p);
      d.events.push({ k: 'padd', s: 'p', n: d.payLog.length, id: p.id, sid: p.sid, amt: p.amt, at: p.at, dev: p.dev });
      if (p.id > d.maxP) d.maxP = p.id;
    }

    /* Xarajatlar jurnali: [id,"toifa",summa,"sana","izoh",vaqt,qurilma]  yoki  -id[,vaqt[,qurilma]] */
    function applyExp(d, line) {
      if (line[0] === '-') {
        const f = line.split(',');
        const id = +f[0].slice(1);
        const e = d.exp.get(id);
        if (!e) return;
        d.exp.delete(id);
        d.events.push({ k: 'edel', s: 'e', n: d.expLog.length, id, cat: e.cat, amt: e.amt, spent: e.spent, desc: e.desc,
          at: f[1] ? unpackTime(f[1]) : null, dev: f[2] || '' });
        return;
      }
      const [id, cat, amt, spent, desc, t, dev] = JSON.parse(line);
      d.exp.set(id, { id, cat, amt, spent, desc });
      d.events.push({ k: 'eadd', s: 'e', n: d.expLog.length, id, cat, amt, spent, desc, at: t ? unpackTime(t) : null, dev: dev || '' });
      if (id > d.maxE) d.maxE = id;
    }

    const devTail = () => (device ? ',' + device : '');
    function logPay(line) { D.payLog.push(line); applyPay(D, line); }
    function logExp(line) { D.expLog.push(line); applyExp(D, line); }
    function logMealAudit(line) { D.mealLog.push(line); applyMealAudit(D, line); }

    function mealsStream() {
      const out = [];
      for (const day of [...D.meals.keys()].sort((a, b) => a - b)) {
        let line = D.mealLine.get(day);
        if (line === undefined) {
          const c = D.meals.get(day);
          line = c[1].size || c[2].size ? `${day.toString(36)}:${packSet(c[1])}:${packSet(c[2])}` : '';
          D.mealLine.set(day, line);
        }
        if (line) out.push(line);
      }
      return out.join('\n');
    }

    function streams() {
      return {
        c: JSON.stringify({
          v: 2, cash: D.cash, fees: D.fees,
          fl: D.floors.map(f => [f.id, f.name, f.sort]),
          seq: [D.seqF, D.seqS],
          st: D.students.map(s => [s.id, s.name, s.fid, s.room, s.phone, s.jw, s.lw, s.act ? 1 : 0, s.od, s.ex]),
        }),
        p: D.payLog.join('\n'),
        e: D.expLog.join('\n'),
        o: mealsStream(),
        k: D.mealLog.join('\n'),
      };
    }

    // ---------- yordamchilar ----------
    function feeFor(w) {
      let v = DEFAULT_FEE;
      for (const [k, a] of D.fees) { if (k <= w) v = a; else break; }
      return v;
    }
    const currentFee = () => feeFor(weekStart());
    const nextFee = () => feeFor(addDays(weekStart(), 7));
    const floorsMap = () => new Map(D.floors.map(f => [f.id, f]));
    const floorById = id => D.floors.find(f => f.id === id) || null;
    const floorOrder = (a, b) => a.sort - b.sort || cmp(lc(a.name), lc(b.name)) || a.id - b.id;

    function studentOr404(id) {
      const s = D.students.find(x => x.id === id);
      if (!s) throw new ApiError('Bola topilmadi', 404);
      return s;
    }

    function listStudents(floorId = null, active = true) {
      const fl = floorsMap();
      return D.students
        .filter(s => (active === null || s.act === active) && (floorId === null || s.fid === floorId))
        .sort((a, b) => floorOrder(fl.get(a.fid), fl.get(b.fid)) || cmp(lc(a.name), lc(b.name)) || a.id - b.id);
    }

    function listFloors() {
      return D.floors.slice().sort(floorOrder).map(f => {
        let cnt = 0, total = 0;
        for (const s of D.students) if (s.fid === f.id) { total++; if (s.act) cnt++; }
        return { id: f.id, name: f.name, cnt, total };
      });
    }

    /** Har bola uchun: kutilgan, to'lagan, shu hafta to'lagan, qarz. */
    function balances() {
      const cur = weekStart();
      const curDay = isoDay(cur);
      const paid = new Map(), paidWeek = new Map();
      for (const p of D.pay.values()) {
        paid.set(p.sid, (paid.get(p.sid) || 0) + p.amt);
        if (p.at >= cur) paidWeek.set(p.sid, (paidWeek.get(p.sid) || 0) + p.amt);
      }
      const memo = new Map();
      const out = new Map();
      for (const s of D.students) {
        let end = curDay;
        if (s.lw) end = Math.min(end, isoDay(s.lw));
        let expected = s.od || 0;
        const skip = new Set(s.ex.map(isoDay));
        for (let w = isoDay(s.jw); w <= end; w += 7) {
          if (skip.has(w)) continue;
          if (!memo.has(w)) memo.set(w, feeFor(dayIso(w)));
          expected += memo.get(w);
        }
        const pd = paid.get(s.id) || 0;
        out.set(s.id, {
          expected, paid: pd, paid_week: paidWeek.get(s.id) || 0,
          exempt_now: skip.has(curDay), debt: expected - pd,
        });
      }
      return out;
    }

    /** Har bola uchun shu haftadagi oxirgi to'lov (haftada bitta to'lov qoidasi uchun). */
    function weekPayments() {
      const ws = weekStart();
      const out = new Map();
      for (const p of D.pay.values()) {
        if (p.at < ws) continue;
        const cur = out.get(p.sid);
        if (!cur || p.at > cur.at || (p.at === cur.at && p.id > cur.id)) out.set(p.sid, p);
      }
      return out;
    }
    const payBrief = p => (p ? { id: p.id, amount: p.amt, at: fmtDt(p.at), dev: p.dev, edited: p.edits.length > 0 } : null);

    function studentJson(s, b, fee, fl, wp) {
      return {
        id: s.id, name: s.name, floor_id: s.fid, floor: fl.get(s.fid).name,
        room: s.room, phone: s.phone, active: s.act,
        debt: b.debt, paid: b.paid, paid_week: b.paid_week, exempt: b.exempt_now,
        status: s.act ? statusOf(b, fee) : 'left', opening_debt: s.od,
        week_pay: payBrief(wp && wp.get(s.id)),
      };
    }

    function statusCounts(bals = balances(), fee = currentFee()) {
      const c = { ok: 0, part: 0, bad: 0, exempt: 0, debt: 0, total: 0 };
      for (const s of listStudents()) {
        const b = bals.get(s.id);
        c[statusOf(b, fee)] += 1;
        c.debt += Math.max(b.debt, 0);
        c.total += 1;
      }
      return c;
    }

    const sum = (arr, f) => arr.reduce((a, x) => a + f(x), 0);
    const totalIncome = () => sum([...D.pay.values()], p => p.amt);
    const totalExpense = () => sum([...D.exp.values()], e => e.amt);

    function kassa() {
      const bals = balances();
      const opening = D.cash, inc = totalIncome(), exp = totalExpense();
      let debt = 0, prepaid = 0, debtors = 0;
      for (const s of D.students) {
        const d = bals.get(s.id).debt;
        if (d > 0) { debt += d; debtors++; } else prepaid += -d;
      }
      return { opening, income: inc, expense: exp, balance: opening + inc - exp, debt, prepaid, debtors };
    }

    const paymentsIn = (d1, d2) => [...D.pay.values()].filter(p => p.at >= d1 && p.at < d2);
    const expensesIn = (d1, d2) => [...D.exp.values()].filter(e => e.spent >= d1 && e.spent < d2);

    // ---------- holat ----------
    function getState() {
      const fee = currentFee();
      const bals = balances();
      const fl = floorsMap();
      const wp = weekPayments();
      return {
        me: { id: user.id, name: user.name },
        week: weekLabel(weekStart()),
        fee,
        next_fee: nextFee(),
        floors: listFloors(),
        students: listStudents(null, null).map(s => studentJson(s, bals.get(s.id), fee, fl, wp)),
        categories: CATEGORIES.slice(),
        counts: statusCounts(bals, fee),
      };
    }

    // ---------- bolalar va to'lovlar ----------
    function getStudent(sidRaw) {
      const s = studentOr404(toInt(sidRaw));
      const data = studentJson(s, balances().get(s.id), currentFee(), floorsMap(), weekPayments());
      data.joined = weekLabel(s.jw);
      data.left = s.lw ? weekLabel(s.lw) : null;
      const pays = [...D.pay.values()].filter(p => p.sid === s.id)
        .sort((a, b) => cmp(b.at, a.at) || b.id - a.id);
      data.payments = pays.slice(0, 50).map(p => ({
        id: p.id, amount: p.amt, at: fmtDt(p.at), note: null, dev: p.dev,
        edits: p.edits.map(e => ({ old: e.old, amount: e.amt, at: fmtDt(e.at), dev: e.dev })),
      }));
      data.removed = D.events.filter(e => e.k === 'pdel' && e.sid === s.id).reverse().slice(0, 20)
        .map(e => ({ amount: e.amt, paid_at: fmtDt(e.pat), at: e.at ? fmtDt(e.at) : '', dev: e.dev }));
      data.exemptions = s.ex.slice().sort().map(weekLabel).slice(-10);
      data.meals = studentMeals(s);
      data.can_delete = pays.length === 0 && !hasAnyMeal(s.id);
      return data;
    }

    // ---------- ovqat: kuniga ikki mahal, "+" belgisi ----------
    const hasMeal = (day, meal, sid) => { const c = D.meals.get(day); return !!(c && c[meal].has(sid)); };
    function hasAnyMeal(sid) {
      for (const c of D.meals.values()) if (c[1].has(sid) || c[2].has(sid)) return true;
      return false;
    }
    function mealsIn(day1, day2, sid = null) {   // [day1, day2) oralig'idagi belgilar soni
      let m1 = 0, m2 = 0;
      for (const [day, c] of D.meals) {
        if (day < day1 || day >= day2) continue;
        if (sid === null) { m1 += c[1].size; m2 += c[2].size; }
        else { if (c[1].has(sid)) m1++; if (c[2].has(sid)) m2++; }
      }
      return { m1, m2, total: m1 + m2 };
    }

    function studentMeals(s) {
      const t = today(), tday = isoDay(t), ws = isoDay(weekStart());
      const week = [];
      for (let i = 0; i < 7; i++) {
        const n = ws + i, iso = dayIso(n);
        week.push({
          date: iso, d: +iso.slice(8, 10), wd: WD_SHORT[i], today: n === tday,
          // '' — yo'q, 'on' — o'z vaqtida, 'late' — keyin yozilgan; kelajakdagi kun — null
          cells: n > tday ? null : [1, 2].map(m => (!hasMeal(n, m, s.id) ? '' : D.late.has(`${n}.${m}.${s.id}`) ? 'late' : 'on')),
        });
      }
      const log = D.events.filter(e => e.s === 'o' && e.sid === s.id).slice(-10).reverse()
        .map(e => ({ k: e.k, date: shortDate(dayIso(e.day)), meal: e.meal, at: fmtDt(e.at), dev: e.dev }));
      return {
        week, week_count: mealsIn(ws, tday + 1, s.id).total,
        month_count: mealsIn(isoDay(monthStart(t)), tday + 1, s.id).total, log,
      };
    }

    function mealArgs(b) {
      const s = studentOr404(toInt(b.student_id));
      const t = today();
      const iso = b.date ? String(b.date) : t;
      if (!validIso(iso)) throw new ApiError("Sana noto'g'ri");
      if (iso > t) throw new ApiError("Hali kelmagan kunga yozib bo'lmaydi");
      if (iso < addDays(t, -MEAL_BACK_DAYS)) throw new ApiError(`${MEAL_BACK_DAYS} kundan eski kunni o'zgartirib bo'lmaydi`);
      const meal = toInt(b.meal, 'mahal');
      if (meal < 1 || meal > MEALS_PER_DAY) throw new ApiError("Mahal 1 yoki 2 bo'lishi kerak");
      return { s, iso, day: isoDay(iso), meal, late: iso !== t };
    }
    const auditLine = (sign, a) => `${sign}${a.s.id.toString(36)},${a.day.toString(36)},${a.meal},${packTime(nowStr())}${devTail()}`;

    /** Ovqat berildi: bolaga shu kun shu mahal "+" qo'yish. Bir kunda ikki mahal — ortiq emas. */
    function addMeal(b) {
      const a = mealArgs(b);
      if (!a.s.act) throw new ApiError(`${a.s.name} chiqib ketgan. Avval kartochkasida «Qaytib keldi» ni bosing.`);
      if (hasMeal(a.day, a.meal, a.s.id)) {
        throw new ApiError(`${a.s.name}: ${shortDate(a.iso)} ${a.meal}-mahal allaqachon yozilgan. Kuniga ${MEALS_PER_DAY} mahal.`, 409);
      }
      let c = D.meals.get(a.day);
      if (!c) D.meals.set(a.day, c = [null, new Set(), new Set()]);
      c[a.meal].add(a.s.id);
      D.mealLine.delete(a.day);
      if (a.late) logMealAudit(auditLine('+', a));   // o'tgan kunga keyin yozildi — vaqti va qurilmasi saqlanadi
      return { ok: true, name: a.s.name, date: a.iso, meal: a.meal, late: a.late, day_count: (c[1].has(a.s.id) ? 1 : 0) + (c[2].has(a.s.id) ? 1 : 0) };
    }

    function removeMeal(sidRaw, iso, mealRaw) {
      const a = mealArgs({ student_id: sidRaw, date: iso, meal: mealRaw });
      if (!hasMeal(a.day, a.meal, a.s.id)) throw new ApiError('Bu belgi topilmadi', 404);
      D.meals.get(a.day)[a.meal].delete(a.s.id);
      D.mealLine.delete(a.day);
      logMealAudit(auditLine('-', a));
      return { ok: true, name: a.s.name, date: a.iso, meal: a.meal };
    }

    /** Bir kunlik ovqat ro'yxati: kimga qaysi mahal berildi. */
    function getMeals(q) {
      const t = today(), min = addDays(t, -MEAL_BACK_DAYS);
      let iso = q.d ? String(q.d) : t;
      if (!validIso(iso) || iso > t) iso = t;
      if (iso < min) iso = min;
      const day = isoDay(iso);
      const c = D.meals.get(day);
      const marks = {};
      let m1 = 0, m2 = 0, active = 0;
      for (const s of D.students) {
        if (s.act) active++;
        const mask = (c && c[1].has(s.id) ? 1 : 0) | (c && c[2].has(s.id) ? 2 : 0);
        if (!mask) continue;
        marks[s.id] = mask;
        if (mask & 1) m1++;
        if (mask & 2) m2++;
      }
      return {
        date: iso, label: dayLabel(iso), short: shortDate(iso),
        rel: iso === t ? 'Bugun' : iso === addDays(t, -1) ? 'Kecha' : '',
        prev: iso > min ? addDays(iso, -1) : null, next: iso < t ? addDays(iso, 1) : null,
        m1, m2, active, marks,
      };
    }

    function pay(b) {
      const s = studentOr404(toInt(b.student_id));
      const amount = amountArg(b.amount);
      if (onePaymentPerWeek) {
        const prev = weekPayments().get(s.id);
        if (prev) {
          throw new ApiError(`${s.name} bu hafta to'lagan: ${num(prev.amt)} so'm (${fmtDt(prev.at)}). `
            + "Bir haftada bitta to'lov. Xato bo'lsa — o'sha to'lovni o'zgartiring.", 409);
        }
      }
      const since = fmtWall(wallDate(clock() - 4000));
      for (const p of D.pay.values()) {
        if (p.sid === s.id && p.amt === amount && p.at >= since) throw new ApiError("Bu to'lov hozirgina yozildi", 409);
      }
      const id = D.maxP + 1;
      const at = nowStr();
      logPay(`${id},${s.id},${amount},${packTime(at)}${devTail()}`);
      return { payment_id: id, name: s.name, amount, debt: balances().get(s.id).debt, at: fmtDt(at) };
    }

    function editPayment(pidRaw, b) {
      const p = D.pay.get(toInt(pidRaw));
      if (!p) throw new ApiError("To'lov topilmadi", 404);
      const s = studentOr404(p.sid);
      const amount = amountArg(b.amount);
      if (amount === p.amt) throw new ApiError("Summa o'zgarmadi");
      const old = p.amt;
      logPay(`~${p.id},${amount},${packTime(nowStr())}${devTail()}`);
      return { ok: true, name: s.name, old, amount, debt: balances().get(s.id).debt };
    }

    function deletePayment(pidRaw) {
      const p = D.pay.get(toInt(pidRaw));
      if (!p) throw new ApiError("To'lov topilmadi", 404);
      const s = studentOr404(p.sid);
      const amount = p.amt;
      logPay(`-${p.id},${packTime(nowStr())}${devTail()}`);
      return { ok: true, name: s.name, amount };
    }

    /** O'zgarishlar tarixi: to'lov va xarajatlar — qo'shilgan, o'zgartirilgan, o'chirilgan. Yangisi birinchi. */
    function getJournal(q) {
      const only = q.only === 'fix';
      const limit = Math.min(Math.max(toInt(q.limit === undefined ? '100' : q.limit, 'son'), 1), 500);
      const names = new Map(D.students.map(s => [s.id, s.name]));
      const items = [];
      // vaqt bo'yicha (yangisi birinchi); vaqti yo'q eski yozuvlar — to'lov/xarajat sanasi bo'yicha
      const when = e => e.at || e.pat || (e.spent ? e.spent + ' 00:00:00' : '');
      const sorted = D.events.slice().sort((a, b) => cmp(when(b), when(a)) || cmp(a.s, b.s) || b.n - a.n);
      for (const e of sorted) {
        if (items.length >= limit) break;
        if (only && (e.k === 'padd' || e.k === 'eadd' || e.k === 'mlate')) continue;
        const it = { k: e.k, at: e.at ? fmtDt(e.at) : '', amount: e.amt, dev: e.dev };
        if (e.s === 'o') {
          it.name = names.get(e.sid) || '—';
          it.date = shortDate(dayIso(e.day));
          it.meal = e.meal;
        } else if (e.k[0] === 'p') {
          it.name = names.get(e.sid) || '—';
          if (e.k !== 'padd') it.paid_at = fmtDt(e.pat);
          if (e.k === 'pedit') it.old = e.old;
        } else {
          it.name = e.cat;
          it.desc = e.desc;
          it.spent = fmtDate(e.spent);
        }
        items.push(it);
      }
      const fixes = D.events.filter(e => e.k === 'pedit' || e.k === 'pdel' || e.k === 'edel' || e.k === 'mdel').length;
      return { items, total: only ? fixes : D.events.length, fixes };
    }

    function toggleExempt(b) {
      const s = studentOr404(toInt(b.student_id));
      const cur = weekStart();
      const i = s.ex.indexOf(cur);
      if (i >= 0) { s.ex.splice(i, 1); return { exempt: false }; }
      s.ex.push(cur);
      s.ex.sort();
      return { exempt: true };
    }

    function sameNameExists(fid, name) {
      return listStudents(fid).some(s => lc(s.name) === lc(name));
    }

    function addStudents(b) {
      const f = floorById(toInt(b.floor_id, 'etaj'));
      if (!f) throw new ApiError('Etaj topilmadi', 404);
      const added = [], bad = [], dup = [];
      for (const raw of splitLines(b.text === undefined ? '' : b.text)) {
        if (!raw.trim()) continue;
        const parsed = parseStudentLine(raw);
        if (!parsed) { bad.push(cpSlice(raw.trim(), 40)); continue; }
        const [name, room] = parsed;
        if (sameNameExists(f.id, name)) dup.push(name);
        D.students.push({
          id: ++D.seqS, name, fid: f.id, room, phone: null, jw: weekStart(), lw: null, act: true, od: 0, ex: [],
        });
        added.push(name);
      }
      if (!added.length) throw new ApiError('Ism topilmadi. Har bir qatorga bitta ism-familiya yozing.');
      return { added, bad, dup, floor: f.name };
    }

    function updateStudent(sidRaw, b) {
      const s = studentOr404(toInt(sidRaw));
      const f = {};
      if ('name' in b) {
        const name = collapse(b.name);
        if (cpLen(name) < 2 || cpLen(name) > 64) throw new ApiError("Ism 2–64 belgi bo'lishi kerak");
        f.name = name;
      }
      if ('room' in b) f.room = cleanRoom(String(b.room || ''));
      if ('phone' in b) f.phone = cpSlice(String(b.phone || '').trim(), 32) || null;
      if ('floor_id' in b) {
        const fl = floorById(toInt(b.floor_id, 'etaj'));
        if (!fl) throw new ApiError('Etaj topilmadi', 404);
        f.fid = fl.id;
      }
      if ('opening_debt' in b) f.od = amountArg(b.opening_debt, true, true);
      Object.assign(s, f);
      return { ok: true };
    }

    function leave(sidRaw) {
      const s = studentOr404(toInt(sidRaw));
      s.act = false;
      s.lw = weekStart();
      return { ok: true };
    }

    function comeBack(sidRaw) {
      const s = studentOr404(toInt(sidRaw));
      const cur = isoDay(weekStart());
      if (s.lw) {   // yo'q bo'lgan haftalar ozod hisoblanadi
        for (let w = isoDay(s.lw) + 7; w < cur; w += 7) {
          const iso = dayIso(w);
          if (!s.ex.includes(iso)) s.ex.push(iso);
        }
        s.ex.sort();
      }
      s.act = true;
      s.lw = null;
      return { ok: true };
    }

    function deleteStudent(sidRaw) {
      const s = studentOr404(toInt(sidRaw));
      if ([...D.pay.values()].some(p => p.sid === s.id)) {
        throw new ApiError("Bu bolaning to'lovlari bor — o'chirib bo'lmaydi. «Chiqib ketdi» qiling.");
      }
      if (hasAnyMeal(s.id)) throw new ApiError("Bu bolaga ovqat yozilgan — o'chirib bo'lmaydi. «Chiqib ketdi» qiling.");
      D.students = D.students.filter(x => x !== s);
      return { ok: true };
    }

    // ---------- etajlar ----------
    const floorNameTaken = (name, exceptId) => D.floors.some(f => f.id !== exceptId && lc(f.name) === lc(name));

    function addFloors(b) {
      const added = [], exists = [];
      for (const raw of splitLines(b.text === undefined ? '' : b.text)) {
        const name = floorName(raw);
        if (!name) continue;
        if (floorNameTaken(name)) { exists.push(name); continue; }
        D.floors.push({ id: ++D.seqF, name, sort: floorSortKey(name) });
        added.push(name);
      }
      if (!added.length && !exists.length) throw new ApiError('Etaj nomini yozing');
      return { added, exists };
    }

    function renameFloor(fidRaw, b) {
      const f = floorById(toInt(fidRaw));
      if (!f) throw new ApiError('Etaj topilmadi', 404);
      const name = floorName(b.name === undefined ? '' : b.name);
      if (!name) throw new ApiError("Nom bo'sh bo'lmasin");
      if (floorNameTaken(name, f.id)) throw new ApiError('Bunday nomli etaj bor');
      f.name = name;
      f.sort = floorSortKey(name);
      return { ok: true };
    }

    function deleteFloor(fidRaw) {
      const f = floorById(toInt(fidRaw));
      if (!f) throw new ApiError('Etaj topilmadi', 404);
      if (D.students.some(s => s.fid === f.id)) {
        throw new ApiError("Bu etajda bolalar bor (yoki bo'lgan). Avval ularni boshqa etajga ko'chiring.");
      }
      D.floors = D.floors.filter(x => x !== f);
      return { ok: true };
    }

    // ---------- xarajatlar ----------
    function getExpenses() {
      const ws = weekStart(), ms = monthStart(today());
      const items = [...D.exp.values()].sort((a, b) => cmp(b.spent, a.spent) || b.id - a.id).slice(0, 40);
      return {
        week: sum(expensesIn(ws, addDays(ws, 7)), e => e.amt),
        month: sum(expensesIn(ms, addMonths(ms, 1)), e => e.amt),
        today: today(),
        items: items.map(e => ({
          id: e.id, category: e.cat, description: e.desc, amount: e.amt, date: fmtDate(e.spent),
        })),
      };
    }

    function addExpense(b) {
      const category = String(b.category === undefined ? '' : b.category);
      if (!CATEGORIES.includes(category)) throw new ApiError('Toifani tanlang');
      const amount = amountArg(b.amount);
      let spent = today();
      if (b.date) {
        spent = String(b.date);
        if (!validIso(spent)) throw new ApiError("Sana noto'g'ri");
        if (spent > today() || spent < addDays(today(), -90)) {
          throw new ApiError("Sana bugundan keyin yoki 90 kundan eski bo'lmasin");
        }
      }
      const desc = cpSlice(String(b.description || '').trim(), 200) || null;
      const id = D.maxE + 1;
      logExp(JSON.stringify([id, category, amount, spent, desc, packTime(nowStr()), device]));
      return { id };
    }

    function deleteExpense(eidRaw) {
      const e = D.exp.get(toInt(eidRaw));
      if (!e) throw new ApiError('Xarajat topilmadi', 404);
      logExp(`-${e.id},${packTime(nowStr())}${devTail()}`);
      return { ok: true };
    }

    // ---------- hisobot ----------
    function getReport(q) {
      let kind = q.k === undefined ? 'w' : q.k;
      const offset = Math.min(toInt(q.o === undefined ? '0' : q.o, 'davr'), 0);
      let d1, d2, label;
      if (kind === 'm') {
        d1 = addMonths(monthStart(today()), offset);
        d2 = addMonths(d1, 1);
        label = monthLabel(d1);
      } else {
        kind = 'w';
        d1 = addDays(weekStart(), offset * 7);
        d2 = addDays(d1, 7);
        label = weekLabel(d1);
      }
      const pays = paymentsIn(d1, d2), exps = expensesIn(d1, d2);
      const inc = sum(pays, p => p.amt), exp = sum(exps, e => e.amt);
      const byFloor = new Map();
      const sfloor = new Map(D.students.map(s => [s.id, s.fid]));
      for (const p of pays) {
        const fid = sfloor.get(p.sid);
        byFloor.set(fid, (byFloor.get(fid) || 0) + p.amt);
      }
      const byCat = new Map();
      for (const e of exps) byCat.set(e.cat, (byCat.get(e.cat) || 0) + e.amt);
      return {
        kind, offset, label,
        income: inc, n_pay: pays.length, expense: exp, n_exp: exps.length, diff: inc - exp,
        by_floor: D.floors.filter(f => byFloor.has(f.id)).sort(floorOrder)
          .map(f => ({ name: f.name, total: byFloor.get(f.id) })),
        by_cat: [...byCat].map(([name, total]) => ({ name, total }))
          .sort((a, b) => b.total - a.total || cmp(a.name, b.name)),
        status: offset === 0 ? statusCounts() : null,
        kassa: kassa(),
        meals: mealsIn(isoDay(d1), isoDay(d2)),
      };
    }

    function getDebtors() {
      const fee = currentFee();
      const bals = balances();
      const fl = floorsMap();
      const groups = [], left = [];
      let total = 0;
      for (const s of listStudents(null, null)) {
        const b = bals.get(s.id);
        if (b.debt <= 0) continue;
        const floor = fl.get(s.fid).name;
        const item = {
          id: s.id, name: s.name, room: s.room, debt: b.debt,
          status: s.act ? statusOf(b, fee) : 'left', floor,
        };
        total += b.debt;
        if (!s.act) left.push(item);
        else if (groups.length && groups[groups.length - 1].floor === floor) groups[groups.length - 1].items.push(item);
        else groups.push({ floor, items: [item] });
      }
      const count = sum(groups, g => g.items.length) + left.length;
      return { groups, left, total, count };
    }

    // ---------- sozlamalar ----------
    function getSettings() {
      return {
        fee: currentFee(), next_fee: nextFee(),
        this_week: weekLabel(weekStart()), next_week: weekLabel(addDays(weekStart(), 7)),
        opening_cash: D.cash,
      };
    }

    function setFee(b) {
      const amount = amountArg(b.amount);
      const start = addDays(weekStart(), b.when === 'next' ? 7 : 0);
      D.fees = D.fees.filter(([w]) => w < start);
      D.fees.push([start, amount]);
      D.fees.sort((a, b) => cmp(a[0], b[0]));
      return { ok: true, from: weekLabel(start) };
    }

    function setCash(b) {
      D.cash = amountArg(b.amount, true);
      return { ok: true };
    }

    // ---------- matn ko'rinishidagi hisobotlar (nusxalash uchun) ----------
    function debtorsText() {
      const d = getDebtors();
      const out = [`❗ Qarzdorlar — ${weekLabel(weekStart())}`, `Haftalik to'lov: ${money(currentFee())}`];
      for (const g of d.groups) {
        out.push('', `🏢 ${g.floor}`);
        for (const i of g.items) out.push(`${ICON[i.status]} ${i.name}${i.room ? ` (${i.room})` : ''} — ${num(i.debt)}`);
      }
      if (d.left.length) {
        out.push('', '🚶 Chiqib ketganlar');
        for (const i of d.left) out.push(`❌ ${i.name} (${i.floor}) — ${num(i.debt)}`);
      }
      out.push('', d.count ? `Jami: ${d.count} ta bola — ${money(d.total)}` : "🎉 Hamma to'lagan! Qarzdor yo'q.");
      return out.join('\n');
    }

    function reportText(k, o) {
      const r = getReport({ k, o: String(o) });
      const out = [`📊 Hisobot — ${r.label}`, '',
        `💰 Kirim: ${money(r.income)} (${r.n_pay} ta to'lov)`,
        `🛒 Chiqim: ${money(r.expense)} (${r.n_exp} ta xarajat)`,
        `${r.diff >= 0 ? '📈' : '📉'} Farq: ${r.diff > 0 ? '+' : ''}${money(r.diff)}`];
      if (r.meals.total) out.push(`🍽 Ovqat: 1-mahal ${r.meals.m1}, 2-mahal ${r.meals.m2} (jami ${r.meals.total} marta)`);
      if (r.by_cat.length) {
        out.push('', 'Xarajatlar:');
        for (const c of r.by_cat) out.push(`  ${c.name} — ${num(c.total)}`);
      }
      if (r.by_floor.length) {
        out.push('', "Kirim etajlar bo'yicha:");
        for (const f of r.by_floor) out.push(`  ${f.name} — ${num(f.total)}`);
      }
      const k2 = r.kassa;
      out.push('', `🏦 Kassada bo'lishi kerak: ${money(k2.balance)}`,
        `❗ Qarzdorlar: ${k2.debtors} ta — ${money(k2.debt)}`);
      return out.join('\n');
    }

    // ---------- yo'naltirish ----------
    const ROUTES = [
      ['GET', /^\/state$/, () => getState()],
      ['GET', /^\/student\/([^/]+)$/, m => getStudent(m[1])],
      ['PATCH', /^\/student\/([^/]+)$/, (m, b) => updateStudent(m[1], b)],
      ['DELETE', /^\/student\/([^/]+)$/, m => deleteStudent(m[1])],
      ['POST', /^\/student\/([^/]+)\/leave$/, m => leave(m[1])],
      ['POST', /^\/student\/([^/]+)\/return$/, m => comeBack(m[1])],
      ['POST', /^\/students$/, (m, b) => addStudents(b)],
      ['POST', /^\/pay$/, (m, b) => pay(b)],
      ['DELETE', /^\/payment\/([^/]+)$/, m => deletePayment(m[1])],
      ['PATCH', /^\/payment\/([^/]+)$/, (m, b) => editPayment(m[1], b)],
      ['GET', /^\/journal$/, (m, b, q) => getJournal(q)],
      ['GET', /^\/meals$/, (m, b, q) => getMeals(q)],
      ['POST', /^\/meal$/, (m, b) => addMeal(b)],
      ['DELETE', /^\/meal\/([^/]+)\/([^/]+)\/([^/]+)$/, m => removeMeal(m[1], m[2], m[3])],
      ['POST', /^\/exempt$/, (m, b) => toggleExempt(b)],
      ['POST', /^\/floors$/, (m, b) => addFloors(b)],
      ['PATCH', /^\/floor\/([^/]+)$/, (m, b) => renameFloor(m[1], b)],
      ['DELETE', /^\/floor\/([^/]+)$/, m => deleteFloor(m[1])],
      ['GET', /^\/expenses$/, () => getExpenses()],
      ['POST', /^\/expenses$/, (m, b) => addExpense(b)],
      ['DELETE', /^\/expense\/([^/]+)$/, m => deleteExpense(m[1])],
      ['GET', /^\/report$/, (m, b, q) => getReport(q)],
      ['GET', /^\/debtors$/, () => getDebtors()],
      ['GET', /^\/settings$/, () => getSettings()],
      ['POST', /^\/settings\/fee$/, (m, b) => setFee(b)],
      ['POST', /^\/settings\/cash$/, (m, b) => setCash(b)],
    ];

    /** Server API bilan bir xil: api('POST', '/pay', {student_id, amount}) -> javob yoki ApiError. */
    function api(method, path, body) {
      const [p, qs] = String(path).split('?');
      const q = {};
      if (qs) {
        for (const part of qs.split('&')) {
          const [k, v = ''] = part.split('=');
          q[decodeURIComponent(k)] = decodeURIComponent(v);
        }
      }
      if (body !== undefined && (body === null || typeof body !== 'object' || Array.isArray(body))) {
        throw new ApiError("Noto'g'ri so'rov");
      }
      for (const [mm, re, fn] of ROUTES) {
        if (mm !== method) continue;
        const m = re.exec(p);
        if (!m) continue;
        const r = fn(m, body || {}, q);
        if (method !== 'GET') onChange();
        return r;
      }
      throw new ApiError('Topilmadi', 404);
    }

    return {
      api, load, streams, debtorsText, reportText,
      setOnChange: fn => { onChange = fn || (() => {}); },
      setUser: u => { user = { id: u && u.id || 0, name: (u && u.name) || '' }; },
      setDevice: code => { device = /^[a-z0-9]{1,12}$/.test(code || '') ? code : ''; },
      counts: () => ({
        floors: D.floors.length, students: D.students.length, payments: D.pay.size, expenses: D.exp.size,
        meals: mealsIn(0, Infinity).total,
      }),
    };
  }

  const PLATFORM = { a: '📱 Android', i: '📱 iPhone', d: '💻 Kompyuter', m: '💻 Mac', w: '🌐 Veb' };
  /** "a3f9k" -> "📱 Android 3F9K" — qaysi qurilmadan kiritilgani. */
  function deviceLabel(code) {
    if (!code) return '';
    return `${PLATFORM[code[0]] || '📱 Qurilma'} ${code.slice(1).toUpperCase()}`.trim();
  }

  return {
    createDb, ApiError, CATEGORIES, deviceLabel,
    setClock: fn => { clock = fn || (() => Date.now()); },
    _t: { parseAmount, parseStudentLine, floorName, cleanRoom, weekStart, weekLabel, addMonths, monthLabel, packTime, unpackTime, num,
      packSet, unpackSet, dayLabel },
  };
});
