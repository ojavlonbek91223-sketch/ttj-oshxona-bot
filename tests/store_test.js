// Telegram bulutiga saqlash (docs/store.js) sinovi — Telegram cheklovlari bilan nusxa (memoryBackend) ustida.
//   node tests/store_test.js
'use strict';
const path = require('path');
const L = require(path.join(__dirname, '..', 'docs', 'logic.js'));
const S = require(path.join(__dirname, '..', 'docs', 'store.js'));

let failed = false;
function check(cond, what, extra = '') {
  if (!cond) { console.log(`❌ XATO: ${what} ${extra}`); failed = true; throw new Error(what); }
  console.log(`✅ ${what}`);
}
const memKv = () => { const m = new Map(); return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) }; };
const same = (a, b) => ['c', 'p', 'e', 'o', 'k'].every(k => (a[k] || '') === (b[k] || ''));

let now = Date.UTC(2026, 8, 1, 3, 0, 0);
L.setClock(() => now);
const MIN = 60000, DAY = 86400000;

async function freshLoad(backend) {
  const st = S.createStore(backend);
  const idx = await st.loadIndex();
  const data = await st.loadData(idx);
  st.adopt(idx);
  return { st, data };
}

async function volume() {
  // 300 bola, 9 etaj, 2 yil: har hafta har bola to'laydi, har kuni 2 mahal ovqat, 1 xarajat; har kuni oxirida saqlanadi.
  const backend = S.memoryBackend();
  const store = S.createStore(backend, { kv: memKv() });
  const db = L.createDb();
  db.api('POST', '/floors', { text: '1\n2\n3\n4\n5\n6\n7\n8\n9' });
  for (let f = 1; f <= 9; f++) {
    const lines = [];
    for (let i = 0; i < 34; i++) lines.push(`Familiyaov Ismjon ${f}-${i}, ${f}${String(i).padStart(2, '0')}`);
    db.api('POST', '/students', { floor_id: f, text: lines.join('\n') });
  }
  await store.commit(db.streams());
  const sids = db.api('GET', '/state').students.map(s => s.id);
  let commits = 0, maxWrites = 0, sumWrites = 0;
  for (let day = 0; day < 730; day++) {
    now += DAY;
    const dow = new Date(now + 5 * 3600000).getUTCDay();
    if (dow === 1) {           // dushanba: hamma to'laydi
      for (const sid of sids) { now += 7000; db.api('POST', '/pay', { student_id: sid, amount: 90000 }); }
    }
    db.api('POST', '/expenses', { category: L.CATEGORIES[day % 12], amount: 150000 + day, description: `${day}-kun xaridi` });
    for (const sid of sids) {   // ovqat: har kuni ikki mahal, ba'zilar kelmagan
      if ((sid * 7 + day) % 20) db.api('POST', '/meal', { student_id: sid, meal: 1 });
      if ((sid * 3 + day) % 20) db.api('POST', '/meal', { student_id: sid, meal: 2 });
    }
    const r = await store.commit(db.streams());
    commits++;
    sumWrites += r.writes;
    maxWrites = Math.max(maxWrites, r.writes);
  }
  const u = store.usage();
  const c = db.counts();
  console.log(`   2 yil: ${c.payments} to'lov, ${c.expenses} xarajat, ${c.meals} ovqat belgisi → ${u.keys} kalit (${u.percent}%), ${(u.bytes / 1024).toFixed(0)} KB`);
  console.log(`   har saqlashda o'rtacha ${(sumWrites / commits).toFixed(1)} ta yozuv, eng ko'pi ${maxWrites} (300 ta to'lovli kun)`);
  check(u.keys < 1024 * 0.5, "300 bola × 2 yil Telegram xotirasining yarmiga ham yetmaydi");
  check(backend.map.size === u.keys, "bulutda ortiqcha (yetim) kalit qolmagan", `${backend.map.size} vs ${u.keys}`);
  const { data } = await freshLoad(backend);
  check(same(data, db.streams()), "yangi qurilmada yuklangan ma'lumot aynan bir xil");

  // bitta to'lov — nechta yozuv?
  now += 7 * DAY;   // yangi hafta (haftada bitta to'lov)
  db.api('POST', '/pay', { student_id: sids[5], amount: 90000 });
  const r = await store.commit(db.streams());
  console.log(`   bitta to'lov: ${r.writes} ta yangi bo'lak + root, ${r.removed} ta eski o'chirildi`);
  check(r.writes <= 3, "bitta to'lov bulutga 1–3 ta bo'lak yozadi (hammasini emas)");

  // bitta ovqat belgisi va o'tgan kunga keyin yozilgan belgi — nechta yozuv?
  now += DAY;
  db.api('POST', '/meal', { student_id: sids[7], meal: 1 });
  const rm = await store.commit(db.streams());
  check(rm.writes <= 3, `bitta ovqat belgisi ${rm.writes} ta bo'lak yozadi`);
  const back = new Date(now - 10 * DAY + 5 * 3600000).toISOString().slice(0, 10);
  const fed = +Object.keys(db.api('GET', `/meals?d=${back}`).marks)[0];
  db.api('DELETE', `/meal/${fed}/${back}/1`);
  db.api('POST', '/meal', { student_id: fed, meal: 1, date: back });
  const rl = await store.commit(db.streams());
  check(rl.writes <= 5, `10 kun oldingi ovqatni tuzatish ${rl.writes} ta bo'lak yozadi`);
  const again = await freshLoad(backend);
  check(same(again.data, db.streams()), "ovqat belgilari bilan ham yangi qurilmada aynan bir xil");
  check(JSON.parse(backend.map.get('root')).v === 2, "bulut 2-versiyada (eski ilova bu ma'lumot ustidan yozmaydi)");
  return { backend, store, db };
}

async function crash() {
  const backend = S.memoryBackend();
  const store = S.createStore(backend, { kv: memKv() });
  const db = L.createDb();
  db.api('POST', '/floors', { text: '1\n2' });
  db.api('POST', '/students', { floor_id: 1, text: Array.from({ length: 120 }, (_, i) => `Bola Ismli ${i}`).join('\n') });
  for (let i = 1; i <= 120; i++) { now += 5000; db.api('POST', '/pay', { student_id: i, amount: 90000 }); }
  await store.commit(db.streams());
  const good = db.streams();

  // yangi o'zgarishlar: ko'p bo'lak o'zgaradi (bola nomlari + to'lovlar + xarajat)
  for (let i = 1; i <= 120; i += 3) db.api('PATCH', `/student/${i}`, { name: `Yangi Nom ${i}` });
  now += 7 * DAY;   // keyingi hafta (haftada bitta to'lov)
  for (let i = 1; i <= 120; i++) { now += 5000; db.api('POST', '/pay', { student_id: i, amount: 45000 }); }
  db.api('POST', '/expenses', { category: L.CATEGORIES[0], amount: 500000 });

  let crashes = 0;
  for (let n = 1; n < 12; n++) {
    backend.setFailAfter(n);    // n-chi so'rovdan keyin internet uziladi
    try { await store.commit(db.streams()); backend.setFailAfter(Infinity); break; } catch (e) { crashes++; }
    backend.setFailAfter(Infinity);
    const { data } = await freshLoad(backend);
    check(same(data, good), `uzilish (${n}-so'rovda): bulutda eski, butun holat qoldi`);
  }
  check(crashes > 0, `${crashes} marta yozish o'rtasida uzildi`);
  const r = await store.commit(db.streams());
  const { data } = await freshLoad(backend);
  check(same(data, db.streams()), 'internet qaytgach qayta urinish hammasini saqladi');
  const orphans = backend.map.size - r.keys;
  console.log(`   uzilishlardan ${orphans} ta yetim bo'lak qoldi`);

  // yetim bo'laklarni tozalash: birinchi marta faqat belgilanadi, 10 daqiqadan keyin o'chiriladi
  let t = Date.now();
  const kv = memKv();
  const g = S.createStore(backend, { kv, now: () => t });
  const idx = await g.loadIndex(); g.adopt(idx);
  const first = await g.gc();
  check(first === 0 && backend.map.size === r.keys + orphans, 'tozalash: darhol o\'chirmaydi (boshqa qurilma yozayotgan bo\'lishi mumkin)');
  t += 11 * MIN;
  const second = await g.gc();
  check(second === orphans && backend.map.size === r.keys, `tozalash: 10 daqiqadan keyin ${second} ta yetim bo'lak o'chirildi`);
  const again = await freshLoad(backend);
  check(same(again.data, db.streams()), "tozalashdan keyin ma'lumot butun");
}

async function conflict() {
  const backend = S.memoryBackend();
  const a = S.createStore(backend);
  const dbA = L.createDb();
  dbA.api('POST', '/floors', { text: '1' });
  dbA.api('POST', '/students', { floor_id: 1, text: 'Aliyev Vali\nKarimov Sardor' });
  await a.commit(dbA.streams());

  const { st: b, data } = await freshLoad(backend);   // ikkinchi qurilma (masalan kompyuter)
  const dbB = L.createDb(); dbB.load(data);

  now += MIN; dbA.api('POST', '/pay', { student_id: 1, amount: 90000 });
  await a.commit(dbA.streams());
  now += MIN; dbB.api('POST', '/pay', { student_id: 2, amount: 90000 });
  let err = null;
  try { await b.commit(dbB.streams()); } catch (e) { err = e; }
  check(err && err.conflict, 'eskirgan qurilma ustidan yoza olmaydi (ConflictError)');
  const fresh = await freshLoad(backend);
  check(same(fresh.data, dbA.streams()), "bulutda birinchi qurilmaning to'lovi saqlanib qoldi");
}

async function sync() {
  const backend = S.memoryBackend({ latency: 3 });
  const store = S.createStore(backend);
  const db = L.createDb();
  const saved = [];
  const mirrorData = {};
  const mirror = { save: (streams, cid, pending) => Object.assign(mirrorData, { streams, cid, pending }) };
  const statuses = [];
  const fast = (fn, ms) => setTimeout(fn, Math.min(ms, 20));
  const sy = S.createSync({ store, db, mirror, debounce: 10, setTimer: fast, onStatus: s => statuses.push(s) });
  db.setOnChange(() => sy.markDirty());
  db.api('POST', '/floors', { text: '1' });
  db.api('POST', '/students', { floor_id: 1, text: 'A B\nC D\nE F' });
  for (let i = 1; i <= 3; i++) { now += 5000; db.api('POST', '/pay', { student_id: i, amount: 90000 }); }
  check(mirrorData.pending === true, "o'zgarish darhol telefonga (pending) yozildi");
  await new Promise(r => setTimeout(r, 120));
  check(!sy.pending() && mirrorData.pending === false, "bulutga saqlandi, telefondagi nusxa 'saqlangan' deb belgilandi");
  check(statuses.filter(s => s === 'saving').length === 1, "5 ta tez o'zgarish bitta saqlashga yig'ildi");

  backend.setFailAfter(0);                 // internet yo'q
  now += 7 * DAY; db.api('POST', '/pay', { student_id: 1, amount: 1000 });
  await new Promise(r => setTimeout(r, 80));
  check(statuses.includes('error') && sy.pending(), 'internet yo\'q: xato ko\'rsatildi, o\'zgarish kutmoqda');
  backend.setFailAfter(Infinity);          // internet qaytdi
  await new Promise(r => setTimeout(r, 200));
  check(!sy.pending() && statuses[statuses.length - 1] === 'saved', 'internet qaytgach o\'zi qayta urinib saqladi');
  const { data } = await freshLoad(backend);
  check(same(data, db.streams()), "bulutdagi ma'lumot ilovadagi bilan bir xil");
}

(async () => {
  try {
    console.log('— 2 yillik hajm'); await volume();
    console.log('— yozish o\'rtasida internet uzilishi'); await crash();
    console.log('— ikki qurilma'); await conflict();
    console.log('— avtomatik saqlash'); await sync();
    console.log('\n✅ Saqlash sinovlari o\'tdi');
  } catch (e) {
    if (!failed) console.log('❌', e);
    process.exit(1);
  }
})();
