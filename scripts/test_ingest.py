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
