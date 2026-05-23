from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Awaitable, Callable, Iterable

from .filters import Filter, FilterStore
from .formatter import EnrichedToken
from .sources.dexscreener import DexScreenerClient, TokenSnapshot
from .sources.gmgn import GmgnClient, GmgnEnrichment

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
SEEN_FILE = DATA_DIR / "seen_tokens.json"
SEEN_TTL_SECONDS = 60 * 60 * 24  # 24 jam, biar gak spam token yang sama


def _passes_dex_only(s: TokenSnapshot, f: Filter) -> bool:
    """Filter awal pakai data DexScreener (cepet, gak butuh GMGN)."""
    if f.min_volume_h1 is not None and (s.volume_h1 or 0) < f.min_volume_h1:
        return False
    mc = s.market_cap or 0
    if f.min_market_cap is not None and mc < f.min_market_cap:
        return False
    if f.max_market_cap is not None and mc > f.max_market_cap:
        return False
    if f.max_age_days is not None:
        age = s.age_days
        if age is None or age > f.max_age_days:
            return False
    if f.min_liquidity is not None and (s.liquidity_usd or 0) < f.min_liquidity:
        return False
    if f.min_txns_h1 is not None and (s.txns_h1 or 0) < f.min_txns_h1:
        return False
    if f.min_price_change_h1_pct is not None and (
        s.price_change_h1 is None or s.price_change_h1 < f.min_price_change_h1_pct
    ):
        return False
    return True


def _passes_gmgn(en: GmgnEnrichment, f: Filter) -> bool:
    """Filter tambahan pakai data GMGN (holders, jupiter fees)."""
    if f.min_jupiter_fees_sol is not None:
        if en.jupiter_fees_sol is None or en.jupiter_fees_sol < f.min_jupiter_fees_sol:
            return False
    if f.min_holders is not None:
        if en.holders is None or en.holders < f.min_holders:
            return False
    return True


class SeenStore:
    """Track token addresses yang udah pernah di-alert biar gak duplicate."""

    def __init__(self, path: Path = SEEN_FILE) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, float] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text())
            except json.JSONDecodeError:
                self._data = {}
        self._prune()

    def _prune(self) -> None:
        cutoff = time.time() - SEEN_TTL_SECONDS
        self._data = {k: v for k, v in self._data.items() if v > cutoff}

    def seen(self, address: str) -> bool:
        return address in self._data

    def mark(self, address: str) -> None:
        self._data[address] = time.time()
        self._save()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data))


AlertCallback = Callable[[EnrichedToken, Filter], Awaitable[None]]


class Screener:
    def __init__(
        self,
        filter_store: FilterStore,
        on_alert: AlertCallback,
        enable_gmgn: bool = True,
        poll_interval: int = 60,
    ) -> None:
        self.filter_store = filter_store
        self.on_alert = on_alert
        self.enable_gmgn = enable_gmgn
        self.poll_interval = poll_interval
        self.dex = DexScreenerClient()
        self.gmgn = GmgnClient() if enable_gmgn else None
        self.seen = SeenStore()
        self._stop = asyncio.Event()

    async def close(self) -> None:
        await self.dex.close()
        if self.gmgn:
            await self.gmgn.close()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        log.info("Screener started (interval=%ss, gmgn=%s)", self.poll_interval, self.enable_gmgn)
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:  # jangan sampe loop mati gara2 error transient
                log.exception("tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> int:
        """Satu siklus: discover, filter, enrich, alert. Return jumlah alert dikirim."""
        f = self.filter_store.current
        snapshots = await self.dex.discover_candidates()
        log.info("Discovered %d candidates from DexScreener", len(snapshots))

        prefiltered = [s for s in snapshots if _passes_dex_only(s, f)]
        log.info("%d candidates passed dex-only filter", len(prefiltered))

        new_ones = [s for s in prefiltered if not self.seen.seen(s.address)]

        sent = 0
        for snap in new_ones:
            enrichment = GmgnEnrichment()
            if self.gmgn:
                enrichment = await self.gmgn.enrich(snap.address)

            if not _passes_gmgn(enrichment, f):
                # Token gagal di filter GMGN — jangan mark seen biar dicek
                # lagi kalau next tick holders/fees udah naik.
                continue

            et = EnrichedToken(snapshot=snap, enrichment=enrichment)
            try:
                await self.on_alert(et, f)
                self.seen.mark(snap.address)
                sent += 1
            except Exception:
                log.exception("alert callback failed for %s", snap.address)

        log.info("Tick done: %d alerts sent", sent)
        return sent
