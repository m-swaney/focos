"""Zillow property values via RapidAPI (real-estate-zillow-com). Needs RAPIDAPI_KEY in .env."""
from __future__ import annotations

import os
import time

import httpx

from .. import settings  # noqa: F401  (loads .env)

HOST = "real-estate-zillow-com.p.rapidapi.com"


class ZillowClient:
    def __init__(self, key: str | None = None, timeout: float = 45.0):
        self.key = key or os.environ.get("RAPIDAPI_KEY")
        if not self.key:
            raise RuntimeError("RAPIDAPI_KEY not set")
        self._c = httpx.Client(base_url=f"https://{HOST}", timeout=timeout,
                               headers={"x-rapidapi-key": self.key, "x-rapidapi-host": HOST})

    def resolve_zpid(self, address: str) -> int | None:
        r = self._c.get("/v1/autocomplete", params={"query": address})
        r.raise_for_status()
        for item in ((r.json().get("data") or {}).get("results") or []):
            z = (item.get("metaData") or {}).get("zpid")
            if z:
                return int(z)
        return None

    def property(self, zpid: int) -> dict:
        r = self._c.get("/v1/property", params={"zpid_or_url": zpid})
        r.raise_for_status()
        body = r.json()
        data = body.get("data")
        if not data:
            raise RuntimeError(f"zillow property {zpid}: {body.get('description')}")
        return {
            "zpid": data.get("zpid"),
            "zestimate": data.get("zestimate"),
            "rent_zestimate": data.get("rentZestimate"),
            "tax_assessed_value": data.get("taxAssessedValue"),
            "last_sold_price": data.get("lastSoldPrice"),
            "home_status": data.get("homeStatus"),
            "bedrooms": data.get("bedrooms"),
            "bathrooms": data.get("bathrooms"),
            "living_area": data.get("livingArea"),
            "year_built": data.get("yearBuilt"),
            "address": data.get("streetAddress"),
        }

    def value(self, address: str | None = None, zpid: int | None = None) -> dict:
        if not zpid and address:
            zpid = self.resolve_zpid(address)
            time.sleep(1.0)
        if not zpid:
            raise RuntimeError(f"could not resolve zpid for {address}")
        return self.property(zpid)
