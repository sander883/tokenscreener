"""Inline keyboard menus untuk /settings command."""
from __future__ import annotations

from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .filters import Filter

# ─── Callback data prefixes ──────────────────────────────────────────────
# nav:<page>           → navigate ke menu page
# set:<field>:<value>  → set filter field (value="off" untuk matiin)
# tog:<key>            → toggle boolean setting
# act:<action>         → trigger action (scan, reset, pause, resume)
# nop                  → no-op (header buttons)
# close                → tutup menu


def _btn(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data)


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "off"
    if v >= 1_000_000:
        return f"${v/1_000_000:g}M"
    if v >= 1_000:
        return f"${v/1_000:g}K"
    return f"${v:g}"


def _mark(active: bool) -> str:
    return "● " if active else ""


def _preset_row(field: str, current, presets: list[tuple[str, object]]) -> list[list[InlineKeyboardButton]]:
    """Render preset value buttons. Mark currently-selected value with bullet."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for label, value in presets:
        is_current = (value is None and current is None) or (
            value is not None and current is not None and float(value) == float(current)
        )
        row.append(_btn(f"{_mark(is_current)}{label}", f"set:{field}:{value if value is not None else 'off'}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


# ─── Header text builders ────────────────────────────────────────────────

def header_main(f: Filter, enable_gmgn: bool, paused: bool, poll_interval: int) -> str:
    src_dex = "✅"
    src_gmgn = "✅" if enable_gmgn else "❌"
    scan = "paused" if paused else f"every {poll_interval}s"
    return (
        "⚙️ *Settings Menu*\n\n"
        f"Mode: SOL | Auto-scan: {scan}\n"
        f"Sources: DexScreener {src_dex} | GMGN {src_gmgn}\n"
        f"Chain: {f.chain}\n\n"
        f"Volume 1H: {_fmt_money(f.min_volume_h1)}\n"
        f"MC: {_fmt_money(f.min_market_cap)} - {_fmt_money(f.max_market_cap)}\n"
        f"Age: {f.max_age_days if f.max_age_days else 'off'}d | "
        f"Liq: {_fmt_money(f.min_liquidity)}\n"
        f"Holders: {f.min_holders if f.min_holders else 'off'} | "
        f"Smart$: {f.min_smart_money if f.min_smart_money is not None else 'off'}\n"
        f"Rug: {f.max_rug_ratio if f.max_rug_ratio is not None else 'off'} | "
        f"Top10: {f.max_top_10_holder_rate if f.max_top_10_holder_rate is not None else 'off'}"
    )


def header_screen(f: Filter) -> str:
    return (
        "🔍 *Screen Filters* (DexScreener data)\n\n"
        "Tap field untuk ubah:"
    )


def header_gmgn(f: Filter) -> str:
    return (
        "🟢 *GMGN Filters*\n\n"
        "Tap field untuk ubah:"
    )


def header_sources(enable_gmgn: bool) -> str:
    return (
        "📡 *Data Sources*\n\n"
        f"DexScreener: ✅ (always on)\n"
        f"GMGN: {'✅ on' if enable_gmgn else '❌ off'}\n\n"
        "GMGN dipakai untuk enrich holders, smart money, rug ratio, "
        "dan honeypot check. Matiin kalau lo gak punya API key atau "
        "mau lebih banyak hit (filter GMGN otomatis di-skip)."
    )


def header_config(f: Filter) -> str:
    lines = ["📄 *Full Config*\n"]
    for k, v in f.to_dict().items():
        lines.append(f"`{k}`: `{v}`")
    return "\n".join(lines)


# ─── Keyboard builders ───────────────────────────────────────────────────

def kb_main(enable_gmgn: bool, paused: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("🔍 Screen", "nav:screen"), _btn("🟢 GMGN", "nav:gmgn")],
        [_btn("📡 Sources", "nav:sources"), _btn("📄 Show Config", "nav:config")],
        [
            _btn(f"Auto-scan: {'⏸ off' if paused else '▶️ on'}",
                 f"tog:{'resume' if paused else 'pause'}"),
            _btn("🔎 Scan Now", "act:scan"),
        ],
        [_btn("🔄 Reset Filter", "act:reset"), _btn("❌ Close", "close")],
    ])


def kb_screen(f: Filter) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn(f"Volume 1H: {_fmt_money(f.min_volume_h1)}", "nav:p_volume"),
            _btn(f"MC Min: {_fmt_money(f.min_market_cap)}", "nav:p_mc_min"),
        ],
        [
            _btn(f"MC Max: {_fmt_money(f.max_market_cap)}", "nav:p_mc_max"),
            _btn(f"Age: {f.max_age_days if f.max_age_days else 'off'}d", "nav:p_age"),
        ],
        [
            _btn(f"Liquidity: {_fmt_money(f.min_liquidity)}", "nav:p_liq"),
            _btn(f"Txns 1H: {f.min_txns_h1 if f.min_txns_h1 else 'off'}", "nav:p_txns"),
        ],
        [_btn("← Back", "nav:main"), _btn("❌ Close", "close")],
    ])


def kb_gmgn(f: Filter) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn(f"Holders: {f.min_holders if f.min_holders else 'off'}", "nav:p_holders"),
            _btn(f"Smart$: {f.min_smart_money if f.min_smart_money is not None else 'off'}", "nav:p_smart"),
        ],
        [
            _btn(f"Rug: {f.max_rug_ratio if f.max_rug_ratio is not None else 'off'}", "nav:p_rug"),
            _btn(f"Top10: {f.max_top_10_holder_rate if f.max_top_10_holder_rate is not None else 'off'}", "nav:p_top10"),
        ],
        [_btn("← Back", "nav:main"), _btn("❌ Close", "close")],
    ])


def kb_sources(enable_gmgn: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn(f"GMGN: {'✅ on' if enable_gmgn else '❌ off'} (tap to toggle)", "tog:gmgn")],
        [_btn("← Back", "nav:main"), _btn("❌ Close", "close")],
    ])


def kb_config() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("← Back", "nav:main"), _btn("❌ Close", "close")],
    ])


# ─── Preset menus ────────────────────────────────────────────────────────

PRESETS_VOLUME = [
    ("$100K", 100_000), ("$250K", 250_000), ("$400K", 400_000),
    ("$500K", 500_000), ("$1M", 1_000_000), ("$2M", 2_000_000),
    ("Off", None),
]
PRESETS_MC_MIN = [
    ("$100K", 100_000), ("$250K", 250_000), ("$350K", 350_000),
    ("$500K", 500_000), ("$1M", 1_000_000), ("Off", None),
]
PRESETS_MC_MAX = [
    ("$5M", 5_000_000), ("$10M", 10_000_000), ("$18M", 18_000_000),
    ("$25M", 25_000_000), ("$50M", 50_000_000), ("Off", None),
]
PRESETS_AGE = [
    ("1d", 1), ("3d", 3), ("7d", 7),
    ("14d", 14), ("30d", 30), ("60d", 60),
    ("90d", 90), ("180d", 180), ("Off", None),
]
PRESETS_LIQ = [
    ("$5K", 5_000), ("$10K", 10_000), ("$25K", 25_000),
    ("$50K", 50_000), ("$100K", 100_000), ("Off", None),
]
PRESETS_TXNS = [
    ("50", 50), ("100", 100), ("250", 250),
    ("500", 500), ("1000", 1000), ("Off", None),
]
PRESETS_HOLDERS = [
    ("100", 100), ("300", 300), ("500", 500),
    ("700", 700), ("1000", 1000), ("2000", 2000),
    ("5000", 5000), ("Off", None),
]
PRESETS_SMART = [
    ("0", 0), ("1", 1), ("3", 3),
    ("5", 5), ("10", 10), ("20", 20),
    ("Off", None),
]
PRESETS_RUG = [
    ("10%", 0.1), ("20%", 0.2), ("30%", 0.3),
    ("50%", 0.5), ("80%", 0.8), ("Off", None),
]
PRESETS_TOP10 = [
    ("30%", 0.3), ("40%", 0.4), ("50%", 0.5),
    ("70%", 0.7), ("Off", None),
]


# Map preset-page name → (field name in Filter, header label, preset list, back page)
PRESET_PAGES: dict[str, tuple[str, str, list, str]] = {
    "p_volume":  ("min_volume_h1",         "Volume 1H minimum",   PRESETS_VOLUME,  "screen"),
    "p_mc_min":  ("min_market_cap",        "Market Cap minimum",  PRESETS_MC_MIN,  "screen"),
    "p_mc_max":  ("max_market_cap",        "Market Cap maximum",  PRESETS_MC_MAX,  "screen"),
    "p_age":     ("max_age_days",          "Max age (days)",      PRESETS_AGE,     "screen"),
    "p_liq":     ("min_liquidity",         "Min liquidity",       PRESETS_LIQ,     "screen"),
    "p_txns":    ("min_txns_h1",           "Min txns 1H",         PRESETS_TXNS,    "screen"),
    "p_holders": ("min_holders",           "Min holders",         PRESETS_HOLDERS, "gmgn"),
    "p_smart":   ("min_smart_money",       "Min smart money",     PRESETS_SMART,   "gmgn"),
    "p_rug":     ("max_rug_ratio",         "Max rug ratio",       PRESETS_RUG,     "gmgn"),
    "p_top10":   ("max_top_10_holder_rate","Max top-10 holder %", PRESETS_TOP10,   "gmgn"),
}


def header_preset(page: str, f: Filter) -> str:
    field, label, _, _ = PRESET_PAGES[page]
    current = getattr(f, field)
    return f"🎯 *{label}*\n\nCurrent: `{current if current is not None else 'off'}`"


def kb_preset(page: str, f: Filter) -> InlineKeyboardMarkup:
    field, _, presets, back = PRESET_PAGES[page]
    current = getattr(f, field)
    rows = _preset_row(field, current, presets)
    rows.append([_btn("← Back", f"nav:{back}"), _btn("❌ Close", "close")])
    return InlineKeyboardMarkup(rows)
