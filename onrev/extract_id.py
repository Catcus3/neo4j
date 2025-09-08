# onrev/extract_id.py
"""
Endpoints to extract Neo4j-assigned internal IDs (elementId) for :Person nodes,
optionally returning an external→internal mapping.

- GET /ids/person/internal -> { "items": ["<elementId>", ...], "next_skip": <int> }
- GET /ids/person/map      -> { "items": [{external_id, neo4j_id}, ...], "next_skip": <int> }
"""

from typing import List, Optional
import os

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from neo4j import GraphDatabase
from dotenv import find_dotenv, load_dotenv

# --- Load environment variables ---
# Loads environment variables from a .env file if present, supporting both local and cloud deployment.
load_dotenv(find_dotenv())

# --- Neo4j connection configuration ---
# Reads Neo4j connection details (URI, username, password, database) from environment variables.
# Supports multiple naming conventions for flexibility.
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or os.getenv("NEO4J_DB", "neo4j")

neo4j_driver = None 

# --- FastAPI router and pagination constants ---
# Initializes the FastAPI APIRouter and sets default/max pagination limits for API endpoints.
router = APIRouter()
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000

# --- Utility functions ---
def _clamp_limit(n: int) -> int:
    # Ensures the limit parameter stays within allowed bounds.
    return min(max(1, int(n)), MAX_LIMIT)

def _ensure_driver():
    """Create the Neo4j driver and validate required environment variables."""
    global neo4j_driver
    if neo4j_driver is not None:
        return
    missing = [k for k, v in {
        "NEO4J_URI": NEO4J_URI,
        "NEO4J_USER/USERNAME": NEO4J_USER,
        "NEO4J_PASS/PASSWORD": NEO4J_PASS,
    }.items() if not v]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Neo4j connection envs missing: {', '.join(missing)}"
        )
    try:
        neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j driver init failed: {e}")

# --- Response models ---
# Defines Pydantic models for API responses:
# - IdList: List of Neo4j internal IDs and next pagination skip value.
# - PersonMapItem: Mapping of external person ID to Neo4j internal ID.
# - PersonMapResponse: List of PersonMapItem and next pagination skip value.
class IdList(BaseModel):
    items: List[str]
    next_skip: int

class PersonMapItem(BaseModel):
    external_id: Optional[str]
    neo4j_id: str

class PersonMapResponse(BaseModel):
    items: List[PersonMapItem]
    next_skip: int

# --- API Endpoints ---
@router.get("/ids/person/internal", response_model=IdList)
async def list_person_internal_ids(
    only_connected: bool = Query(
        False, description="If true, only persons with at least one :Clicked_on relationship."
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    Return Neo4j elementId() values for :Person nodes (paginated).
    Optionally filters for persons with at least one :Clicked_on relationship.
    """
    _ensure_driver()
    limit = _clamp_limit(limit)

    cypher = """
    CALL {
      WITH $only_connected AS oc
      MATCH (p:Person)
      WHERE oc = false OR (p)-[:Clicked_on]->(:AdCampaign)
      RETURN elementId(p) AS neo4j_id
      ORDER BY neo4j_id
      SKIP $skip LIMIT $limit
    }
    RETURN neo4j_id;
    """
    params = {"only_connected": only_connected, "skip": int(skip), "limit": limit}

    try:
        rows, _, _ = neo4j_driver.execute_query(cypher, **params, database_=NEO4J_DATABASE)
        return IdList(items=[r["neo4j_id"] for r in rows], next_skip=int(skip) + limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ids/person/map", response_model=PersonMapResponse)
async def list_person_id_map(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    Return pairs of (external p.id, internal elementId(p)) for :Person nodes (paginated).
    """
    _ensure_driver()
    limit = _clamp_limit(limit)

    cypher = """
    MATCH (p:Person)
    RETURN p.id AS external_id, elementId(p) AS neo4j_id
    ORDER BY external_id
    SKIP $skip LIMIT $limit
    """
    try:
        data, _, _ = neo4j_driver.execute_query(cypher, skip=int(skip), limit=limit, database_=NEO4J_DATABASE)
        items = [PersonMapItem(external_id=r.get("external_id"), neo4j_id=r["neo4j_id"]) for r in data]
        return PersonMapResponse(items=items, next_skip=int(skip) + limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Export router for FastAPI app inclusion ---
__all__ = ["router"]