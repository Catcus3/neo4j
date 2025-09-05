# OnRev API

## Overview
OnRev = FastAPI-based microservice that interacts with a Neo4j graph database to manage marketing campaign data, user clicks, and relationships. It exposes REST endpoints for upserting people, campaigns, and click events, and for sampling recent click data.

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
NEO4J_URI=bolt://localhost:7687 #found in neo4j instance
NEO4J_USER=neo4j
NEO4J_PASS=your_password
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
- Place your service account JSON in `onrev-proxy-sa.json`
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
- Update YAML and JSON config files to match your environment and security needs.
- Extend proxy logic in `main.py` for custom routing, logging, or authentication as needed.
