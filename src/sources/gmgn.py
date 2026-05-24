from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


@dataclass
class GmgnEnrichment:
    """Data tambahan dari GMGN yang gak ada di DexScreener."""

    holders: Optional[int] = None
    jupiter_fees_sol: Optional[float] = None
    top_10_holder_rate: Optional[float] = None
    smart_money_count: Optional[int] = None
    volume_h1: Optional[float] = None
    market_cap: Optional[float] = None
    liquidity: Optional[float] = None
    rug_ratio: Optional[float] = None
    is_honeypot: Optional[bool] = None
    raw: Optional[dict] = None


@dataclass
class GmgnTrendingToken:
    """Token dari GMGN trending/market rank."""

    address: str
    symbol: str
    name: str
    price: Optional[float] = None
    market_cap: Optional[float] = None
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    holder_count: Optional[int] = None
    smart_degen_count: Optional[int] = None
    swaps: Optional[int] = None
    price_change_percent: Optional[float] = None
    rug_ratio: Optional[float] = None
    top_10_holder_rate: Optional[float] = None
    creation_timestamp: Optional[int] = None
    logo: Optional[str] = None
    twitter_username: Optional[str] = None
    website: Optional[str] = None
    raw: Optional[dict] = None


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> Optional[int]:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _safe_bool(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v == 1
    if isinstance(v, str):
        return v.lower() in ("true", "yes", "1")
    return None


class GmgnClient:
    """
    GMGN Official OpenAPI client.

    Menggunakan GMGN Agent API (https://openapi.gmgn.ai) untuk query
    data token secara real-time. Auth pakai API key + timestamp + client_id.

    Environment variables:
      GMGN_API_KEY           - API key dari https://gmgn.ai/ai (WAJIB)
      GMGN_CHAIN             - chain default, default 'sol'
      GMGN_CONCURRENCY       - max concurrent requests, default 5
      GMGN_DEBUG             - kalau di-set, simpan raw response di enrichment
    """

    BASE_URL = "https://openapi.gmgn.ai"

    def __init__(self, timeout: float = 15.0) -> None:
        self.api_key = os.getenv("GMGN_API_KEY", "")
        if not self.api_key:
            log.warning(
                "GMGN_API_KEY belum di-set! GMGN enrichment tidak akan berfungsi. "
                "Daftar di https://gmgn.ai/ai untuk dapatkan API key."
            )

        self.chain = os.getenv("GMGN_CHAIN", "sol")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "X-APIKEY": self.api_key,
                "Content-Type": "application/json",
            },
        )
        self._sem = asyncio.Semaphore(int(os.getenv("GMGN_CONCURRENCY", "5")))

    def _auth_params(self) -> dict[str, str]:
        """Generate auth query params: timestamp (unix seconds) + client_id (UUID)."""
        return {
            "timestamp": str(int(time.time())),
            "client_id": str(uuid.uuid4()),
        }

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Optional[dict]:
        """Make authenticated GET request to GMGN OpenAPI."""
        if not self.api_key:
            return None

        query = self._auth_params()
        if params:
            query.update({k: str(v) for k, v in params.items() if v is not None})

        url = f"{self.BASE_URL}{path}"

        async with self._sem:
            try:
                r = await self._client.get(url, params=query)

                if r.status_code == 429:
                    reset_at = r.headers.get("x-ratelimit-reset", "")
                    log.warning(
                        "GMGN rate-limited (429). Reset at: %s", reset_at or "unknown"
                    )
                    return None

                if r.status_code in (401, 403):
                    log.warning(
                        "GMGN auth gagal (%s). Pastikan GMGN_API_KEY sudah benar. "
                        "Daftar di https://gmgn.ai/ai",
                        r.status_code,
                    )
                    return None

                r.raise_for_status()
                data = r.json()

                # GMGN API returns {code: 0, data: {...}} on success
                # Some endpoints double-wrap: {code:0, data: {code:0, data: {...}}}
                if isinstance(data, dict):
                    code = data.get("code")
                    if code is not None and code != 0:
                        log.warning(
                            "GMGN API error: code=%s, message=%s",
                            code,
                            data.get("message", ""),
                        )
                        return None
                    inner = data.get("data", data)

                    # Handle double-wrapped responses
                    if isinstance(inner, dict) and "code" in inner and "data" in inner:
                        inner_code = inner.get("code")
                        if inner_code is not None and inner_code != 0:
                            log.warning(
                                "GMGN API inner error: code=%s, message=%s",
                                inner_code,
                                inner.get("message", ""),
                            )
                            return None
                        return inner.get("data", inner)

                    return inner

                return data

            except httpx.HTTPStatusError as e:
                log.debug("GMGN request failed (%s): HTTP %s", path, e.response.status_code)
                return None
            except (httpx.HTTPError, Exception) as e:
                log.debug("GMGN request failed (%s): %s", path, e)
                return None

    # ─── Token Info ─────────────────────────────────────────────────────

    async def get_token_info(self, address: str, chain: str | None = None) -> Optional[dict]:
        """Get token basic info (price, supply, holders, liquidity, etc)."""
        return await self._get(
            "/v1/token/info",
            {"chain": chain or self.chain, "address": address},
        )

    async def get_token_security(self, address: str, chain: str | None = None) -> Optional[dict]:
        """Get token security info (honeypot, rug ratio, taxes, etc)."""
        return await self._get(
            "/v1/token/security",
            {"chain": chain or self.chain, "address": address},
        )

    # ─── Market / Trending ──────────────────────────────────────────────

    async def get_trending(
        self,
        chain: str | None = None,
        interval: str = "1h",
        order_by: str = "volume",
        limit: int = 50,
        filters: list[str] | None = None,
    ) -> list[GmgnTrendingToken]:
        """
        Get trending tokens dari GMGN market rank.

        Args:
            chain: blockchain (sol/bsc/base/eth)
            interval: time window (1m/5m/1h/6h/24h)
            order_by: sort field (volume/swaps/marketcap/smart_degen_count/etc)
            limit: max results (max 100)
            filters: filter tags (e.g. ['renounced', 'frozen'])
        """
        params: dict[str, Any] = {
            "chain": chain or self.chain,
            "interval": interval,
            "order_by": order_by,
            "limit": limit,
        }
        if filters:
            params["filter"] = ",".join(filters)

        data = await self._get("/v1/market/rank", params)
        if not data:
            return []

        # Response: data.rank is array of tokens
        rank_list = data.get("rank", []) if isinstance(data, dict) else []
        if not isinstance(rank_list, list):
            return []

        tokens: list[GmgnTrendingToken] = []
        for item in rank_list:
            if not isinstance(item, dict):
                continue
            address = item.get("address")
            if not address:
                continue

            tokens.append(GmgnTrendingToken(
                address=address,
                symbol=item.get("symbol", "?"),
                name=item.get("name", "?"),
                price=_safe_float(item.get("price")),
                market_cap=_safe_float(item.get("market_cap")),
                liquidity=_safe_float(item.get("liquidity")),
                volume=_safe_float(item.get("volume")),
                holder_count=_safe_int(item.get("holder_count")),
                smart_degen_count=_safe_int(item.get("smart_degen_count")),
                swaps=_safe_int(item.get("swaps")),
                price_change_percent=_safe_float(item.get("price_change_percent")),
                rug_ratio=_safe_float(item.get("rug_ratio")),
                top_10_holder_rate=_safe_float(item.get("top_10_holder_rate")),
                creation_timestamp=_safe_int(item.get("creation_timestamp")),
                logo=item.get("logo"),
                twitter_username=item.get("twitter_username"),
                website=item.get("website"),
                raw=item if os.getenv("GMGN_DEBUG") else None,
            ))

        return tokens

    # ─── Enrich (for screener compatibility) ────────────────────────────

    async def enrich(self, address: str, chain: str | None = None) -> GmgnEnrichment:
        """
        Enrich token data dari GMGN. Mengambil token info + security.
        Digunakan oleh screener untuk filter tambahan (holders, smart money, dll).
        """
        chain = chain or self.chain

        # Fetch token info dan security secara parallel
        info_task = self.get_token_info(address, chain)
        security_task = self.get_token_security(address, chain)

        info_data, security_data = await asyncio.gather(
            info_task, security_task, return_exceptions=True
        )

        # Handle exceptions dari gather
        if isinstance(info_data, Exception):
            log.debug("GMGN token info failed for %s: %s", address, info_data)
            info_data = None
        if isinstance(security_data, Exception):
            log.debug("GMGN token security failed for %s: %s", address, security_data)
            security_data = None

        return self._parse_enrichment(info_data, security_data)

    def _parse_enrichment(
        self, info_data: Optional[dict], security_data: Optional[dict]
    ) -> GmgnEnrichment:
        """Parse combined token info + security response into GmgnEnrichment."""
        holders: Optional[int] = None
        top_10_holder_rate: Optional[float] = None
        smart_money_count: Optional[int] = None
        volume_h1: Optional[float] = None
        market_cap: Optional[float] = None
        liquidity: Optional[float] = None
        rug_ratio: Optional[float] = None
        is_honeypot: Optional[bool] = None

        if info_data and isinstance(info_data, dict):
            # holder_count bisa di top-level atau di stat
            holders = _safe_int(
                info_data.get("holder_count")
                or (info_data.get("stat") or {}).get("holder_count")
            )

            # Top 10 holder rate
            top_10_holder_rate = _safe_float(
                (info_data.get("stat") or {}).get("top_10_holder_rate")
                or (info_data.get("dev") or {}).get("top_10_holder_rate")
            )

            # Smart money count dari wallet_tags_stat
            wallet_tags = info_data.get("wallet_tags_stat") or {}
            smart_money_count = _safe_int(wallet_tags.get("smart_wallets"))

            # Price & volume dari price object
            price_obj = info_data.get("price") or {}
            if isinstance(price_obj, dict):
                volume_h1 = _safe_float(price_obj.get("volume_1h"))

            # Liquidity
            liquidity = _safe_float(info_data.get("liquidity"))

            # Market cap = price * circulating_supply
            price_val = _safe_float(
                price_obj.get("price") if isinstance(price_obj, dict) else None
            )
            circ_supply = _safe_float(info_data.get("circulating_supply"))
            if price_val and circ_supply:
                market_cap = price_val * circ_supply

        if security_data and isinstance(security_data, dict):
            rug_ratio = _safe_float(security_data.get("rug_ratio"))
            is_honeypot = _safe_bool(security_data.get("is_honeypot"))

            # Fallback top_10_holder_rate from security if not found in info
            if top_10_holder_rate is None:
                top_10_holder_rate = _safe_float(
                    security_data.get("top_10_holder_rate")
                )

        raw = None
        if os.getenv("GMGN_DEBUG"):
            raw = {"info": info_data, "security": security_data}

        return GmgnEnrichment(
            holders=holders,
            jupiter_fees_sol=None,  # Not available via GMGN API
            top_10_holder_rate=top_10_holder_rate,
            smart_money_count=smart_money_count,
            volume_h1=volume_h1,
            market_cap=market_cap,
            liquidity=liquidity,
            rug_ratio=rug_ratio,
            is_honeypot=is_honeypot,
            raw=raw,
        )
