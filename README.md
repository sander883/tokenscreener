# Token Screener Bot

Telegram bot yang screening token Solana dari DexScreener + GMGN dan kirim
notifikasi otomatis ketika token lolos filter yang lo set.

Default filter (sesuai gambar referensi):

- Volume 1H >= $400,000
- Market Cap $350,000 – $18,000,000
- Age <= 60 days
- Liquidity >= $10,000
- Total Jupiter Fees >= 24 SOL
- Holders >= 700

Semua filter bisa diubah lewat command `/setfilter` di chat.

---

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Bikin Telegram bot**

   - Chat ke [@BotFather](https://t.me/BotFather) → `/newbot` → ikutin instruksi.
   - Copy token-nya.
   - Chat ke bot lo sekali, lalu buka
     `https://api.telegram.org/bot<TOKEN>/getUpdates` untuk dapetin chat id.

3. **Bikin `.env`** (copy dari `.env.example`)

   ```bash
   cp .env.example .env
   ```

   Isi minimal:

   ```env
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_CHAT_ID=123456789
   POLL_INTERVAL=60
   ENABLE_GMGN=true
   ```

4. **(Opsional) Set GMGN API credentials**

   GMGN gak punya official public API. Kalau lo udah punya endpoint /
   credentials sendiri, set ini di `.env`:

   ```env
   # Base URL (default https://gmgn.ai)
   GMGN_BASE_URL=https://gmgn.ai

   # Path template untuk detail token. {address} akan di-replace.
   GMGN_TOKEN_PATH=/defi/quotation/v1/tokens/sol/{address}

   # Kalau ada API key
   GMGN_API_KEY=xxxxx
   GMGN_AUTH_HEADER=X-API-Key      # default

   # Atau pakai cookie session
   GMGN_COOKIE=cf_clearance=...; gmgn_session=...

   # Header tambahan custom (JSON)
   GMGN_EXTRA_HEADERS={"Origin":"https://gmgn.ai"}

   # Concurrency limit untuk request ke GMGN
   GMGN_CONCURRENCY=3
   ```

   Field mapping di `src/sources/gmgn.py::GmgnClient._parse()` udah handle
   beberapa nama field umum (`holder_count`, `jupiter_fees`, dll). Kalau
   response dari endpoint lo pakai nama field beda, edit `_parse()` sesuai
   shape JSON-nya.

5. **Jalanin**

   ```bash
   python main.py
   ```

---

## Cara pakai di Telegram

Kirim ke bot:

- `/help` — bantuan
- `/filter` — lihat filter aktif
- `/setfilter <field> <value>` — ubah filter, contoh:
  - `/setfilter volume 500000`
  - `/setfilter mc_min 1000000`
  - `/setfilter mc_max 25000000`
  - `/setfilter age 30`
  - `/setfilter liquidity 20000`
  - `/setfilter fees 50`
  - `/setfilter holders 1000`
  - `/setfilter fees off` (matikan filter ini)
- `/resetfilter` — reset ke default
- `/scan` — paksa scan sekarang juga
- `/pause` / `/resume` — pause/lanjut auto-scan

Filter di-persist ke `data/filters.json` jadi tetap ada setelah restart.

---

## Arsitektur

```
main.py                  → entrypoint, load env, start bot
src/bot.py               → Telegram handlers + lifecycle
src/screener.py          → loop scanning, dedupe, filter logic
src/filters.py           → Filter dataclass + persistence
src/formatter.py         → Format pesan alert (mirip Astra)
src/sources/dexscreener.py → DexScreener API client
src/sources/gmgn.py      → GMGN client (enrichment, configurable)
```

Flow tiap tick:

1. DexScreener: kumpulin kandidat dari `token-profiles`, `token-boosts`,
   dan search `SOL`/`USDC`.
2. Filter awal pakai data DexScreener (volume, mc, age, liquidity).
3. Untuk yang lolos, enrich pakai GMGN (holders, jupiter fees).
4. Cek filter GMGN. Yang lolos semua → kirim alert ke Telegram, mark sebagai
   "seen" selama 24 jam supaya gak duplicate.

## Catatan

- DexScreener rate limit ~300 req/min, bot ini hemat di bawah itu.
- GMGN endpoint unofficial dan sering kena Cloudflare. Kalau lo lihat warning
  "GMGN auth gagal" / "GMGN rate-limited" di log, atur credentials di `.env`.
- `data/seen_tokens.json` track token yang udah pernah di-alert. Hapus file
  itu kalau mau reset.
