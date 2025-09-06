# main.py
import os
import requests
from flask import Response, abort, request
from google.oauth2 import id_token
import google.auth.transport.requests as gar

TARGET = os.environ["TARGET_URL"].rstrip("/")
API_KEY = os.environ["API_KEY"]

def _id_token_for(audience: str) -> str:
    req = gar.Request()
    return id_token.fetch_id_token(req, audience)

def proxy(request):  # <-- entry point
    # Simple shared-key check from Make.com
    if request.headers.get("X-Api-Key") != API_KEY:
        abort(401, "Missing or invalid X-Api-Key")

    path = request.path.lstrip("/")
    url = f"{TARGET}/{path}"

    # Forward headers except host/authorization (we’ll add ID token)
    headers = {
        k: v for k, v in request.headers
        if k.lower() not in {"host", "authorization"}
    }
    headers["Authorization"] = f"Bearer {_id_token_for(TARGET)}"

    resp = requests.request(
        method=request.method,
        url=url,
        headers=headers,
        params=request.args,
        data=request.get_data(),
        timeout=60,
    )

    out = Response(resp.content, resp.status_code)
    for k, v in resp.headers.items():
        if k.lower() not in {"content-length","transfer-encoding","content-encoding","connection"}:
            out.headers[k] = v
    return out
