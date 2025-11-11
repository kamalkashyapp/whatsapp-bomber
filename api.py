# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import aiohttp
import asyncio
import os
from typing import List, Optional

app = FastAPI(title="Safe Async Demo API - Vercel")

class Target(BaseModel):
    url: HttpUrl
    method: Optional[str] = "POST"
    body: Optional[str] = None
    headers: Optional[dict] = None
    timeout: Optional[float] = 5.0

class SendRequest(BaseModel):
    phone: Optional[str] = None
    # If mode == "mock", we will ignore provided URLs and use httpbin test endpoints
    mode: Optional[str] = "mock"  # "mock" or "custom"
    targets: Optional[List[Target]] = None

@app.get("/")
async def root():
    return {"status": True, "message": "Safe Async Demo API — deployed on Vercel"}

async def _single_request(session: aiohttp.ClientSession, target: Target):
    method = target.method.upper()
    try:
        if method == "GET":
            async with session.get(str(target.url), headers=target.headers or {}, timeout=target.timeout) as resp:
                text = await resp.text()
                return {"url": str(target.url), "status": resp.status, "length": len(text)}
        elif method == "POST":
            # send as raw data (string) or empty
            async with session.post(str(target.url), headers=target.headers or {}, data=target.body or "", timeout=target.timeout) as resp:
                text = await resp.text()
                return {"url": str(target.url), "status": resp.status, "length": len(text)}
        else:
            return {"url": str(target.url), "error": f"Unsupported method {method}"}
    except Exception as e:
        return {"url": str(target.url), "error": str(e)}

@app.post("/send-test")
async def send_test(req: SendRequest):
    """
    Safe endpoint that demonstrates concurrent async requests.
    mode="mock" -> sends to httpbin.org endpoints (safe for testing)
    mode="custom" -> must include targets list (explicit URLs you want to hit)
    """
    if req.mode not in ("mock", "custom"):
        raise HTTPException(status_code=400, detail="mode must be 'mock' or 'custom'")

    # Build list of targets to hit
    targets = []
    if req.mode == "mock":
        # mock behavior: use httpbin test endpoints (safe)
        targets = [
            Target(url="https://httpbin.org/post", method="POST", body=f"phone={req.phone or 'unknown'}"),
            Target(url="https://httpbin.org/get", method="GET"),
            Target(url="https://httpbin.org/status/204", method="GET"),
        ]
    else:  # custom
        if not req.targets:
            raise HTTPException(status_code=400, detail="When mode='custom' you must provide a non-empty targets list")
        # simple safety: only allow custom targets when VERCEL_ALLOW_CUSTOM env is set to "1"
        if os.environ.get("VERCEL_ALLOW_CUSTOM") != "1":
            raise HTTPException(status_code=403, detail="Custom targets not allowed on this deployment. Set env VERCEL_ALLOW_CUSTOM=1 if you understand the risks.")
        targets = req.targets

    results = []
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [_single_request(session, t) for t in targets]
        responses = await asyncio.gather(*tasks, return_exceptions=False)
        results.extend(responses)

    return {"requested": len(targets), "results": results}
