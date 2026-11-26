// Python yozib olgan amallarni docs/logic.js da takrorlab, javoblarni solishtiradi.
// Ishga tushirish: python tests/crosscheck.py  (bu faylni o'zi chaqiradi)
'use strict';
const fs = require('fs');
const path = require('path');
const L = require(path.join(__dirname, '..', 'docs', 'logic.js'));

const steps = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let now = 0;
L.setClock(() => now);
// Server versiyasida "haftada bitta to'lov" qoidasi yo'q — solishtirishda o'chiriladi.
const make = () => L.createDb({ onePaymentPerWeek: false });
let db = make();

function canon(v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object') {
    const o = {};
    for (const k of Object.keys(v).sort()) o[k] = canon(v[k]);
    return o;
  }
  return v;
}

function normalize(p, res) {
  const r = JSON.parse(JSON.stringify(res));
  // faqat serversiz versiyada bor maydonlar (vaqt, qurilma, tuzatishlar tarixi)
  const dropExtra = s => { delete s.week_pay; delete s.removed; for (const x of s.payments || []) { delete x.dev; delete x.edits; } };
  if (p === '/state') { delete r.me; (r.students || []).forEach(dropExtra); }
  if (p.startsWith('/student/')) dropExtra(r);
  if (p === '/pay') delete r.at;
  if (p === '/settings') { delete r.admins; delete r.me; }
  if (p.startsWith('/report') && r.by_cat) {
    r.by_cat.sort((a, b) => b.total - a.total || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  }
  return canon(r);
}

let reloads = 0;
for (let i = 0; i < steps.length; i++) {
  const s = steps[i];
  now = s.t;
  let status = 200, res;
  try {
    res = db.api(s.m, s.p, s.b === null ? undefined : s.b);
  } catch (e) {
    if (!(e instanceof L.ApiError)) throw e;
    status = e.status;
    res = { error: e.message };
  }
  const a = JSON.stringify(normalize(s.p, s.res));
  const b = JSON.stringify(normalize(s.p, res));
  if (s.status !== status || a !== b) {
    console.log(`FARQ #${i}: ${s.m} ${s.p} ${JSON.stringify(s.b)}`);
    console.log(`  Python [${s.status}]: ${a.slice(0, 1500)}`);
    console.log(`  JS     [${status}]: ${b.slice(0, 1500)}`);
    process.exit(1);
  }
  // Har 97 amalda: saqlab, qayta yuklab, shu nusxa bilan davom etish (saqlash formati to'g'riligi)
  if (i % 97 === 96) {
    const st = db.streams();
    const before = JSON.stringify(normalize('/state', db.api('GET', '/state')));
    const db2 = make();
    db2.load(JSON.parse(JSON.stringify(st)));
    const after = JSON.stringify(normalize('/state', db2.api('GET', '/state')));
    if (before !== after) { console.log(`Qayta yuklashda farq #${i}`); process.exit(1); }
    db = db2;
    reloads++;
  }
}
const c = db.counts();
console.log(`JS: ${steps.length} ta javob bir xil · ${reloads} marta saqlab-qayta yuklandi · `
  + `${c.floors} etaj, ${c.students} bola, ${c.payments} to'lov, ${c.expenses} xarajat`);
