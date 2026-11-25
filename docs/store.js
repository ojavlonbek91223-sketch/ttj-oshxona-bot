/* Ma'lumotni Telegram bulutida (CloudStorage) saqlash — serversiz.
 *
 * Telegram har bir foydalanuvchiga har bir bot uchun 1024 ta kalit beradi, har birida 4096 belgigacha.
 *  * Ma'lumot ~4000 baytlik bo'laklarga bo'linadi. Bo'lak kaliti — mazmunining xeshi (d_xxxx),
 *    shuning uchun o'zgarmagan bo'laklar qayta yozilmaydi (yangi to'lov = 1–2 ta yozuv).
 *  * Bo'laklar ro'yxati (manifest) ham shunday bo'laklarda (m_xxxx) turadi.
 *  * "root" kaliti eng oxirida yoziladi. U yozilmaguncha eski holat butunligicha qoladi,
 *    ya'ni internet uzilsa ham yarim yozilgan, buzilgan holat bo'lmaydi.
 *  * Boshqa qurilmada o'zgartirilgan bo'lsa (root.cid boshqacha) — ustidan yozilmaydi (ConflictError).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.OshStore = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const CHUNK_BYTES = 4000;
  const MAX_KEYS = 1024;
  const MAX_VALUE = 4096;
  const STREAMS = ['c', 'e', 'p'];
  const BATCH = 50;       // getItems bir so'rovda nechta kalit
  const PARALLEL = 4;     // bir vaqtda nechta setItem
  const GC_AGE = 10 * 60 * 1000;

  class ConflictError extends Error {
    constructor() { super("Ma'lumot boshqa qurilmada o'zgartirilgan"); this.conflict = true; }
  }

  // cyrb53 — 53 bitli xesh, base36 da ≤ 11 belgi
  function hash(str) {
    let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
    for (let i = 0; i < str.length; i++) {
      const ch = str.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
  }

  const byteLen = cp => (cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4);
  const utf8Bytes = s => { let n = 0; for (const ch of s) n += byteLen(ch.codePointAt(0)); return n; };

  /** Matnni ≤ CHUNK_BYTES baytli bo'laklarga bo'lish (harf o'rtasidan bo'linmaydi). */
  function chunk(str) {
    const out = [];
    let start = 0, bytes = 0, i = 0;
    while (i < str.length) {
      const cp = str.codePointAt(i);
      const w = cp > 0xffff ? 2 : 1;
      const b = byteLen(cp);
      if (bytes + b > CHUNK_BYTES) { out.push(str.slice(start, i)); start = i; bytes = 0; }
      bytes += b;
      i += w;
    }
    if (i > start) out.push(str.slice(start));
    return out;
  }

  const randomId = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36);

  async function pool(items, n, fn) {
    let next = 0;
    const worker = async () => { while (next < items.length) { const i = next++; await fn(items[i]); } };
    await Promise.all(Array.from({ length: Math.min(n, items.length) }, worker));
  }

  function parseManifest(text) {
    const lists = { c: [], e: [], p: [] };
    for (const part of text.split(';')) {
      const [s, hs] = part.split(':');
      if (s in lists) lists[s] = hs ? hs.split(',').map(h => 'd_' + h) : [];
    }
    return lists;
  }

  /**
   * backend: { get(keys) -> {key: value}, set(key, value), remove(keys), keys() -> [key] }
   * kv:      kichik mahalliy xotira (GC nomzodlari uchun), localStorage ga o'xshash: getItem/setItem
   */
  function createStore(backend, { kv = null, now = () => Date.now() } = {}) {
    let rev = 0, cid = '', known = new Set(), info = { keys: 0, bytes: 0 };
    let queue = Promise.resolve();
    const cache = {};   // oqim -> {text, parts:[{key, end, bytes}]}: jurnal oxiriga qo'shilsa, boshi qayta bo'linmaydi

    /** Oqimni bo'laklash; avvalgi matnning o'zgarmagan boshidagi to'liq bo'laklar qayta hisoblanmaydi. */
    function chunkStream(s, text) {
      const old = cache[s];
      let parts = [], from = 0;
      if (old) {
        for (let n = old.parts.length - 1; n > 0; n--) {   // oxirgi bo'lak to'liq bo'lmasligi mumkin
          const end = old.parts[n - 1].end;
          if (text.length >= end && text.startsWith(old.text.slice(0, end))) {
            parts = old.parts.slice(0, n);
            from = end;
            break;
          }
        }
      }
      for (const str of chunk(text.slice(from))) {
        from += str.length;
        parts.push({ key: 'd_' + hash(str), end: from, bytes: utf8Bytes(str), str });
      }
      return { text, parts };
    }

    /** Bulut bilan ishlaydigan barcha amallar navbat bilan — bir-biriga xalal bermaydi. */
    function serial(fn) {
      const r = queue.then(fn, fn);
      queue = r.catch(() => {});
      return r;
    }

    async function getMany(keys) {
      const out = {};
      for (let i = 0; i < keys.length; i += BATCH) Object.assign(out, await backend.get(keys.slice(i, i + BATCH)));
      return out;
    }

    function need(vals, key) {
      const v = vals[key];
      if (typeof v !== 'string' || !v) throw new Error("Ma'lumot to'liq yuklanmadi. Qayta urinib ko'ring.");
      if (hash(v) !== key.slice(2)) throw new Error(`Ma'lumot bo'lagi buzilgan (${key})`);
      return v;
    }

    async function readRoot() {
      const v = (await backend.get(['root'])).root;
      if (!v) return null;
      const r = JSON.parse(v);
      if (r.v !== 1) throw new Error("Ma'lumot yangi versiyada saqlangan — ilovani yangilang");
      return r;
    }

    /** Qaysi bo'laklar borligini o'qish (root + manifest). Ma'lumotning o'zi emas. */
    async function loadIndex() {
      const r = await readRoot();
      if (!r) return { rev: 0, cid: '', lists: { c: [], e: [], p: [] }, mKeys: [], bytes: 0 };
      const mKeys = r.m.map(h => 'm_' + h);
      const mv = await getMany(mKeys);
      const lists = parseManifest(mKeys.map(k => need(mv, k)).join(''));
      return { rev: r.rev, cid: r.cid, lists, mKeys, bytes: r.b || 0 };
    }

    async function loadData(idx) {
      const all = [...new Set(STREAMS.flatMap(s => idx.lists[s]))];
      const vals = await getMany(all);
      const out = {};
      for (const s of STREAMS) out[s] = idx.lists[s].map(k => need(vals, k)).join('');
      return out;
    }

    /** Indeksni "o'ziniki" qilib olish: keyingi yozuvlar shunga asoslanadi. */
    function adopt(idx) {
      rev = idx.rev;
      cid = idx.cid;
      known = new Set([...idx.mKeys, ...STREAMS.flatMap(s => idx.lists[s])]);
      info = { keys: known.size + (cid ? 1 : 0), bytes: idx.bytes || 0 };
    }

    /** Yangi holatni yozish. Faqat o'zgargan bo'laklar yoziladi, oxirida root. */
    async function commit(streams) {
      const remote = await readRoot();
      if ((remote ? remote.cid : '') !== cid) throw new ConflictError();

      const writes = new Map();
      const lists = {}, chunked = {};
      let bytes = 0;
      for (const s of STREAMS) {
        chunked[s] = chunkStream(s, streams[s] || '');
        lists[s] = chunked[s].parts.map(part => {
          if (!known.has(part.key)) writes.set(part.key, part.str);
          bytes += part.bytes;
          return part.key;
        });
      }
      const manifest = STREAMS.map(s => s + ':' + lists[s].map(k => k.slice(2)).join(',')).join(';');
      const mKeys = chunk(manifest).map(part => {
        const k = 'm_' + hash(part);
        if (!known.has(k)) writes.set(k, part);
        return k;
      });
      const next = new Set([...mKeys, ...STREAMS.flatMap(s => lists[s])]);
      if (known.size + writes.size + 1 > MAX_KEYS) {
        throw new Error("Telegram xotirasi to'ldi. Eski ma'lumotlarni arxivlash kerak.");
      }

      await pool([...writes], PARALLEL, ([k, v]) => backend.set(k, v));
      const r = {
        v: 1, rev: (remote ? remote.rev : 0) + 1, cid: randomId(), t: now(),
        m: mKeys.map(k => k.slice(2)), b: bytes, k: next.size,
      };
      await backend.set('root', JSON.stringify(r));

      const stale = [...known].filter(k => !next.has(k));
      known = next;
      rev = r.rev;
      cid = r.cid;
      info = { keys: next.size + 1, bytes };
      for (const s of STREAMS) cache[s] = chunked[s];
      if (stale.length) {
        try { await backend.remove(stale); } catch (e) { /* keyingi tozalashda o'chadi */ }
      }
      return { rev, writes: writes.size, removed: stale.length, keys: info.keys, bytes };
    }

    /**
     * Hech narsa havola qilmaydigan eski bo'laklarni tozalash (uzilib qolgan yozuvlardan qolganlar).
     * Ehtiyot uchun: kalit kamida 10 daqiqa oldin ham "keraksiz" bo'lgan bo'lsagina o'chiriladi.
     */
    async function gc() {
      const remote = await readRoot();
      if ((remote ? remote.cid : '') !== cid) return 0;
      const keys = await backend.keys();
      const orphans = keys.filter(k => k !== 'root' && !known.has(k));
      let seen = {};
      try { seen = JSON.parse((kv && kv.getItem('osh_gc')) || '{}') || {}; } catch (e) { /* bo'sh */ }
      const t = now(), ripe = [], keep = {};
      for (const k of orphans) {
        if (seen[k] && t - seen[k] >= GC_AGE) ripe.push(k);
        else keep[k] = seen[k] || t;
      }
      if (ripe.length) await backend.remove(ripe);
      try { if (kv) kv.setItem('osh_gc', JSON.stringify(keep)); } catch (e) { /* mahalliy xotira yo'q */ }
      return ripe.length;
    }

    return {
      serial, loadIndex, loadData, adopt, commit, gc,
      cid: () => cid, rev: () => rev,
      usage: () => ({ keys: info.keys, bytes: info.bytes, maxKeys: MAX_KEYS, percent: Math.min(100, Math.round(info.keys / MAX_KEYS * 100)) }),
    };
  }

  // ------------------------------------------------------------ saqlash joylari
  /** Telegram.WebApp.CloudStorage ni Promise ko'rinishiga o'tkazish. */
  function telegramBackend(cs, timeoutMs = 20000) {
    const call = (method, ...args) => new Promise((resolve, reject) => {
      let done = false;
      const timer = setTimeout(() => {
        if (!done) { done = true; reject(new Error("Telegram javob bermadi. Internetni tekshiring.")); }
      }, timeoutMs);
      try {
        cs[method](...args, (err, val) => {
          if (done) return;
          done = true;
          clearTimeout(timer);
          if (err) reject(new Error('Telegram bulutiga yozib bo\'lmadi: ' + err));
          else resolve(val);
        });
      } catch (e) {
        done = true;
        clearTimeout(timer);
        reject(e);
      }
    });
    return {
      get: async keys => (keys.length ? (await call('getItems', keys)) || {} : {}),
      set: async (k, v) => { if (!(await call('setItem', k, v))) throw new Error('Saqlanmadi: ' + k); },
      remove: async keys => { if (keys.length) await call('removeItems', keys); },
      keys: async () => (await call('getKeys')) || [],
    };
  }

  /**
   * Sinov uchun Telegram bulutining nusxasi (xuddi shu cheklovlar bilan).
   * persist — localStorage kabi obyekt berilsa, ma'lumot sahifa yangilansa ham qoladi.
   */
  function memoryBackend({ latency = 0, failAfter = Infinity, persist = null, prefix = 'mockcloud:' } = {}) {
    const map = new Map();
    if (persist) {
      for (let i = 0; i < persist.length; i++) {
        const k = persist.key(i);
        if (k && k.startsWith(prefix)) map.set(k.slice(prefix.length), persist.getItem(k));
      }
    }
    let ops = 0;
    const wait = () => new Promise(r => setTimeout(r, latency ? Math.random() * latency : 0));
    const tick = () => { if (++ops > failAfter) throw new Error('mock: tarmoq uzildi'); };
    const KEY_RE = /^[A-Za-z0-9_-]{1,128}$/;
    return {
      map,
      stats: () => ({ ops, keys: map.size }),
      setFailAfter: n => { failAfter = n; ops = 0; },
      async get(keys) {
        await wait(); tick();
        const out = {};
        for (const k of keys) { if (!KEY_RE.test(k)) throw new Error('mock: kalit noto\'g\'ri ' + k); out[k] = map.has(k) ? map.get(k) : ''; }
        return out;
      },
      async set(k, v) {
        await wait(); tick();
        if (!KEY_RE.test(k)) throw new Error('mock: kalit noto\'g\'ri ' + k);
        if (typeof v !== 'string' || v.length > MAX_VALUE || utf8Bytes(v) > MAX_VALUE) throw new Error('mock: qiymat juda uzun ' + k);
        if (!map.has(k) && map.size >= MAX_KEYS) throw new Error('mock: kalitlar soni 1024 dan oshdi');
        map.set(k, v);
        if (persist) persist.setItem(prefix + k, v);
      },
      async remove(keys) {
        await wait(); tick();
        for (const k of keys) { map.delete(k); if (persist) persist.removeItem(prefix + k); }
      },
      async keys() { await wait(); tick(); return [...map.keys()]; },
    };
  }

  // ------------------------------------------------------------ avtomatik saqlash
  /**
   * O'zgarishlarni yig'ib (debounce), bulutga navbat bilan yozadi.
   * mirror — telefondagi nusxa: ilova saqlanmasdan yopilsa, keyingi ochilishda yuboriladi.
   */
  function createSync({ store, db, mirror, onStatus = () => {}, onConflict = async () => {}, debounce = 600,
    setTimer = setTimeout, clearTimer = clearTimeout }) {
    let dirty = false, timer = null, running = null, fails = 0;

    function schedule(ms) {
      if (timer) clearTimer(timer);
      timer = setTimer(() => { timer = null; flush(); }, ms);
    }

    function markDirty() {
      dirty = true;
      mirror.save(db.streams(), store.cid(), true);
      onStatus('pending');
      if (!running) schedule(debounce);
    }

    function flush() {
      if (timer) { clearTimer(timer); timer = null; }
      if (running) return running;
      if (!dirty) return Promise.resolve();
      dirty = false;
      onStatus('saving');
      running = store.serial(() => store.commit(db.streams()))
        .then(r => {
          fails = 0;
          mirror.save(db.streams(), store.cid(), dirty);
          onStatus(dirty ? 'pending' : 'saved', r);
          return r;
        }, async e => {
          if (e && e.conflict) {
            dirty = false;
            await onConflict(e);
            return null;
          }
          dirty = true;
          fails++;
          onStatus('error', e);
          return null;
        })
        .finally(() => {
          running = null;
          if (dirty) schedule(fails ? Math.min(30000, 2000 * 2 ** (fails - 1)) : debounce);
        });
      return running;
    }

    return {
      markDirty, flush,
      busy: () => dirty || !!running || !!timer,
      pending: () => dirty || !!running,
    };
  }

  /** Telefondagi nusxa (localStorage). Har Telegram akkaunti uchun alohida. */
  function localMirror(storage, userKey) {
    const key = 'osh_mirror_' + userKey;
    return {
      read() {
        try { const v = storage && storage.getItem(key); return v ? JSON.parse(v) : null; } catch (e) { return null; }
      },
      save(streams, cid, pending) {
        try { if (storage) storage.setItem(key, JSON.stringify({ cid, pending: !!pending, streams, t: Date.now() })); }
        catch (e) { /* telefon xotirasi to'lgan — bulut asosiy */ }
      },
      clear() { try { if (storage) storage.removeItem(key); } catch (e) { /* yo'q */ } },
    };
  }

  return { createStore, createSync, telegramBackend, memoryBackend, localMirror, ConflictError, _t: { chunk, hash, utf8Bytes } };
});
