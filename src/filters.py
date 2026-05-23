from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
FILTER_FILE = DATA_DIR / "filters.json"


@dataclass
class Filter:
    """Filter konfigurasi untuk screening token. Semua field opsional —
    kalau None artinya filter tidak aktif."""

    min_volume_h1: Optional[float] = 400_000
    min_market_cap: Optional[float] = 350_000
    max_market_cap: Optional[float] = 18_000_000
    max_age_days: Optional[float] = 60
    min_liquidity: Optional[float] = 10_000
    min_jupiter_fees_sol: Optional[float] = 24
    min_holders: Optional[int] = 700

    # Field opsional tambahan (bisa diaktifin nanti)
    min_txns_h1: Optional[int] = None
    min_price_change_h1_pct: Optional[float] = None
    chain: str = "solana"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Filter":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


# Field-field yang bisa di-set via /setfilter
FIELD_ALIASES = {
    "volume": "min_volume_h1",
    "vol": "min_volume_h1",
    "volume_h1": "min_volume_h1",
    "min_mc": "min_market_cap",
    "mc_min": "min_market_cap",
    "mc_max": "max_market_cap",
    "max_mc": "max_market_cap",
    "age": "max_age_days",
    "age_days": "max_age_days",
    "liq": "min_liquidity",
    "liquidity": "min_liquidity",
    "fees": "min_jupiter_fees_sol",
    "jupiter_fees": "min_jupiter_fees_sol",
    "holders": "min_holders",
    "txns": "min_txns_h1",
    "change": "min_price_change_h1_pct",
}


def resolve_field(name: str) -> Optional[str]:
    name = name.lower().strip()
    if name in Filter.__dataclass_fields__:
        return name
    return FIELD_ALIASES.get(name)


@dataclass
class FilterStore:
    """Persistensi filter ke JSON file biar config tetap ada setelah restart."""

    path: Path = field(default_factory=lambda: FILTER_FILE)
    _filter: Filter = field(default_factory=Filter)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                self._filter = Filter.from_dict(json.loads(self.path.read_text()))
            except (json.JSONDecodeError, TypeError):
                pass

    @property
    def current(self) -> Filter:
        return self._filter

    def update(self, field_name: str, value) -> Filter:
        resolved = resolve_field(field_name)
        if resolved is None:
            raise KeyError(f"Field '{field_name}' tidak dikenal")

        if value in (None, "off", "none", "null"):
            parsed = None
        else:
            current = getattr(self._filter, resolved)
            target_type = type(current) if current is not None else float
            if target_type is int:
                parsed = int(float(value))
            elif target_type is float:
                parsed = float(value)
            else:
                parsed = value

        setattr(self._filter, resolved, parsed)
        self._save()
        return self._filter

    def reset(self) -> Filter:
        self._filter = Filter()
        self._save()
        return self._filter

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._filter.to_dict(), indent=2))
