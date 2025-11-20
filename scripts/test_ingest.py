import sys
import pathlib
import json
from dotenv import load_dotenv

# Load .env so settings.GEMINI_API_KEY and other env-vars are available
load_dotenv()

# Ensure project root is on sys.path so `src` package can be imported
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.orchestrate.run import url_to_recipe
url = "https://downshiftology.com/recipes/chicken-piccata/"
parsed = url_to_recipe(url)
print("--- orchestrator result ---")
print(json.dumps(parsed, indent=2, ensure_ascii=False))

# --- Run the parser directly for debugging to see any Gemini errors ---
try:
	from src.ingest.fetch import fetch_url
	from src.ingest.extract_text import extract_main_text
	from src.ingest.parse_llm_gemini import parse_recipe_text

	print("\n--- direct parse attempt ---")
	html, final = fetch_url(url)
	text = extract_main_text(html, final)
	try:
		# pass full html so parse_recipe_text can extract JSON-LD and include it in the prompt
		recipe = parse_recipe_text(text, final, html)
		print(json.dumps(recipe.model_dump(), indent=2, ensure_ascii=False))
	except Exception as e:
		print("parse_recipe_text raised:", repr(e))
except Exception as e:
	print("Direct parser invocation failed to import or run:", repr(e))
