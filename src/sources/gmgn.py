from __future__ import annotations

import asyncio
import json
import logging
import os
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
    raw: Optional[dict] = None


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any) -> Optional[int]:
    try:
        return int(float(v)) if v is not None else None
    except (ValueError, TypeError):
        return None


class GmgnClient:
    """
    GMGN client. GMGN gak punya official public API, jadi endpoint dan
    header bisa diatur lewat env var:

      GMGN_BASE_URL          - base URL, default https://gmgn.ai
      GMGN_TOKEN_PATH        - path template untuk detail token. Default:
                               /defi/quotation/v1/tokens/sol/{address}
                               (placeholder {address} bakal di-replace)
      GMGN_API_KEY           - kalau lo punya API key, dikirim sebagai
                               header `X-API-Key` (atau sesuai GMGN_AUTH_HEADER)
      GMGN_AUTH_HEADER       - nama header untuk auth, default X-API-Key
      GMGN_COOKIE            - cookie raw (kalau pakai session-based auth)
      GMGN_USER_AGENT        - user agent override
      GMGN_EXTRA_HEADERS     - JSON object header tambahan, contoh:
                               '{"X-Foo":"bar"}'

    Field mapping di _parse() bisa diadjust sesuai shape response API lo.
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self.base = os.getenv("GMGN_BASE_URL", "https://gmgn.ai").rstrip("/")
        self.token_path = os.getenv(
            "GMGN_TOKEN_PATH", "/defi/quotation/v1/tokens/sol/{address}"
        )

        headers = {
            "User-Agent": os.getenv(
                "GMGN_USER_AGENT",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            ),
            "Accept": "application/json",
        }

        api_key = os.getenv("GMGN_API_KEY")
        if api_key:
            auth_header = os.getenv("GMGN_AUTH_HEADER", "X-API-Key")
            headers[auth_header] = api_key

        cookie = os.getenv("GMGN_COOKIE")
        if cookie:
            headers["Cookie"] = cookie

        extra = os.getenv("GMGN_EXTRA_HEADERS")
        if extra:
            try:
                headers.update(json.loads(extra))
            except json.JSONDecodeError:
                log.warning("GMGN_EXTRA_HEADERS bukan JSON yang valid, di-skip")

        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)
        self._sem = asyncio.Semaphore(int(os.getenv("GMGN_CONCURRENCY", "3")))

    async def close(self) -> None:
        await self._client.aclose()

    async def enrich(self, address: str) -> GmgnEnrichment:
        url = f"{self.base}{self.token_path.format(address=address)}"
        async with self._sem:
            try:
                r = await self._client.get(url)
                if r.status_code in (401, 403):
                    log.warning(
                        "GMGN auth gagal (%s). Set GMGN_API_KEY / GMGN_COOKIE.",
                        r.status_code,
                    )
                    return GmgnEnrichment()
                if r.status_code == 429:
                    log.warning("GMGN rate-limited")
                    return GmgnEnrichment()
                r.raise_for_status()
                return self._parse(r.json())
            except (httpx.HTTPError, json.JSONDecodeError) as e:
                log.debug("GMGN enrich %s gagal: %s", address, e)
                return GmgnEnrichment()

    def _parse(self, payload: dict) -> GmgnEnrichment:
        """
        Parse response. GMGN umumnya bungkus data di `data` dan kadang
        nested di bawah `token`. Field mapping di-extract dari beberapa
        kemungkinan key supaya tahan banting kalau shape sedikit beda.
        """
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if isinstance(data, dict) and "token" in data and isinstance(data["token"], dict):
            data = {**data, **data["token"]}

        return GmgnEnrichment(
            holders=_safe_int(
                data.get("holder_count")
                or data.get("holders")
                or data.get("holder")
            ),
            jupiter_fees_sol=_safe_float(
                data.get("jupiter_fees")
                or data.get("jupiter_fees_sol")
                or data.get("jup_fees")
                or data.get("total_jupiter_fees")
            ),
            top_10_holder_rate=_safe_float(
                data.get("top_10_holder_rate")
                or data.get("top10_holder_rate")
            ),
            smart_money_count=_safe_int(
                data.get("smart_money_count") or data.get("smart_count")
            ),
            raw=payload if os.getenv("GMGN_DEBUG") else None,
        )
