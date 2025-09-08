# --- Imports ---
import os, uuid
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from neo4j import GraphDatabase
from dotenv import find_dotenv, load_dotenv
from contextlib import asynccontextmanager

# --- Load environment variables from .env file ---
load_dotenv(find_dotenv())
URI  = os.getenv("NEO4J_URI")                  # Neo4j connection URI
USER = os.getenv("NEO4J_USER", "neo4j")        # Neo4j username
PASS = os.getenv("NEO4J_PASS")                 # Neo4j password
DB   = os.getenv("NEO4J_DB", "neo4j")          # Neo4j database name

driver = None  # Will hold the Neo4j driver instance

# --- FastAPI lifespan event for managing Neo4j driver connection ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global driver
    driver = GraphDatabase.driver(URI, auth=(USER, PASS))  # Connect to Neo4j
    try:
        yield  # App runs here
    finally:
        if driver:
            driver.close()  # Clean up Neo4j connection on shutdown

# --- Initialize FastAPI app with lifespan handler ---
app = FastAPI(title="OnRev API", lifespan=lifespan)

# ---------- Data Models (Pydantic) ----------
class Person(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    contact_number: Optional[str] = None

class Campaign(BaseModel):
    id: Optional[str] = None
    campaign: Optional[str] = None

class Click(BaseModel):
    person_id: str
    campaign_id: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str]  = None
    medium: Optional[str]  = None
    date: Optional[str]    = None   # ISO or YYYY-MM-DD
    device: Optional[str]  = None
    id: Optional[str]      = None

# ---------- API Endpoints ----------

# Health check endpoint
@app.get("/healthz")
def health():
    """Simple health check endpoint."""
    return {"ok": True}

# Upsert (create/update) a Person node in Neo4j
@app.post("/person")
def upsert_person(p: Person):
    """
    Create or update a Person node in Neo4j.
    Uses MERGE to ensure uniqueness by id.
    """
    cypher = """
    MERGE (x:Person {id:$id})
      ON CREATE SET x.name=$name, x.email=$email, x.contact_number=$contact_number
      ON MATCH  SET x.name=coalesce($name,x.name),
                   x.email=coalesce($email,x.email),
                   x.contact_number=coalesce($contact_number,x.contact_number)
    RETURN x.id AS id
    """
    recs, _, _ = driver.execute_query(
        cypher, id=p.id, name=p.name, email=p.email,
        contact_number=p.contact_number, database_=DB
    )
    return {"ok": True, "id": recs[0]["id"]}

# Upsert (create/update) an AdCampaign node in Neo4j
@app.post("/campaign")
def upsert_campaign(c: Campaign):
    """
    Create or update an AdCampaign node in Neo4j.
    If no campaign info is provided, uses 'unknown'/'Unknown'.
    """
    cid   = (c.id or "").strip() or "unknown"
    cname = (c.campaign or "").strip() or "Unknown"
    cypher = """
    MERGE (x:AdCampaign {id:$id})
      ON CREATE SET x.campaign=$campaign
      ON MATCH  SET x.campaign=coalesce($campaign, x.campaign)
    RETURN x.id AS id
    """
    recs, _, _ = driver.execute_query(cypher, id=cid, campaign=cname, database_=DB)
    return {"ok": True, "id": recs[0]["id"]}

# Upsert a Clicked_on relationship between Person and AdCampaign
@app.post("/clicked_on")
def upsert_clicked_on(r: Click):
    """
    Create or update a Clicked_on relationship between a Person and an AdCampaign.
    Sets various properties and tags based on content.
    """
    cid    = (r.campaign_id or "").strip() or "unknown"
    cname  = "Unknown" if cid == "unknown" else None
    dstr   = (r.date or "").strip() or None

    cypher = """
    MERGE (p:Person {id:$person_id})
    MERGE (c:AdCampaign {id:$campaign_id})
      ON CREATE SET c.campaign = coalesce($campaign_name, 'Unknown')

    MERGE (p)-[rel:Clicked_on]->(c)
      ON CREATE SET
        rel.id          = coalesce($id, 'clk:' + $person_id + '|' + $campaign_id + '|' +
                                    toString(CASE WHEN $date IS NULL OR $date = '' THEN date()
                                                  ELSE date(datetime($date)) END)),
        rel.person_id   = $person_id,
        rel.campaign_id = $campaign_id,
        rel.date        = CASE WHEN $date IS NULL OR $date = '' THEN date()
                               ELSE date(datetime($date)) END,
        rel.device      = $device,
        rel.content     = $content,
        rel.source      = $source,
        rel.medium      = $medium,
        rel.tag         = CASE
                            WHEN $content IS NOT NULL AND toLower($content) CONTAINS 'instagram' THEN 'instagram'
                            WHEN $content IS NOT NULL AND toLower($content) CONTAINS 'facebook'  THEN 'facebook'
                            ELSE NULL
                          END
      ON MATCH SET
        rel.person_id   = $person_id,
        rel.campaign_id = $campaign_id,
        rel.date        = CASE WHEN $date IS NULL OR $date = '' THEN rel.date
                               ELSE date(datetime($date)) END,
        rel.device      = coalesce($device, rel.device),
        rel.content     = coalesce($content, rel.content),
        rel.source      = coalesce($source, rel.source),
        rel.medium      = coalesce($medium, rel.medium),
        rel.tag         = CASE
                            WHEN $content IS NOT NULL AND toLower($content) CONTAINS 'instagram' THEN 'instagram'
                            WHEN $content IS NOT NULL AND toLower($content) CONTAINS 'facebook'  THEN 'facebook'
                            ELSE rel.tag
                          END
    RETURN p.id AS person_id, rel.id AS click_id, c.id AS campaign_id
    """
    try:
        recs, summary, _ = driver.execute_query(
            cypher,
            person_id=r.person_id,
            campaign_id=cid,
            campaign_name=cname,
            content=r.content, source=r.source, medium=r.medium,
            date=dstr, device=r.device, id=r.id,
            database_=DB
        )
        return {
            "ok": True,
            "link": recs[0].data(),
            "nodes_created": summary.counters.nodes_created,
            "rels_created": summary.counters.relationships_created,
            "props_set": summary.counters.properties_set,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get a sample of recent Clicked_on relationships
@app.get("/sample")
def sample():
    """
    Return a sample of recent Clicked_on relationships with related Person and AdCampaign info.
    """
    recs, _, _ = driver.execute_query(
        """
        MATCH (p:Person)-[r:Clicked_on]->(c:AdCampaign)
        RETURN p.id AS person, p.name AS name,
               c.id AS campaign_id, c.campaign AS campaign,
               r.content AS content, r.source AS source, r.medium AS medium, r.tag AS tag,
               r.date AS date, r.device AS device, r.id AS click
        ORDER BY date DESC
        LIMIT 10
        """,
        database_=DB
    )
    return [r.data() for r in recs]


from extract_id import router as extract_id_router
app.include_router(extract_id_router)