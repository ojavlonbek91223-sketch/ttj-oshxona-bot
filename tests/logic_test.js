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

console.log("\n✅ Yangi qoidalar sinovi o'tdi");
