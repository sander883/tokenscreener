from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .filters import Filter
from .sources.dexscreener import TokenSnapshot
from .sources.gmgn import GmgnEnrichment


@dataclass
class EnrichedToken:
    snapshot: TokenSnapshot
    enrichment: GmgnEnrichment

    @property
    def holders(self) -> Optional[int]:
        return self.enrichment.holders

    @property
    def jupiter_fees_sol(self) -> Optional[float]:
        return self.enrichment.jupiter_fees_sol


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v:,.0f}"
    return f"${v:,.2f}"


def _fmt_age(days: Optional[float]) -> str:
    if days is None:
        return "n/a"
    if days < 1:
        return f"{days*24:.1f} hours"
    return f"{days:.2f} days"


def _fmt_num(v) -> str:
    if v is None:
        return "n/a"
    return f"{v:,}"


def _line(active: bool, text: str) -> str:
    return f"{'✅' if active else '❌'} {text}"


def format_alert(et: EnrichedToken, f: Filter) -> str:
    s = et.snapshot
    addr = s.address

    filter_lines = []
    if f.min_volume_h1 is not None:
        filter_lines.append(_line(
            (s.volume_h1 or 0) >= f.min_volume_h1,
            f"Volume 1H >= {_fmt_money(f.min_volume_h1)}",
        ))
    if f.min_market_cap is not None or f.max_market_cap is not None:
        lo = _fmt_money(f.min_market_cap) if f.min_market_cap is not None else "0"
        hi = _fmt_money(f.max_market_cap) if f.max_market_cap is not None else "∞"
        mc = s.market_cap or 0
        ok = (f.min_market_cap is None or mc >= f.min_market_cap) and (
            f.max_market_cap is None or mc <= f.max_market_cap
        )
        filter_lines.append(_line(ok, f"MC between {lo} - {hi}"))
    if f.max_age_days is not None:
        age = s.age_days
        filter_lines.append(_line(
            age is not None and age <= f.max_age_days,
            f"Age <= {f.max_age_days:g} days",
        ))
    if f.min_liquidity is not None:
        filter_lines.append(_line(
            (s.liquidity_usd or 0) >= f.min_liquidity,
            f"Liquidity >= {_fmt_money(f.min_liquidity)}",
        ))
    if f.min_jupiter_fees_sol is not None:
        filter_lines.append(_line(
            (et.jupiter_fees_sol or 0) >= f.min_jupiter_fees_sol,
            f"Jupiter Fees >= {f.min_jupiter_fees_sol:g} SOL",
        ))
    if f.min_holders is not None:
        filter_lines.append(_line(
            (et.holders or 0) >= f.min_holders,
            f"Holders >= {_fmt_num(f.min_holders)}",
        ))

    active_lines = []
    if f.min_volume_h1 is not None:
        active_lines.append(f"Volume 1H: >= {_fmt_money(f.min_volume_h1)}")
    if f.min_market_cap is not None or f.max_market_cap is not None:
        lo = _fmt_money(f.min_market_cap) if f.min_market_cap is not None else "0"
        hi = _fmt_money(f.max_market_cap) if f.max_market_cap is not None else "∞"
        active_lines.append(f"Market Cap: {lo} - {hi}")
    if f.max_age_days is not None:
        active_lines.append(f"Age: <= {f.max_age_days:g} days")
    if f.min_liquidity is not None:
        active_lines.append(f"Liquidity: >= {_fmt_money(f.min_liquidity)}")
    if f.min_jupiter_fees_sol is not None:
        active_lines.append(f"Jupiter Fees: >= {f.min_jupiter_fees_sol:g} SOL")
    if f.min_holders is not None:
        active_lines.append(f"Holders: >= {_fmt_num(f.min_holders)}")

    metrics_volume_h1 = _fmt_money(s.volume_h1) if s.volume_h1 is not None else "n/a"
    metrics_mc = _fmt_money(s.market_cap) if s.market_cap is not None else "n/a"
    metrics_liq = _fmt_money(s.liquidity_usd) if s.liquidity_usd is not None else "n/a"
    metrics_fees = (
        f"{et.jupiter_fees_sol:.2f} SOL" if et.jupiter_fees_sol is not None else "n/a"
    )
    metrics_holders = _fmt_num(et.holders) if et.holders is not None else "n/a"

    return (
        "🚀 ASTRA GMGN TOKEN PASSED FILTER\n\n"
        f"Token: {s.symbol} / {s.name}\n"
        f"CA: {addr}\n\n"
        "GMGN Metrics:\n"
        f"Volume 1H: {metrics_volume_h1}\n"
        f"Market Cap: {metrics_mc}\n"
        f"Age: {_fmt_age(s.age_days)}\n"
        f"Liquidity: {metrics_liq}\n"
        f"Total Jupiter Fees: {metrics_fees}\n"
        f"Holders: {metrics_holders}\n\n"
        "Filter:\n" + "\n".join(filter_lines) + "\n\n"
        "Active Filter:\n" + "\n".join(active_lines) + "\n\n"
        "Links:\n"
        f"GMGN:\nhttps://gmgn.ai/sol/token/{addr}\n"
        f"Dexscreener:\nhttps://dexscreener.com/solana/{addr}\n"
        f"Birdeye:\nhttps://birdeye.so/token/{addr}?chain=solana"
    )


def format_filter_summary(f: Filter) -> str:
    lines = ["📋 Active Filter:"]
    if f.min_volume_h1 is not None:
        lines.append(f"• Volume 1H >= {_fmt_money(f.min_volume_h1)}")
    if f.min_market_cap is not None or f.max_market_cap is not None:
        lo = _fmt_money(f.min_market_cap) if f.min_market_cap is not None else "0"
        hi = _fmt_money(f.max_market_cap) if f.max_market_cap is not None else "∞"
        lines.append(f"• Market Cap {lo} - {hi}")
    if f.max_age_days is not None:
        lines.append(f"• Age <= {f.max_age_days:g} days")
    if f.min_liquidity is not None:
        lines.append(f"• Liquidity >= {_fmt_money(f.min_liquidity)}")
    if f.min_jupiter_fees_sol is not None:
        lines.append(f"• Jupiter Fees >= {f.min_jupiter_fees_sol:g} SOL")
    if f.min_holders is not None:
        lines.append(f"• Holders >= {_fmt_num(f.min_holders)}")
    if f.min_txns_h1 is not None:
        lines.append(f"• Txns 1H >= {_fmt_num(f.min_txns_h1)}")
    if f.min_price_change_h1_pct is not None:
        lines.append(f"• Price change 1H >= {f.min_price_change_h1_pct:g}%")
    return "\n".join(lines)
