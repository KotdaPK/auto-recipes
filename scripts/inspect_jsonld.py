from src.ingest.fetch import fetch_url
import re, json, sys
url = sys.argv[1] if len(sys.argv)>1 else 'https://downshiftology.com/recipes/chicken-piccata/'
html, _ = fetch_url(url)
blocks = []
for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, flags=re.S | re.I):
    body = m.group(1).strip()
    try:
        parsed = json.loads(body)
        blocks.append(parsed)
    except Exception:
        try:
            s = body
            start = s.find('{')
            end = s.rfind('}')
            if start!=-1 and end!=-1:
                parsed = json.loads(s[start:end+1])
                blocks.append(parsed)
        except Exception:
            pass
print('Found', len(blocks), 'JSON-LD blocks')
for i,b in enumerate(blocks[:10]):
    print('--- block', i)
    print(json.dumps(b, indent=2)[:1000])
