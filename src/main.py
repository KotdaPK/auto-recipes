from typing import Optional, List, Dict, Any
import sqlite3
import os
import json
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel

from src.orchestrate.run import url_to_recipe
from src.dedup.canonicalize import canonicalize

DB_PATH = os.path.join("data", "recipes.db")


def ensure_db(path: str = DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            title TEXT,
            source_url TEXT,
            servings REAL,
            steps_json TEXT,
            include_in_groceries INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            version INTEGER DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS changes_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            entity TEXT NOT NULL,
            entity_id INTEGER,
            op TEXT NOT NULL,
            version INTEGER NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            payload TEXT
        )
        """
    )
    # ingredients table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            default_unit TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            version INTEGER DEFAULT 1,
            UNIQUE(user_id, name)
        )
        """
    )

    # recipe_ingredients junction
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            recipe_id INTEGER NOT NULL,
            ingredient_id INTEGER,
            qty_raw TEXT,
            uom TEXT,
            qty_gml REAL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            version INTEGER DEFAULT 1,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
            FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL
        )
        """
    )

    # density cache for converting volume -> mass
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS density_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            ingredient_name TEXT NOT NULL,
            density_g_ml REAL NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            source TEXT
        )
        """
    )
    conn.commit()
    conn.close()


class IngestRecipeRequest(BaseModel):
    url: Optional[str] = None
    html: Optional[str] = None


class OutboxOp(BaseModel):
    op: str
    entity: str
    temp_id: Optional[str] = None
    entity_id: Optional[int] = None
    payload: Dict[str, Any]


class SyncPushRequest(BaseModel):
    outbox: List[OutboxOp]
    last_seen_server_version: Optional[int] = 0


app = FastAPI(title="Auto-Recipes Server (minimal)")


def lookup_density(conn: sqlite3.Connection, user_id: str, ingredient_name: str) -> Optional[float]:
    cur = conn.execute(
        "SELECT density_g_ml FROM density_cache WHERE user_id = ? AND ingredient_name = ? ORDER BY updated_at DESC LIMIT 1",
        (user_id, ingredient_name),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    # try global (null user_id)
    cur = conn.execute(
        "SELECT density_g_ml FROM density_cache WHERE user_id IS NULL AND ingredient_name = ? ORDER BY updated_at DESC LIMIT 1",
        (ingredient_name,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    return None


def convert_qty_to_gml(conn: sqlite3.Connection, user_id: str, qty: Optional[float], uom: Optional[str], ingredient_name: str) -> Optional[float]:
    if qty is None:
        return None
    if not uom:
        return None
    u = uom.lower().strip()
    # weight units
    if u in ("g", "gram", "grams"):
        return float(qty)
    if u in ("kg", "kilogram", "kilograms"):
        return float(qty) * 1000.0
    if u in ("mg", "milligram", "milligrams"):
        return float(qty) / 1000.0
    if u in ("oz", "ounce", "ounces"):
        # assume weight ounce
        return float(qty) * 28.3495

    # volume units -> convert to ml then use density
    ml = None
    if u in ("ml", "milliliter", "milliliters"):
        ml = float(qty)
    if u in ("l", "liter", "liters"):
        ml = float(qty) * 1000.0
    if u in ("tsp", "teaspoon", "teaspoons"):
        ml = float(qty) * 4.92892
    if u in ("tbsp", "tablespoon", "tablespoons"):
        ml = float(qty) * 14.7868
    if u in ("cup", "cups"):
        ml = float(qty) * 240.0
    if u in ("fl oz", "fl_oz", "fluid ounce", "fluid ounces"):
        ml = float(qty) * 29.5735

    if ml is not None:
        density = lookup_density(conn, user_id, ingredient_name)
        if density:
            return ml * float(density)
        else:
            return None

    # fallback: unknown unit
    return None


def lookup_or_create_ingredient(conn: sqlite3.Connection, user_id: str, name: str, default_unit: Optional[str] = None) -> int:
    # canonicalize name before lookup
    can = canonicalize(name)
    cur = conn.execute("SELECT id FROM ingredients WHERE user_id = ? AND name = ?", (user_id, can))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO ingredients (user_id, name, default_unit) VALUES (?,?,?)",
        (user_id, can, default_unit),
    )
    return cur.lastrowid


def upsert_parsed_recipe(parsed: Dict[str, Any], user_id: str, source_url: Optional[str] = None) -> int:
    """Normalize parsed recipe dict into recipes, ingredients and recipe_ingredients.

    parsed is expected to follow src.models.recipe_schema.RecipePayload structure (title, servings, ingredients, steps).
    Returns the created recipe_id.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    title = parsed.get("title") or parsed.get("name") or "untitled"
    servings = parsed.get("servings")
    steps = parsed.get("steps") or []

    cur.execute(
        "INSERT INTO recipes (user_id, title, source_url, servings, steps_json) VALUES (?,?,?,?,?)",
        (user_id, title, source_url, servings, json.dumps(steps)),
    )
    recipe_id = cur.lastrowid

    # insert recipe change log
    cur.execute(
        "INSERT INTO changes_log (user_id, entity, entity_id, op, version, payload) VALUES (?,?,?,?,?,?)",
        (user_id, "recipe", recipe_id, "create", 1, json.dumps(parsed)),
    )

    # process ingredients
    for ing in parsed.get("ingredients", []) or []:
        # ing may be a dict with keys: name, quantity, unit, raw, notes
        name = ing.get("name") or ing.get("raw") or ""
        if not name:
            continue
        qty = ing.get("quantity") or ing.get("qty") or None
        uom = ing.get("unit") or ing.get("uom") or None
        notes = ing.get("notes") or ing.get("description") or None

        ingredient_id = lookup_or_create_ingredient(conn, user_id, name, default_unit=uom)

        qty_gml = None
        try:
            qty_gml = convert_qty_to_gml(conn, user_id, float(qty) if qty is not None else None, uom, name)
        except Exception:
            qty_gml = None

        qty_raw = ing.get("raw") or (f"{qty or ''} {uom or ''} {name}").strip()

        cur.execute(
            "INSERT INTO recipe_ingredients (user_id, recipe_id, ingredient_id, qty_raw, uom, qty_gml, notes) VALUES (?,?,?,?,?,?,?)",
            (user_id, recipe_id, ingredient_id, qty_raw, uom, qty_gml, notes),
        )
        ri_id = cur.lastrowid
        cur.execute(
            "INSERT INTO changes_log (user_id, entity, entity_id, op, version, payload) VALUES (?,?,?,?,?,?)",
            (user_id, "recipe_ingredient", ri_id, "create", 1, json.dumps({"ingredient_id": ingredient_id, "qty_raw": qty_raw, "uom": uom, "qty_gml": qty_gml})),
        )

    conn.commit()
    conn.close()
    return recipe_id


def get_current_user(authorization: Optional[str] = Header(None), x_user: Optional[str] = Header(None)) -> Dict[str, str]:
    """
    Minimal dev-friendly auth: if Authorization header present we treat its value as a token and
    derive a uid; otherwise an X-User header may be used locally. In production replace with
    Firebase ID token verification.
    """
    if x_user:
        return {"uid": x_user}
    if authorization:
        # Authorization: Bearer <token>
        parts = authorization.split()
        if len(parts) == 2:
            token = parts[1]
        else:
            token = parts[0]
        # lightweight uid extraction for dev
        return {"uid": token[-16:]}
    raise HTTPException(status_code=401, detail="Missing auth; set X-User header for local dev")


@app.on_event("startup")
def startup():
    ensure_db()


@app.post("/ingest/recipe")
def ingest_recipe(req: IngestRecipeRequest, user: Dict[str, str] = Depends(get_current_user)):
    if not req.url and not req.html:
        raise HTTPException(status_code=400, detail="url or html required")
    parsed = url_to_recipe(req.url) if req.url else {"title": "imported", "note": "html import not implemented"}

    recipe_id = upsert_parsed_recipe(parsed, user["uid"], source_url=req.url)
    return {"recipe_id": recipe_id, "server_version": recipe_id}


@app.post("/sync/push")
def sync_push(req: SyncPushRequest, user: Dict[str, str] = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    applied = []
    server_version = None
    for op in req.outbox:
        if op.entity == "recipe" and op.op == "create":
            # If payload contains structured ingredients, upsert fully; otherwise insert minimal row
            if isinstance(op.payload, dict) and op.payload.get("ingredients"):
                created_id = upsert_parsed_recipe(op.payload, user["uid"], source_url=op.payload.get("source_url"))
            else:
                title = op.payload.get("title") or op.payload.get("name") or "untitled"
                cur.execute(
                    "INSERT INTO recipes (user_id, title, source_url, servings, steps_json) VALUES (?,?,?,?,?)",
                    (user["uid"], title, op.payload.get("source_url"), op.payload.get("servings"), json.dumps(op.payload.get("steps", []))),
                )
                created_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO changes_log (user_id, entity, entity_id, op, version, payload) VALUES (?,?,?,?,?,?)",
                    (user["uid"], "recipe", created_id, "create", 1, json.dumps(op.payload)),
                )
            applied.append({"temp_id": op.temp_id, "entity": "recipe", "entity_id": created_id, "server_version": created_id})
            server_version = created_id
        else:
            # Generic append to change log for updates/deletes or other entities
            cur.execute(
                "INSERT INTO changes_log (user_id, entity, entity_id, op, version, payload) VALUES (?,?,?,?,?,?)",
                (user["uid"], op.entity, op.entity_id, op.op, 1, json.dumps(op.payload)),
            )
            applied.append({"temp_id": op.temp_id, "entity": op.entity, "entity_id": cur.lastrowid, "server_version": cur.lastrowid})
            server_version = cur.lastrowid

    conn.commit()
    conn.close()
    return {"applied": applied, "server_version": server_version}


@app.get("/sync/pull")
def sync_pull(since: int = 0, user: Dict[str, str] = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, entity, entity_id, op, version, updated_at, payload FROM changes_log WHERE user_id = ? AND id > ? ORDER BY id ASC", (user["uid"], since))
    rows = cur.fetchall()
    changes = []
    for r in rows:
        changes.append({
            "id": r[0],
            "entity": r[1],
            "entity_id": r[2],
            "op": r[3],
            "version": r[4],
            "updated_at": r[5],
            "payload": json.loads(r[6]) if r[6] else None,
        })
    conn.close()
    server_version = changes[-1]["id"] if changes else since
    return {"changes": changes, "server_version": server_version}


@app.get("/grocery/weekly")
def grocery_weekly(week: str, user: Dict[str, str] = Depends(get_current_user)):
    # Placeholder: server-side rollups will compute grocery lines by aggregating
    # planned meals and converting quantities. Return empty structure for now.
    return {"week_start": week, "lines": [], "server_version": 0}
