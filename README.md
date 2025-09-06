# Context

OnRev exposes a **FastAPI** app that writes `Person`, `AdCampaign`, and `Clicked_on` data into **Neo4j**. In Google Cloud, the app is fronted by a signed proxy and an API Gateway so external tools (e.g., **Make.com**) can call it safely with just an API key.

**Overall architecture**

* **Cloud Run – `onrev-api`**
	Containerized FastAPI service talking to Neo4j (AuraDB or self-hosted) using env vars:
	`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.

* **Cloud Functions (Gen2) – `onrev-proxy`**
	Forwards requests to Cloud Run using an **ID token** (audience = Cloud Run URL) and adds a shared secret header `x-api-key`. Runs as SA **`onrev-proxy-sa`**.

* **API Gateway – `onrev-gw`**
	Public HTTPS hostname (e.g., `https://<gw>.gateway.dev`) that requires `?key=<GatewayKey>`. Gateway calls the proxy as SA **`onrev-gw-sa`**. You manage routes with a Swagger v2 file (e.g., `onrev-gw-v2.yaml`).

* **Make.com**
	Calls `https://<gw>.gateway.dev/<endpoint>?key=<GatewayKey>` with header `x-api-key: <FunctionHeaderKey>`. API already tolerates missing UTM fields (falls back to `Unknown`/generated ids).

**Auth chain**

`Make.com (API key) → API Gateway (GW SA) → Cloud Function Proxy (Proxy SA + ID Token) → Cloud Run (checks audience + x-api-key) → FastAPI → Neo4j`

---

## How it runs on GCP

1. **App** runs in **Cloud Run** and reads Neo4j env vars.
2. **Proxy** runs in **Cloud Functions Gen2**, mints an **ID token** for the Cloud Run URL, and forwards requests, attaching `x-api-key`.
3. **API Gateway** exposes a public URL, validates `?key=...`, and uses its **service account** to invoke the proxy.
4. **Make.com** hits the Gateway URL (query param key + header).
   API handles blank/missing UTM values by defaulting to `"Unknown"` and generating a stable id.
---

## Commands on terminal

> Use **PowerShell** (Windows) or bash on macOS/Linux. Replace the bracketed placeholders.

### 0) Project and services

```powershell
$PROJECT_ID = "<project-id>"
$REGION     = "europe-west2"

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com cloudfunctions.googleapis.com `
	apigateway.googleapis.com servicemanagement.googleapis.com servicecontrol.googleapis.com `
	apikeys.googleapis.com
```

### 1) Deploy the FastAPI app to Cloud Run (from the `onrev/` folder)

```powershell
cd <repo>/onrev
gcloud run deploy onrev-api --region=$REGION --source=.

# Neo4j config (Aura example)
$NEO4J_URI      = "neo4j+s://<aura-id>.databases.neo4j.io"
$NEO4J_USERNAME = "neo4j"
$NEO4J_PASSWORD = "<password>"
$NEO4J_DATABASE = "neo4j"

gcloud run services update onrev-api --region=$REGION `
	--set-env-vars "NEO4J_URI=$NEO4J_URI,NEO4J_USERNAME=$NEO4J_USERNAME,NEO4J_PASSWORD=$NEO4J_PASSWORD,NEO4J_DATABASE=$NEO4J_DATABASE"

$RUN_URL = gcloud run services describe onrev-api --region=$REGION --format "value(status.url)"
```

### 2) Create service accounts & permissions (once)

```powershell
# Gateway SA (used by API Gateway to call proxy)
$GW_SA = "onrev-gw-sa@$PROJECT_ID.iam.gserviceaccount.com"
gcloud iam service-accounts create onrev-gw-sa --display-name="OnRev API Gateway SA"

# Proxy SA (used by the Cloud Function)
$CF_SA = "onrev-proxy-sa@$PROJECT_ID.iam.gserviceaccount.com"
gcloud iam service-accounts create onrev-proxy-sa --display-name="OnRev Proxy SA"

# Allow the proxy to call Cloud Run
gcloud run services add-iam-policy-binding onrev-api --region=$REGION `
	--member="serviceAccount:$CF_SA" --role="roles/run.invoker"
```

### 3) Deploy the proxy (from the `onrev-proxy/` folder)

```powershell
cd <repo>/onrev-proxy

# Secret header value the app expects
$FUNC_HEADER_KEY = "<choose-a-random-string>"

gcloud functions deploy onrev-proxy --gen2 --region=$REGION --runtime=python311 `
	--source=. --entry-point=proxy --trigger-http `
	--service-account=$CF_SA `
	--set-env-vars "TARGET_URL=$RUN_URL,API_KEY=$FUNC_HEADER_KEY"

$CF_URL = gcloud functions describe onrev-proxy --gen2 --region=$REGION --format "value(url)"
```

### 4) API Gateway config & gateway

Prepare `onrev-gw-v2.yaml` (Swagger v2) pointing to `$CF_URL` with routes for `/docs`, `/openapi.json`, `/person`, `/campaign`, `/clicked_on`.

```powershell
$GW_API = "onrev-gw"
gcloud api-gateway apis create $GW_API

$GW_CFG = "onrev-gw-v2-$(Get-Date -Format yyyyMMddHHmmss)"
gcloud api-gateway api-configs create $GW_CFG `
	--api=$GW_API `
	--openapi-spec=onrev-gw-v2.yaml `
	--backend-auth-service-account=$GW_SA

gcloud api-gateway gateways create onrev-gw `
	--api=$GW_API --api-config=$GW_CFG `
	--location=$REGION

$GW_HOST = gcloud api-gateway gateways describe onrev-gw --location=$REGION --format "value(defaultHostname)"
```

### 5) API key for Gateway (`?key=...`)

```powershell
$KEY_NAME = gcloud services api-keys create --display-name="onrev-make" --format="value(name)"
$GW_KEY   = gcloud services api-keys get-key-string $KEY_NAME --format="value(keyString)"
```

### 6) Smoke tests (exactly how Make.com will call)

```powershell
# Swagger UI HTML (expect 200)
Invoke-WebRequest -Uri "https://$GW_HOST/docs?key=$GW_KEY" -Headers @{ 'x-api-key' = $FUNC_HEADER_KEY } `
	| Select-Object -ExpandProperty StatusCode

# Insert/merge a campaign (API defaults if UTM is blank)
$body = '{"id":"unknown","campaign":"Unknown"}'
Invoke-RestMethod -Method POST -Uri "https://$GW_HOST/campaign?key=$GW_KEY" `
	-Headers @{ 'x-api-key' = $FUNC_HEADER_KEY } `
	-ContentType 'application/json' -Body $body
```

### 7) Make.com wiring (HTTP → Make a request)

```
URL:     https://<GW_HOST>/<endpoint>?key={{GW_KEY}}
Headers: x-api-key: {{FUNC_HEADER_KEY}}
Method:  POST (or GET)
Body:    JSON (e.g., person/campaign/click payloads)
```

---

## Where to find it later (Console)

* **Cloud Run → Services**: `onrev-api` (URL, Env Vars, Logs)
* **Cloud Functions (Gen2)**: `onrev-proxy` (URL, Env Vars, Logs)
* **API Gateway**: `onrev-gw` (default hostname, configs)
* **IAM → Service Accounts**: `onrev-gw-sa`, `onrev-proxy-sa`
* **APIs & Services → Credentials**: API Keys (look for display name like `onrev-make`)

# OnRev API

## Overview
FastAPI-based microservice that interacts with a Neo4j graph database to manage marketing campaign data, user clicks, and relationships. It exposes REST endpoints for upserting people, campaigns, and click events, and for sampling recent click data.

## Features
- Upsert (create/update) Person nodes
- Upsert AdCampaign nodes
- Record Clicked_on relationships between Person and AdCampaign
- Sample recent click events
- Health check endpoint

## Requirements
- Python 3.8+
- Neo4j database (local or remote)
- Docker (optional)

## Setup

### 1. Clone the repository
```
git clone <repo-url>
cd onrev
```

### 2. Create and activate a virtual environment
```
python -m venv venv
./venv/Scripts/activate  # Windows
source venv/bin/activate # Linux/Mac
```

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Configure environment variables
Create a `.env` file in the `onrev` directory:
```
NEO4J_URI=<neo4j_instance_uri> #found in neo4j instance
NEO4J_USER=neo4j
NEO4J_PASS=<neo4j_instance_password>
NEO4J_DB=neo4j
```

### 5. Start Neo4j
Ensure Neo4j is running and accessible at the URI specified above.

### 6. Run the API server
```
uvicorn main:app --reload
```

## API Endpoints

### Health Check
- `GET /healthz` — Returns `{"ok": true}`

### Upsert Person
- `POST /person`
- Body: `{ "id": "string", "name": "string", "email": "string", "contact_number": "string" }`

### Upsert Campaign
- `POST /campaign`
- Body: `{ "id": "string", "campaign": "string" }`

### Record Click
- `POST /clicked_on`
- Body: `{ "person_id": "string", "campaign_id": "string", ... }`

### Sample Clicks
- `GET /sample`
- Returns a list of recent click events

## Docker Usage
A `Dockerfile` is provided for containerized deployment. Build and run with:
```
docker build -t onrev .
docker run --env-file .env -p 8000:8000 onrev
```

## Notes
- Ensure the Neo4j database is running and accessible before starting the API.
- All endpoints expect JSON bodies.
- For production, set secure credentials in `.env`.

# OnRev Proxy

## Overview
OnRev Proxy is a gateway/proxy service for the OnRev API, designed to route, secure, and manage traffic between clients and the OnRev backend. It can be configured for authentication, request routing, and service orchestration using YAML configuration files.

## Features
- Acts as a gateway for OnRev API
- Supports service account authentication
- Configurable via YAML files
- Can be extended for logging, rate limiting, and more

## Requirements
- Python 3.8+
- OnRev API running and accessible
- Docker (optional)

## Setup

### 1. Clone the repository
```
git clone <repo-url>
cd onrev-proxy
```

### 2. Create and activate a virtual environment
```
python -m venv venv
./venv/Scripts/activate  # Windows
source venv/bin/activate # Linux/Mac
```

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Configure service account and gateway
- Place service account JSON in `onrev-proxy-sa.json`
- Configure routing and authentication in `onrev-gw.yaml` or `onrev-gw-v2.yaml`

### 5. Run the proxy server
```
python main.py
```

## Configuration
- `onrev-gw.yaml` and `onrev-gw-v2.yaml` define routing rules, authentication, and service endpoints.
- `onrev-proxy-sa.json` contains credentials for service account authentication.

## Usage
- Start the OnRev API first (see OnRev README)
- Start the proxy with `python main.py`
- Send requests to the proxy endpoint; it will forward them to the OnRev API according to the configuration

## Docker Usage
A `Dockerfile` is provided for containerized deployment. Build and run with:
```
docker build -t onrev-proxy .
docker run --env-file .env -p 8080:8080 onrev-proxy
```

## Notes
- Ensure the OnRev API is running and accessible before starting the proxy.
- Update YAML and JSON config files to match environment and security needs.
- Extend proxy logic in `main.py` for custom routing, logging, or authentication as needed.
