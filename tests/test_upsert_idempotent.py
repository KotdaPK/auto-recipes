import sqlite3

from src import main


def test_upsert_is_idempotent_by_source_url(tmp_path, monkeypatch):
    db_path = tmp_path / "recipes.db"
    monkeypatch.setattr(main, "DB_PATH", str(db_path))
    main.ensure_db(str(db_path))

    base_payload = {
        "title": "Original",
        "servings": 2,
        "steps": ["mix", "serve"],
        "ingredients": [
            {"name": "Salt", "quantity": 1, "unit": "tsp", "raw": "1 tsp salt"},
        ],
    }
    updated_payload = {
        **base_payload,
        "title": "Updated",
        "ingredients": [
            {"name": "Pepper", "quantity": 2, "unit": "tbsp", "raw": "2 tbsp pepper"},
        ],
    }
    url = "https://example.com/recipe"
    user_id = "user-123"

    first_id = main.upsert_parsed_recipe(base_payload, user_id, source_url=url)
    second_id = main.upsert_parsed_recipe(updated_payload, user_id, source_url=url)

    assert first_id == second_id

    conn = sqlite3.connect(str(db_path))
    recipes = conn.execute("SELECT id, title, version FROM recipes").fetchall()
    assert recipes == [(first_id, "Updated", 2)]

    ingredients = conn.execute(
        "SELECT qty_raw FROM recipe_ingredients WHERE recipe_id = ? ORDER BY id",
        (first_id,),
    ).fetchall()
    assert ingredients == [("2 tbsp pepper",)]

    recipe_ops = conn.execute(
        "SELECT op FROM changes_log WHERE entity = 'recipe' ORDER BY id",
    ).fetchall()
    assert recipe_ops == [("create",), ("update",)]

    conn.close()
