from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import httpx

log = logging.getLogger(__name__)

BASE = "https://api.dexscreener.com"


@dataclass
class TokenSnapshot:
    """Snapshot data 1 token dari DexScreener (pair terbaik)."""

    chain: str
    address: str
    pair_address: str
    symbol: str
    name: str
    price_usd: Optional[float]
    market_cap: Optional[float]
    fdv: Optional[float]
    liquidity_usd: Optional[float]
    volume_h1: Optional[float]
    volume_h24: Optional[float]
    txns_h1: Optional[int]
    price_change_h1: Optional[float]
    pair_created_at_ms: Optional[int]
    dex: str

    @property
    def age_days(self) -> Optional[float]:
        if not self.pair_created_at_ms:
            return None
        return (time.time() * 1000 - self.pair_created_at_ms) / (1000 * 60 * 60 * 24)


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _best_pair(pairs: list[dict]) -> Optional[dict]:
    """Pilih pair dengan liquidity tertinggi (proxy untuk pair utama)."""
    if not pairs:
        return None
    return max(
        pairs,
        key=lambda p: _safe_float((p.get("liquidity") or {}).get("usd")) or 0,
    )


def _pair_to_snapshot(pair: dict) -> Optional[TokenSnapshot]:
    base = pair.get("baseToken") or {}
    address = base.get("address")
    if not address:
        return None

    txns = (pair.get("txns") or {}).get("h1") or {}
    txns_h1 = (_safe_int(txns.get("buys")) or 0) + (_safe_int(txns.get("sells")) or 0)

    return TokenSnapshot(
        chain=pair.get("chainId", "solana"),
        address=address,
        pair_address=pair.get("pairAddress", ""),
        symbol=base.get("symbol", "?"),
        name=base.get("name", "?"),
        price_usd=_safe_float(pair.get("priceUsd")),
        market_cap=_safe_float(pair.get("marketCap")) or _safe_float(pair.get("fdv")),
        fdv=_safe_float(pair.get("fdv")),
        liquidity_usd=_safe_float((pair.get("liquidity") or {}).get("usd")),
        volume_h1=_safe_float((pair.get("volume") or {}).get("h1")),
        volume_h24=_safe_float((pair.get("volume") or {}).get("h24")),
        txns_h1=txns_h1 if txns_h1 else None,
        price_change_h1=_safe_float((pair.get("priceChange") or {}).get("h1")),
        pair_created_at_ms=_safe_int(pair.get("pairCreatedAt")),
        dex=pair.get("dexId", ""),
    )


class DexScreenerClient:
    def __init__(self, chain: str = "solana", timeout: float = 15.0) -> None:
        self.chain = chain
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "tokenscreener/1.0"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str) -> Optional[dict]:
        try:
            r = await self._client.get(f"{BASE}{path}")
            if r.status_code == 429:
                log.warning("DexScreener rate-limited on %s", path)
                return None
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            log.warning("DexScreener request failed (%s): %s", path, e)
            return None

    async def latest_profiles(self) -> list[str]:
        """Token addresses yang baru bikin profile (proxy untuk token baru/aktif)."""
        data = await self._get("/token-profiles/latest/v1")
        if not data:
            return []
        items = data if isinstance(data, list) else []
        return [
            item["tokenAddress"]
            for item in items
            if item.get("chainId") == self.chain and item.get("tokenAddress")
        ]

    async def latest_boosts(self) -> list[str]:
        data = await self._get("/token-boosts/latest/v1")
        if not data:
            return []
        items = data if isinstance(data, list) else []
        return [
            item["tokenAddress"]
            for item in items
            if item.get("chainId") == self.chain and item.get("tokenAddress")
        ]

    async def top_boosts(self) -> list[str]:
        data = await self._get("/token-boosts/top/v1")
        if not data:
            return []
        items = data if isinstance(data, list) else []
        return [
            item["tokenAddress"]
            for item in items
            if item.get("chainId") == self.chain and item.get("tokenAddress")
        ]

    async def get_tokens(self, addresses: Iterable[str]) -> list[TokenSnapshot]:
        """Ambil snapshot untuk batch token. DexScreener support max 30 per request."""
        snapshots: list[TokenSnapshot] = []
        addrs = [a for a in addresses if a]
        for i in range(0, len(addrs), 30):
            batch = addrs[i : i + 30]
            data = await self._get(f"/latest/dex/tokens/{','.join(batch)}")
            if not data:
                continue
            pairs_by_token: dict[str, list[dict]] = {}
            for p in data.get("pairs") or []:
                if p.get("chainId") != self.chain:
                    continue
                addr = (p.get("baseToken") or {}).get("address")
                if addr:
                    pairs_by_token.setdefault(addr, []).append(p)
            for addr in batch:
                best = _best_pair(pairs_by_token.get(addr, []))
                if best:
                    snap = _pair_to_snapshot(best)
                    if snap:
                        snapshots.append(snap)
        return snapshots

    async def search(self, query: str) -> list[TokenSnapshot]:
        data = await self._get(f"/latest/dex/search?q={query}")
        if not data:
            return []
        snapshots: list[TokenSnapshot] = []
        by_token: dict[str, list[dict]] = {}
        for p in data.get("pairs") or []:
            if p.get("chainId") != self.chain:
                continue
            addr = (p.get("baseToken") or {}).get("address")
            if addr:
                by_token.setdefault(addr, []).append(p)
        for addr, pairs in by_token.items():
            best = _best_pair(pairs)
            if best:
                snap = _pair_to_snapshot(best)
                if snap:
                    snapshots.append(snap)
        return snapshots

    async def discover_candidates(self) -> list[TokenSnapshot]:
        """Gabungin profile + boost + search trending untuk dapetin kandidat token."""
        seen: set[str] = set()
        addresses: list[str] = []
        for src in (self.latest_profiles, self.latest_boosts, self.top_boosts):
            for addr in await src():
                if addr not in seen:
                    seen.add(addr)
                    addresses.append(addr)

        snapshots = await self.get_tokens(addresses)

        # Tambah hasil search untuk pasangan utama Solana
        for q in ("SOL", "USDC"):
            for snap in await self.search(q):
                if snap.address not in seen:
                    seen.add(snap.address)
                    snapshots.append(snap)
        return snapshots
