from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
import os
from datetime import datetime

app = FastAPI()

# --- Normalization helpers ---
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
LATIN_DIGITS   = "0123456789"
DIGIT_MAP = str.maketrans(PERSIAN_DIGITS, LATIN_DIGITS)

ALIASES = {
    "CD1GOB0001": "CD1G0B0001",  # O -> 0
    "cd1gob0001": "CD1G0B0001",
    "cd1g0b0001": "CD1G0B0001",
    "cd1sib0001": "CD1SIB0001",
}

def normalize_symbol(raw: str) -> str:
    s = (raw or "").strip().translate(DIGIT_MAP).upper()
    s = s.replace(" ", "").replace("‌", "")
    if s in ALIASES:
        return ALIASES[s]
    s = s.replace("CD1GOB0001", "CD1G0B0001")
    return s

# --- Allowed symbols ---
KNOWN = {
    "CD1G0B0001": {"name": "گواهی سپرده شمش طلا"},
    "CD1SIB0001": {"name": "گواهی سپرده نقره ۱ گرمی"},
}

API_KEY = os.getenv("API_KEY", "test-key")

# --- Middleware برای احراز هویت ---
@app.middleware("http")
async def check_api_key(request: Request, call_next):
    if request.url.path.startswith("/v1"):
        key = request.headers.get("x-api-key")
        if key != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
    return await call_next(request)

# --- اندپوینت تست سلامت ---
@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.utcnow()}

# --- اندپوینت اصلی قیمت ---
@app.get("/v1/price")
async def get_price(symbol: str, prefer: str = "chartix"):
    sym = normalize_symbol(symbol)

    if sym not in KNOWN:
        raise HTTPException(status_code=400, detail="Unknown symbol (allowlisted symbols only)")

    # اینجا به‌جای API واقعی، شبیه‌سازی پاسخ انجام می‌دهیم
    if sym == "CD1G0B0001":
        return {
            "symbol": sym,
            "lastPrice": 930000000,
            "currency": "IRR",
            "per": "coin",
            "unitDetails": "سکه امامی",
            "source": prefer,
            "fetchedAt": datetime.utcnow().isoformat()
        }

    if sym == "CD1SIB0001":
        return {
            "symbol": sym,
            "lastPrice": 73611,
            "currency": "IRR",
            "per": "unit",
            "unitDetails": "گواهی نقره ۱ گرم",
            "source": prefer,
            "fetchedAt": datetime.utcnow().isoformat()
        }

    raise HTTPException(status_code=502, detail="Could not fetch last price from {}/fallbacks".format(prefer))

# --- اجرای سرور ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
