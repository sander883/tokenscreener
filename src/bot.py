from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from .filters import Filter, FilterStore, resolve_field
from .formatter import EnrichedToken, format_alert, format_filter_summary
from .screener import Screener

log = logging.getLogger(__name__)

HELP_TEXT = (
    "🤖 *Token Screener Bot*\n\n"
    "Commands:\n"
    "• `/filter` — lihat filter aktif\n"
    "• `/setfilter <field> <value>` — ubah filter\n"
    "   contoh: `/setfilter volume 500000`\n"
    "   contoh: `/setfilter holders 1000`\n"
    "   contoh: `/setfilter mc_max 25000000`\n"
    "   contoh: `/setfilter smart_money 5`\n"
    "   contoh: `/setfilter rug 0.2`\n"
    "   contoh: `/setfilter fees off`  (matikan filter)\n"
    "• `/resetfilter` — kembalikan ke default\n"
    "• `/scan` — paksa scan sekarang juga\n"
    "• `/pause` & `/resume` — pause/lanjut auto-scan\n"
    "• `/help` — tampilkan bantuan\n\n"
    "Field yang bisa di-set:\n"
    "`volume`, `mc_min`, `mc_max`, `age`, `liquidity`, `holders`,\n"
    "`smart_money`, `rug`, `top10`, `txns`, `change`"
)


class ScreenerBot:
    def __init__(self) -> None:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
        self.filter_store = FilterStore()
        self.app: Application = ApplicationBuilder().token(token).build()
        self.screener = Screener(
            filter_store=self.filter_store,
            on_alert=self._send_alert,
            enable_gmgn=os.getenv("ENABLE_GMGN", "true").lower() == "true",
            poll_interval=int(os.getenv("POLL_INTERVAL", "60")),
        )
        self._paused = False
        self._screener_task: Optional[asyncio.Task] = None
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self.cmd_help))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("filter", self.cmd_filter))
        self.app.add_handler(CommandHandler("setfilter", self.cmd_setfilter))
        self.app.add_handler(CommandHandler("resetfilter", self.cmd_resetfilter))
        self.app.add_handler(CommandHandler("scan", self.cmd_scan))
        self.app.add_handler(CommandHandler("pause", self.cmd_pause))
        self.app.add_handler(CommandHandler("resume", self.cmd_resume))

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)

    async def cmd_filter(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(format_filter_summary(self.filter_store.current))

    async def cmd_setfilter(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if len(ctx.args) < 2:
            await update.message.reply_text(
                "Format: /setfilter <field> <value>\nContoh: /setfilter volume 500000"
            )
            return
        field = ctx.args[0]
        value = " ".join(ctx.args[1:])
        if resolve_field(field) is None:
            await update.message.reply_text(
                f"Field '{field}' tidak dikenal. Lihat /help untuk daftar field."
            )
            return
        try:
            new_filter = self.filter_store.update(field, value)
        except (ValueError, KeyError) as e:
            await update.message.reply_text(f"Error: {e}")
            return
        await update.message.reply_text(
            f"✅ Filter '{field}' diupdate.\n\n{format_filter_summary(new_filter)}"
        )

    async def cmd_resetfilter(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        new_filter = self.filter_store.reset()
        await update.message.reply_text(
            "🔄 Filter direset ke default.\n\n" + format_filter_summary(new_filter)
        )

    async def cmd_scan(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🔍 Scanning sekarang...")
        try:
            count = await self.screener.tick()
            await update.message.reply_text(f"Selesai. {count} token cocok filter.")
        except Exception as e:
            log.exception("manual scan failed")
            await update.message.reply_text(f"❌ Scan gagal: {e}")

    async def cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        self._paused = True
        self.screener.stop()
        await update.message.reply_text("⏸ Auto-scan paused. /resume untuk lanjut.")

    async def cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._paused:
            await update.message.reply_text("Auto-scan udah jalan.")
            return
        self._paused = False
        self.screener._stop.clear()  # type: ignore[attr-defined]
        self._screener_task = asyncio.create_task(self.screener.run_forever())
        await update.message.reply_text("▶️ Auto-scan resumed.")

    async def _send_alert(self, et: EnrichedToken, f: Filter) -> None:
        text = format_alert(et, f)
        await self.app.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            disable_web_page_preview=True,
        )

    async def _on_startup(self, app: Application) -> None:
        self._screener_task = asyncio.create_task(self.screener.run_forever())
        try:
            await app.bot.send_message(
                chat_id=self.chat_id,
                text="🤖 Token screener online. Ketik /help.",
            )
        except Exception:
            log.warning("Tidak bisa kirim pesan startup ke chat %s", self.chat_id)

    async def _on_shutdown(self, app: Application) -> None:
        self.screener.stop()
        if self._screener_task:
            try:
                await asyncio.wait_for(self._screener_task, timeout=5)
            except asyncio.TimeoutError:
                self._screener_task.cancel()
        await self.screener.close()

    def run(self) -> None:
        self.app.post_init = self._on_startup
        self.app.post_shutdown = self._on_shutdown
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
