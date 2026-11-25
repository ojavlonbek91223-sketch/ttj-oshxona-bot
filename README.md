# TTJ oshxona hisobi — Telegram bot

Bu bot oshpazning daftarini almashtiradi: bolalarni etajlar bo'yicha yozib qo'yadi,
haftalik to'lovni (90 000 so'm) tugma bilan qabul qiladi, bozorlik xarajatlarini yozadi,
kim qarzdorligini ko'rsatadi va hisobotlarni chiqaradi.

---

## 📱 Asosiy usul: serversiz ilova (hozir shu ishlaydi)

Server kerak emas, pul to'lanmaydi, hech qachon "uxlab" qolmaydi.

- **Ochish:** Telegram'da botni oching → chap pastdagi **«📱 Ochish»** tugmasi.
- **Ilova sahifasi** GitHub Pages'da turadi (bepul): `docs/` papkasi →
  https://ojavlonbek91223-sketch.github.io/ttj-oshxona-bot/
- **Ma'lumotlar** ilovani ochgan odamning **Telegram akkauntida** (Telegram CloudStorage) saqlanadi.
  Telefon almashsa yoki buzilsa ham yo'qolmaydi — shu akkaunt bilan botni ochish kifoya.
  Kompyuterdagi Telegram'dan ham ochsa bo'ladi. Boshqa odam ochsa — u o'zining bo'sh daftarini ko'radi,
  oshpazning ma'lumotini ko'ra olmaydi.
- **Hisob-kitob** telefonning o'zida bajariladi (`docs/logic.js`); u server versiyasi bilan aynan bir xil
  ishlashi `tests/crosscheck.py` bilan tekshirilgan.
- **Sig'im:** Telegram har bir akkauntga 1024 ta yozuv × 4 KB beradi. 300 ta bolaning 2 yillik hisobi
  ~20% joy oladi (`node tests/store_test.js`). Band joy ⚙️ Sozlama bo'limida ko'rinadi.

**Cheklovlar:** ma'lumotni faqat bitta Telegram akkaunt yuritadi (ikkinchi admin yo'q); yakshanba
hisoboti chatga o'zi kelmaydi — 📊 Hisobot bo'limida ko'rinadi, «📋 Nusxalash» bilan istalgan chatga
yuborish mumkin; Excel fayl yo'q; bot `/start` kabi buyruqlarga javob bermaydi (hamma ish ilovada).

**Ilovani yangilash:** `docs/` dagi fayllarni o'zgartirib GitHub'ga yuklash kifoya — 1–2 daqiqada yangilanadi.
`index.html` dagi `?v=` raqamini oshiring (telefon eski nusxani eslab qolmasligi uchun).

**Kompyuterda sinash:** `python -m http.server 8095 --directory docs` → http://localhost:8095
(Telegram'siz «SINOV REJIMI»: ma'lumot faqat shu brauzerda).

> Quyidagi bo'limlar — server bilan ishlaydigan **chat-bot versiyasi** (ixtiyoriy, kelajak uchun).
> Uning ma'lumotlari serversiz ilova bilan umumiy emas.

---

## Bot nima qila oladi

| Menyu tugmasi | Nima qiladi |
|---|---|
| 💵 **To'lov qabul qilish** | Etaj → bola → «✅ 90 000 to'ladi». Ikki bosishda tayyor. Qisman to'lov, oldindan to'lov, «bu hafta ozod» (uyga ketgan bola uchun) ham bor. |
| 🛒 **Xarajat qo'shish** | Toifa (go'sht, guruch, yog', non...) → summa → nima olingani. |
| 📊 **Hisobot** | Haftalik va oylik kirim-chiqim, etajlar bo'yicha kirim, kassadagi pul, Excel fayl. |
| ❗ **Qarzdorlar** | Etajlar bo'yicha kim qancha qarz. |
| 👥 **Bolalar** | Etaj qo'shish, bola qo'shish (bir yo'la ko'p), tahrirlash, boshqa etajga ko'chirish, «chiqib ketdi». |
| ⚙️ **Sozlamalar** | Haftalik summani o'zgartirish, boshlang'ich kassa, adminlar, zaxira nusxa. |

**Belgilar:** ✅ to'lagan · 🟡 qisman to'lagan · ❌ to'lamagan · 💤 bu hafta ozod

**Qanday hisoblaydi:** har dushanba har bir bolaga haftalik to'lov qo'shiladi.
Bola to'lasa — qarzi kamayadi. Ko'proq to'lasa — keyingi haftaga o'tadi.
Haftalik summa o'zgarsa, o'tgan haftalar eski summa bilan qoladi.

**Xatoni tuzatish:** to'lov yozilgach «↩️ Oxirgi to'lovni bekor qilish» tugmasi chiqadi.
Eskiroq xatoni bolaning kartochkasi → 📜 Tarix → 🗑 orqali o'chirish mumkin.
Xarajatni: 🛒 Xarajat qo'shish → 📋 Oxirgi xarajatlar → 🗑.

**Avtomatik:** har yakshanba kechqurun (soat 20:00 dan keyin) bot barcha adminlarga
haftalik hisobot, Excel fayl va zaxira nusxani o'zi yuboradi.

---

## O'rnatish (bir marta, ~15 daqiqa)

### 1. Bot yaratish (telefonda)
1. Telegramda **@BotFather** ni oching → `/newbot` yozing.
2. Bot nomini yozing, masalan: `TTJ Oshxona`.
3. Username yozing (oxiri `bot` bilan tugashi shart), masalan: `ttj3_oshxona_bot`.
4. BotFather **token** beradi (`1234567890:AAH...` ko'rinishida). Uni hech kimga bermang.

### 2. Kompyuterga Python o'rnatish
- https://www.python.org/downloads/ dan Python 3.10 yoki yangisini yuklab o'rnating.
- O'rnatishda **«Add Python to PATH»** belgisini qo'ying.

### 3. Sozlash
1. Shu papkadagi `.env.example` faylini nusxalab, nomini `.env` qiling.
2. `.env` ni Bloknot bilan oching va `BOT_TOKEN=` dan keyin tokenni qo'ying:
   ```
   BOT_TOKEN=1234567890:AAH...
   ```
3. Saqlang.

### 4. Ishga tushirish
- `start.bat` faylini ikki marta bosing. Birinchi marta kutubxonalarni o'zi o'rnatadi (1–2 daqiqa).
- «Bot ishga tushdi» yozuvi chiqsa — tayyor. **Oynani yopmang** — yopilsa bot to'xtaydi.

### 5. Birinchi kirish
1. Telegramda botingizni oching va `/start` bosing.
   **Birinchi /start yozgan odam bosh admin bo'ladi** — shuning uchun buni oshpaz (yoki mas'ul) o'zi qilsin.
2. 👥 **Bolalar** → **➕ Etaj qo'shish** → yozing:
   ```
   1
   2
   3
   4
   ```
   (bot «1-etaj», «2-etaj»... qilib saqlaydi)
3. 👥 **Bolalar** → **➕ Bola qo'shish** → etajni tanlang → ismlarni har birini yangi qatordan yozing,
   xonani vergul bilan:
   ```
   Aliyev Vali, 305
   Karimov Sardor, 305
   Toshmatov Jasur, 306
   ```
4. ⚙️ **Sozlamalar** → **📒 Boshlang'ich kassa** — daftardagi hozirgi qoldiqni yozing.
5. Daftarda eski qarzi bor bolalar uchun: bolaning kartochkasi → ⚙️ Tahrirlash → **📒 Daftardagi eski qarz**.

### 6. Boshqa odamni qo'shish (yordamchi, mudir)
1. U odam botga `/start` yozadi — bot unga **ID raqamini** ko'rsatadi.
2. Siz: ⚙️ Sozlamalar → 👤 Adminlar → ➕ Admin qo'shish → shu raqamni yozasiz.

Boshqa hech kim botdan foydalana olmaydi.

---

## ☁️ Bepul serverga joylash (Render + Neon)

Bot va ilova kompyutersiz, kecha-kunduz ishlaydi. Ikkala xizmat ham bepul va bank kartasi so'ramaydi.
- **Neon** — ma'lumotlar bazasi (Postgres, 1 GB bepul).
- **Render** — bot va ilova serveri (GitHub'dan avtomatik o'rnatadi).

**1. Neon (baza)**
1. https://neon.com → **Sign up** (GitHub akkaunti bilan kirish mumkin).
2. **New project** → nomi `ttj-oshxona` → region **Frankfurt** (Evropa — O'zbekistonga yaqin).
3. **Connect** tugmasi → **Connection string** ni nusxalang
   (`postgresql://...neon.tech/neondb?sslmode=require` ko'rinishida). Uni hech kimga bermang.

**2. Render (server)**
1. https://render.com → **Sign up** → **GitHub** bilan kiring.
2. **New** → **Blueprint** → `ttj-oshxona-bot` repozitoriysini tanlang
   (Render `render.yaml` faylini o'zi o'qiydi).
3. So'ralgan ikki qiymatni kiriting:
   - `BOT_TOKEN` — @BotFather bergan token;
   - `DATABASE_URL` — Neon'dan nusxalangan manzil.
4. **Apply** → 3–5 daqiqa kuting.
5. Tekshirish: `https://<servis-nomi>.onrender.com/health?db=1` → `{"ok": true, "db": "postgres", "db_ok": true}`.

**3. Muhim:** botni **kompyuterda ishga tushirmang** — server ishlayotganini ko'rsa, kompyuterdagi bot
o'zi to'xtaydi (aks holda serverdagi bot xabar olmay qolardi).

**4. Telegram:** botni oching → `/start` (birinchi yozgan odam bosh admin bo'ladi) → chap pastdagi
**«📱 Ochish»** tugmasi ilovani ochadi.

**Bepul serverning cheklovi:** Render bepul serveri 15 daqiqa ishlatilmasa «uxlab qoladi».
Shundan keyingi birinchi xabarga javob ~1 daqiqada keladi, keyin odatdagidek tez ishlaydi.
Uxlamasligi uchun https://cron-job.org da har 10 daqiqada
`https://<servis-nomi>.onrender.com/health` manzilini ochadigan vazifa qo'yish mumkin
(Render buni tavsiya qilmaydi, lekin bepul tarif 750 soat/oy — butun oyga yetadi).

Kodni o'zgartirib GitHub'ga yuklasangiz, Render yangi versiyani o'zi o'rnatadi.

---

## Bot qayerda ishlaydi?

Yuqoridagi bepul server tavsiya qilinadi. Boshqa yo'llar:

**A) Oshxona/ofis kompyuteri** — `start.bat` ni ishga tushirib qo'yasiz. Kompyuter o'chsa bot ham
to'xtaydi, lekin ma'lumotlar yo'qolmaydi (`data/oshxona.db` faylida saqlanadi). Qayta yoqilganda
`start.bat` ni yana ishga tushirasiz. Avtomatik ishga tushishi uchun: `Win + R` → `shell:startup` →
ochilgan papkaga `start.bat` ning yorlig'ini (ярлык) qo'ying.

**B) VPS server (tavsiya, oyiga ~3–5$)** — kecha-kunduz ishlaydi, kompyuterga bog'liq emas.
Ubuntu serverda:
```bash
sudo apt update && sudo apt install -y python3-venv
cd /opt && sudo mkdir ttj-bot && sudo chown $USER ttj-bot && cd ttj-bot
# shu papkadagi fayllarni bu yerga ko'chiring, .env ni to'ldiring
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
`/etc/systemd/system/ttj-bot.service` fayli:
```ini
[Unit]
Description=TTJ oshxona bot
After=network-online.target

[Service]
WorkingDirectory=/opt/ttj-bot
ExecStart=/opt/ttj-bot/.venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```
So'ng: `sudo systemctl enable --now ttj-bot`

---

## 📱 Telegram Mini App (ilova)

Botning ichida sayt kabi ochiladigan ilova bor: 5 bo'lim — **To'lov**, **Xarajat**, **Hisobot**,
**Bolalar**, **Sozlama**. Ro'yxatdagi har bir bolaning yonida «+90 000» tugmasi bor — bir bosishda
to'lov yoziladi, xato bo'lsa pastdagi «Bekor qilish» bilan qaytariladi. Chat botidagi barcha
imkoniyatlar ilovada ham bor, ma'lumotlar bitta bazada.

Ilova ishlashi uchun unga internetda **HTTPS manzil** kerak (Telegram talabi). Masalan
`https://app.oshpaz.uz`. Manzil tayyor bo'lgach `.env` ga yoziladi:
```
WEBAPP_URL=https://app.oshpaz.uz
```
va bot qayta ishga tushiriladi — botda chap pastda **«📱 Ochish»** tugmasi paydo bo'ladi.

**VPS'da (Caddy bilan, HTTPS avtomatik):**
1. Domen boshqaruvida `app.oshpaz.uz` uchun **A yozuv** qo'shing → VPS IP manzili.
2. VPS'da: `sudo apt install -y caddy`
3. `/etc/caddy/Caddyfile`:
   ```
   app.oshpaz.uz {
       reverse_proxy 127.0.0.1:8080
   }
   ```
4. `sudo systemctl reload caddy` — Caddy HTTPS sertifikatni o'zi oladi.

Ilovaga faqat adminlar kira oladi: har bir so'rov Telegram imzosi bilan tekshiriladi.

**Dasturchi uchun:** `python tests/dev_server.py` — namunaviy ma'lumotlar bilan ilovani
brauzerda (http://localhost:8090) Telegram'siz ko'rish.

---

## Ma'lumotlar xavfsizligi

- Serverda ma'lumotlar Neon bazasida, kompyuterda — `data/oshxona.db` faylida.
- Har yakshanba bot zaxira nusxani adminlarga yuboradi (serverda `.json`, kompyuterda `.db` fayl).
  Qo'lda: ⚙️ Sozlamalar → 💾 Zaxira nusxa.
- **`.json` zaxiradan tiklash:** `python restore_backup.py oshxona_backup_....json`
  (`.env` dagi `DATABASE_URL` bazasiga yoziladi; bazada ma'lumot bo'lsa `--force` kerak).
- **`.db` zaxiradan tiklash (kompyuter):** botni to'xtating → faylni `data` papkasiga ko'chiring va
  nomini `oshxona.db` qiling → botni qayta ishga tushiring.

---

## Dasturchi uchun

```
docs/           — SERVERSIZ ilova (GitHub Pages): index.html, app.js (ekranlar),
                  logic.js (hisob-kitob), store.js (Telegram bulutiga saqlash), style.css
tests/crosscheck.py — logic.js ni db.py + webserver.py bilan 1500 ta tasodifiy amalda solishtiradi (Node.js kerak)
tests/store_test.js — bulutga saqlash: 2 yillik hajm, internet uzilishi, ikki qurilma (node tests/store_test.js)

bot.py          — ishga tushirish, dispatcher
config.py       — .env sozlamalari
db.py           — baza (SQLite yoki Postgres): etajlar, bolalar, to'lovlar, ozod haftalar, xarajatlar, qarz hisobi
views.py        — barcha ekranlar (matn + tugmalar)
handlers/       — tugma va xabarlarga javoblar
export.py       — Excel hisobot
jobs.py         — yakshanba avtomatik hisoboti
webserver.py    — Mini App uchun veb-server va JSON API (Telegram initData tekshiruvi)
webapp/         — Mini App sahifasi (index.html, app.js, style.css)
render.yaml     — Render serveriga joylash sozlamasi
restore_backup.py — JSON zaxirani bazaga tiklash
tests/simulate.py — bot uchun Telegram'siz to'liq sinov
tests/test_api.py — Mini App API sinovi
tests/test_webhook.py — server (webhook) rejimi sinovi
tests/dev_server.py — ilovani brauzerda namunaviy ma'lumot bilan ko'rish
```

Testlarni Postgres'da ishlatish: `TEST_DATABASE_URL=postgresql://... python tests/test_api.py`
