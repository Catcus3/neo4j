# main.py

# --- Imports and environment setup ---
# Import required libraries for environment variables, HTTP requests, Flask, and Google authentication.
import os
import requests
from flask import Response, abort, request
from google.oauth2 import id_token
import google.auth.transport.requests as gar

# --- Target API and key configuration ---
# Read the target URL and API key from environment variables.
TARGET = os.environ["TARGET_URL"].rstrip("/")
API_KEY = os.environ["API_KEY"]

# --- Utility: Google ID token fetch ---
def _id_token_for(audience: str) -> str:
    # Fetches a Google Cloud ID token for the given audience (target URL).
    req = gar.Request()
    return id_token.fetch_id_token(req, audience)

# --- Proxy endpoint ---
def proxy(request):  # <-- entry point
    # Entry point for the proxy. Checks API key, forwards request to target, and returns response.

    # --- API key check ---
    # Simple shared-key check from Make.com
    if request.headers.get("X-Api-Key") != API_KEY:
        abort(401, "Missing or invalid X-Api-Key")

    # --- Build target URL ---
    path = request.path.lstrip("/")
    url = f"{TARGET}/{path}"

    # --- Forward headers ---
    # Forward all headers except host/authorization (add ID token)
    headers = {
        k: v for k, v in request.headers
        if k.lower() not in {"host", "authorization"}
    }
    headers["Authorization"] = f"Bearer {_id_token_for(TARGET)}"

    # --- Forward request ---
    resp = requests.request(
        method=request.method,
        url=url,
        headers=headers,
        params=request.args,
        data=request.get_data(),
        timeout=60,
    )

    # --- Build response ---
    out = Response(resp.content, resp.status_code)
    for k, v in resp.headers.items():
        # Forward all headers except those that can cause issues with Flask
        if k.lower() not in {"content-length","transfer-encoding","content-encoding","connection"}:
            out.headers[k] = v
    return out