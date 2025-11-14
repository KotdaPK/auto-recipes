from dotenv import load_dotenv
load_dotenv()
import os
import json
try:
    import google.genai as genai
    from google.genai import types
except Exception as e:
    print("IMPORT_ERROR:", e)
    raise
api_key = os.getenv('GEMINI_API_KEY')
print('Using GEMINI_API_KEY set?', bool(api_key))
client = genai.Client(api_key=api_key)
try:
    resp = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='Say hello in JSON: {"greeting": "Hello"}',
        config=types.GenerateContentConfig(temperature=0)
    )
    print('REPR:', repr(resp))
    text = getattr(resp, 'text', None) or getattr(resp, 'output_text', None)
    print('TEXT:', text)
except Exception as e:
    print('CALL_ERROR:', repr(e))
    raise
