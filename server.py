import os, re, asyncio
from datetime import datetime, timezone
from typing import Optional, Literal
import httpx
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

API_KEY = os.getenv("API_KEY", "change-me")

# نمادهای مجاز
KNOWN = {
    "CD1G0B0001": {"kind": "gold_cert", "unit": "0.1 g"},
    "CD1GOB0001": {"kind": "gold_cert", "unit": "0.1 g"},   # واریانت تایپی
    "CD1SIB0001": {"kind": "silver_cert", "unit": "1 g"},
}

# --- تنظیمات شبکه/هدرها ---
TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "25"))
RETRIES = int(os.getenv("UPSTREAM_RETRIES", "3"))

DEFAULT_HEADERS = {
    # User-Agent واقعی
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fa,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}

# پاکسازی ارقام فارسی/جداکننده‌ها
NUM_RE = re.compile(r"[^\d]")

def to_int(num_text: str) -> Optional[int]:
    if not num_text:
        return None
    persian = "۰۱۲۳۴۵۶۷۸۹"
    latin   = "0123456789"
    trans = str.maketrans("".join(persian), "".join(latin))
    s = num_text.translate(trans)
    s = NUM_RE.sub("", s)
    return int(s) if s else None

def extract_last_price(html: str) -> Optional[int]:
    # نزدیک «آخرین قیمت»
    m = re.search(r"آخرین\s*قیمت[^0-9]*([۰-۹0-9,٬\.]+)", html)
    if m and m.group(1):
        v = to_int(m.group(1))
        if v:
            return v
    # اولین عدد بزرگ (≥6 رقم)
    m2 = re.search(r"([۰-۹0-9][۰-۹0-9,٬\.]{5,})", html)
    if m2 and m2.group(1):
        return to_int(m2.group(1))
    return None

async def fetch_chartix(symbol: str) -> Optional[int]:
    # صفحه‌ی بازار بورس کالا
    url = f"https://chartix.ir/market/BOURSE_KALA/{symbol}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return extract_last_price(r.text)
    except Exception:
        return None

async def fetch_rahavard(symbol: str) -> Optional[int]:
    # صفحه‌ی جستجو
    url = f"https://rahavard365.com/search?q={symbol}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return extract_last_price(r.text)
    except Exception:
        return None

async def resolve_price(symbol: str, prefer: str = "rahavard") -> tuple[Optional[int], str]:
    sources = {"chartix": fetch_chartix, "rahavard": fetch_rahavard}
    order = [prefer] + [s for s in ("chartix", "rahavard") if s != prefer]
    for src in order:
        for _ in range(RETRIES):
            price = await sources[src](symbol)
            if price:
                return price, src
            await asyncio.sleep(0.8)
    return None, ""

class PriceResponse(BaseModel):
    symbol: str
    lastPrice: int
    currency: Literal["IRR"] = "IRR"
    per: str = "unit"
    unitDetails: Optional[str] = None
    source: str
    fetchedAt: str

app = FastAPI(title="Price Proxy (Gold/Silver Iran)", version="1.1.0")

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}

@app.get("/v1/price", response_model=PriceResponse)
async def get_price(
    symbol: str,
    prefer: Optional[Literal["chartix","rahavard"]] = "rahavard",
    x_api_key: str = Header(None, alias="X-API-Key")
):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    sym = symbol.strip()
    if sym not in KNOWN:
        raise HTTPException(status_code=400, detail="Unknown symbol (allowlisted symbols only)")

    price, src = await resolve_price(sym, prefer=prefer or "rahavard")
    if not price:
        raise HTTPException(status_code=502, detail=f"Could not fetch last price from {prefer}/fallbacks")

    unit_details = "گواهی طلا ۰٫۱ گرم" if KNOWN[sym]["kind"]=="gold_cert" else "گواهی نقره ۱ گرم"
    return PriceResponse(
        symbol=sym,
        lastPrice=price,
        currency="IRR",
        per="unit",
        unitDetails=unit_details,
        source=src,
        fetchedAt=datetime.now(timezone.utc).isoformat()
    )
