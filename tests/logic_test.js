// Serversiz ilovaning yangi qoidalari: haftada bitta to'lov, to'lovni o'zgartirish/o'chirish tarixi, qurilma.
//   node tests/logic_test.js
'use strict';
const path = require('path');
const L = require(path.join(__dirname, '..', 'docs', 'logic.js'));

function check(cond, what, extra = '') {
  if (!cond) { console.log(`❌ XATO: ${what} ${extra}`); process.exit(1); }
  console.log(`✅ ${what}`);
}
function err(fn) { try { fn(); return null; } catch (e) { return e; } }

// 2026-11-25 (chorshanba) 10:00 Toshkent
let now = Date.UTC(2026, 10, 25, 5, 0, 0);
L.setClock(() => now);
const MIN = 60000, DAY = 86400000;

const db = L.createDb();
db.setDevice('a3f9k');
db.api('POST', '/floors', { text: '1' });
db.api('POST', '/students', { floor_id: 1, text: 'Aliyev Vali, 305\nKarimov Sardor' });

// --- to'lov sana-vaqti va qurilmasi
const r1 = db.api('POST', '/pay', { student_id: 1, amount: 90000 });
check(r1.at === '25.11.2026 10:00', "to'lov sana va vaqti bilan yozildi", r1.at);
let st = db.api('GET', '/state');
let s1 = st.students.find(s => s.id === 1);
check(s1.week_pay && s1.week_pay.amount === 90000 && s1.week_pay.at === '25.11.2026 10:00' && s1.week_pay.dev === 'a3f9k',
  "ro'yxatda shu haftadagi to'lov, vaqti va qurilmasi ko'rinadi");

// --- haftada bitta to'lov
now += 2 * DAY;
let e = err(() => db.api('POST', '/pay', { student_id: 1, amount: 45000 }));
check(e && e.status === 409 && e.message.includes("bu hafta to'lagan") && e.message.includes('25.11.2026 10:00'),
  "shu haftada ikkinchi to'lov qabul qilinmaydi (qachon to'lagani aytiladi)", e && e.message);
check(!err(() => db.api('POST', '/pay', { student_id: 2, amount: 90000 })), "boshqa bola shu hafta to'lay oladi");

// --- to'lovni o'zgartirish
now += 5 * MIN;
db.setDevice('i77qp');                    // boshqa telefon (iPhone)
const ed = db.api('PATCH', `/payment/${r1.payment_id}`, { amount: '45 000' });
check(ed.old === 90000 && ed.amount === 45000 && ed.debt === 45000, "to'lov 90 000 → 45 000 ga o'zgartirildi, qarz qayta hisoblandi");
check(err(() => db.api('PATCH', `/payment/${r1.payment_id}`, { amount: 45000 })).message === "Summa o'zgarmadi", "bir xil summaga o'zgartirib bo'lmaydi");
check(err(() => db.api('PATCH', '/payment/999', { amount: 1000 })).status === 404, "yo'q to'lovni o'zgartirib bo'lmaydi");
let card = db.api('GET', '/student/1');
check(card.payments[0].edits.length === 1 && card.payments[0].edits[0].old === 90000 && card.payments[0].edits[0].dev === 'i77qp',
  "kartochkada o'zgarish tarixi: eski summa, vaqt, qaysi qurilma");

// --- o'chirish va qayta to'lash
now += 5 * MIN;
db.api('DELETE', `/payment/${r1.payment_id}`);
card = db.api('GET', '/student/1');
check(card.payments.length === 0 && card.removed.length === 1 && card.removed[0].amount === 45000
  && card.removed[0].paid_at === '25.11.2026 10:00' && card.removed[0].at === '27.11.2026 10:10',
  "o'chirilgan to'lov yo'qolmaydi — kartochkada qachon va qaysi qurilmadan o'chirilgani ko'rinadi");
check(card.can_delete === true, "o'chirilgan to'lov bolani o'chirishga to'sqinlik qilmaydi");
check(!err(() => db.api('POST', '/pay', { student_id: 1, amount: 90000 })), "o'chirilgandan keyin shu hafta qayta to'lash mumkin");

// --- keyingi hafta yana to'lash mumkin
now += 5 * DAY;
check(!err(() => db.api('POST', '/pay', { student_id: 1, amount: 90000 })), "keyingi haftada yana to'lov qabul qilinadi");

// --- xarajat qo'shish/o'chirish ham tarixda
const x = db.api('POST', '/expenses', { category: L.CATEGORIES[0], amount: 350000, description: "go'sht" });
now += MIN;
db.api('DELETE', `/expense/${x.id}`);

// --- tarix (jurnal)
const j = db.api('GET', '/journal');
const kinds = j.items.map(i => i.k).join(',');
check(kinds === 'edel,eadd,padd,padd,pdel,pedit,padd,padd', 'tarixda hamma voqea yangisidan eskisiga', kinds);
const fixes = db.api('GET', '/journal?only=fix');
check(fixes.items.length === 3 && fixes.fixes === 3, "«faqat tuzatishlar»: o'zgartirish va o'chirishlar (3 ta)");
const pe = j.items.find(i => i.k === 'pedit');
check(pe.name === 'Aliyev Vali' && pe.old === 90000 && pe.amount === 45000 && pe.paid_at === '25.11.2026 10:00' && pe.at === '27.11.2026 10:05',
  "tarixda: kim, qaysi to'lov, eski → yangi summa, qachon o'zgartirildi");
check(L.deviceLabel('i77qp') === '📱 iPhone 77QP' && L.deviceLabel('a3f9k') === '📱 Android 3F9K' && L.deviceLabel('') === '',
  "qurilma nomi: platforma + belgi");

// --- saqlab-qayta yuklash: hamma narsa bir xil
const st1 = JSON.stringify([db.api('GET', '/state'), db.api('GET', '/journal'), db.api('GET', '/student/1'), db.api('GET', '/report?k=m&o=0')]);
const db2 = L.createDb();
db2.load(JSON.parse(JSON.stringify(db.streams())));
const st2 = JSON.stringify([db2.api('GET', '/state'), db2.api('GET', '/journal'), db2.api('GET', '/student/1'), db2.api('GET', '/report?k=m&o=0')]);
check(st1 === st2, "saqlab-qayta yuklangandan keyin ham hammasi bir xil (tarix ham)");
check(JSON.parse(db.streams().c).v === 2, 'yangi format belgisi v=2 (eski ilova bu ma\'lumotni noto\'g\'ri o\'qimaydi)');

// --- eski formatdagi (v1) ma'lumot ochiladi
const old = L.createDb();
old.load({
  c: '{"v":1,"cash":0,"fees":[["2000-01-03",90000]],"fl":[[1,"1-etaj",1]],"seq":[1,1],"st":[[1,"Eski Bola",1,null,null,"2026-11-23",null,1,0,[]]]}',
  p: '1,1,90000,1mv2rk\n2,1,45000,1mv2rl\n-2',
  e: '[1,"🍞 Non",20000,"2026-11-24",null]',
});
const os = old.api('GET', '/student/1');
check(os.paid === 90000 && os.removed.length === 1 && os.removed[0].at === '', "eski formatdagi ma'lumot to'g'ri ochiladi");

// ================================================= ovqat: kuniga ikki mahal "+"
{
  let t = Date.UTC(2026, 10, 26, 7, 0, 0);   // 26.11.2026 12:00, payshanba
  L.setClock(() => t);
  const m = L.createDb();
  m.setDevice('a3f9k');
  m.api('POST', '/floors', { text: '1' });
  m.api('POST', '/students', { floor_id: 1, text: 'Aliyev Vali\nKarimov Sardor\nToshmatov Jasur' });

  const r = m.api('POST', '/meal', { student_id: 1, meal: 1 });
  check(r.date === '2026-11-26' && !r.late && r.day_count === 1, "1-mahal ovqat yozildi (bugun, o'z vaqtida)");
  check(m.api('POST', '/meal', { student_id: 1, meal: 2 }).day_count === 2, '2-mahal ham yozildi');
  e = err(() => m.api('POST', '/meal', { student_id: 1, meal: 1 }));
  check(e && e.status === 409 && e.message.includes('allaqachon'), "bir mahalga ikki marta yozilmaydi", e && e.message);
  check(!!err(() => m.api('POST', '/meal', { student_id: 1, meal: 3 })), "3-mahal yo'q — kuniga faqat ikki mahal");
  check(!!err(() => m.api('POST', '/meal', { student_id: 1, meal: 1, date: '2026-11-27' })), "ertangi kunga yozilmaydi");
  check(!!err(() => m.api('POST', '/meal', { student_id: 1, meal: 1, date: '2026-10-26' })), '30 kundan eski kunga yozilmaydi');

  // esidan chiqqan bo'lsa — keyin yozish (boshqa telefondan)
  m.setDevice('i77qp');
  const lt = m.api('POST', '/meal', { student_id: 2, meal: 1, date: '2026-11-25' });
  check(lt.late === true, "kechagi ovqatni bugun keyin yozsa bo'ladi");
  const day = m.api('GET', '/meals');
  check(day.m1 === 1 && day.m2 === 1 && day.marks[1] === 3 && day.active === 3 && day.rel === 'Bugun'
    && day.label === '26-noyabr, payshanba' && day.next === null && day.prev === '2026-11-25', "bugungi ro'yxat: kimga qaysi mahal berilgani");
  const yd = m.api('GET', '/meals?d=2026-11-25');
  check(yd.m1 === 1 && yd.marks[2] === 1 && yd.rel === 'Kecha' && yd.next === '2026-11-26', "kechagi ro'yxatda keyin yozilgani bor");

  // xato qo'yilganini o'chirish
  t += 10 * MIN;
  m.api('DELETE', '/meal/1/2026-11-26/2');
  check(err(() => m.api('DELETE', '/meal/1/2026-11-26/2')).status === 404, "o'chirilgan belgini qayta o'chirib bo'lmaydi");
  check(!err(() => m.api('POST', '/meal', { student_id: 1, meal: 2 })), "o'chirilgandan keyin qayta yozsa bo'ladi");
  m.api('DELETE', '/meal/1/2026-11-26/2');

  const card = m.api('GET', '/student/2').meals;
  check(card.week.length === 7 && card.week[2].cells[0] === 'late' && card.week[3].today && card.week[4].cells === null
    && card.week_count === 1 && card.log[0].k === 'mlate' && card.log[0].dev === 'i77qp' && card.log[0].date === '25.11',
  'kartochkada haftalik jadval: keyin yozilgani ajralib turadi, qaysi qurilmadan');
  const jr = m.api('GET', '/journal');
  check(jr.items.map(i => i.k).join(',') === 'mdel,mdel,mlate', "tarixda o'chirilgan va keyin yozilgan belgilar (o'z vaqtidagilar emas)",
    jr.items.map(i => i.k).join(','));
  check(jr.items[0].name === 'Aliyev Vali' && jr.items[0].date === '26.11' && jr.items[0].meal === 2 && jr.items[0].at === '26.11.2026 12:10',
    "tarixda: kim, qaysi kun, qaysi mahal, qachon o'chirildi");
  check(m.api('GET', '/journal?only=fix').fixes === 2, "o'chirilgan ovqat belgisi «tuzatish» hisoblanadi");

  const rep = m.api('GET', '/report?k=w&o=0');
  check(rep.meals.m1 === 2 && rep.meals.m2 === 0 && rep.meals.total === 2, 'hisobotda haftalik ovqat soni');
  check(m.reportText('w', 0).includes('🍽 Ovqat: 1-mahal 2, 2-mahal 0'), 'nusxalanadigan hisobotda ham bor');

  m.api('POST', '/student/2/leave');
  check(err(() => m.api('DELETE', '/student/2')).message.includes('ovqat'), "ovqat yozilgan bolani butunlay o'chirib bo'lmaydi");
  check(err(() => m.api('POST', '/meal', { student_id: 2, meal: 2 })).message.includes('chiqib ketgan'), 'chiqib ketgan bolaga ovqat yozilmaydi');
  check(!err(() => m.api('DELETE', '/meal/2/2026-11-25/1')) && m.api('GET', '/student/2').can_delete, "belgisi o'chirilsa — bolani o'chirsa bo'ladi");

  // saqlab-qayta yuklash
  const snap = x => JSON.stringify([x.api('GET', '/meals'), x.api('GET', '/meals?d=2026-11-25'), x.api('GET', '/student/1'),
    x.api('GET', '/student/2'), x.api('GET', '/journal'), x.api('GET', '/report?k=m&o=0')]);
  const m2 = L.createDb();
  m2.load(JSON.parse(JSON.stringify(m.streams())));
  check(snap(m) === snap(m2), "ovqat belgilari va tarixi saqlab-qayta yuklangandan keyin bir xil");

  t += Date.UTC(2026, 10, 27, 1) - t;      // ertasi kuni ertalab
  const nd = m2.api('GET', '/meals');
  check(nd.date === '2026-11-27' && nd.m1 === 0 && m2.api('GET', '/meals?d=2026-11-26').m1 === 1, "ertasi kuni ro'yxat bo'sh, kechagisi joyida");
  check(m2.api('GET', '/student/1').meals.week[3].cells[0] === 'on', "kechagi o'z vaqtidagi belgi «keyin yozilgan» bo'lib qolmaydi");

  // ixcham saqlash: tasodifiy to'plamlar to'g'ri tiklanadi
  let ok = true;
  for (let n = 0; n < 300; n++) {
    const s = new Set();
    for (let i = Math.floor(Math.random() * 400); i > 0; i--) s.add(1 + Math.floor(Math.random() * 1500));
    const back = L._t.unpackSet(L._t.packSet(s));
    if (back.size !== s.size || [...s].some(x => !back.has(x))) { ok = false; break; }
  }
  check(ok, "bolalar to'plami ixcham yozilib, aynan tiklanadi (300 ta tasodifiy sinov)");
  const all = new Set(Array.from({ length: 300 }, (_, i) => i + 1));
  check(L._t.packSet(all).length < 60, `300 bolalik bir mahal ${L._t.packSet(all).length} belgida saqlanadi`);
}

console.log("\n✅ Yangi qoidalar sinovi o'tdi");
