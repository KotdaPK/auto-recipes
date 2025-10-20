from notion_client import Client
from dotenv import load_dotenv
import os

load_dotenv()
print('NOTION_TOKEN present:', bool(os.environ.get('NOTION_TOKEN')))
print('INGREDIENTS_DB_ID:', os.environ.get('INGREDIENTS_DB_ID'))
client = Client(auth=os.environ.get('NOTION_TOKEN'))
res = client.databases.query(database_id=os.environ.get('INGREDIENTS_DB_ID'), page_size=50)
results = res.get('results', [])
print('results_count:', len(results))
if results:
    sample = results[0]
    print('sample_page_id:', sample.get('id'))
    props = sample.get('properties', {})
    print('property keys:', list(props.keys()))
    title_prop = props.get('Name') or props.get(os.environ.get('P_RECIPE_TITLE', 'Name'))
    print('title_prop present:', bool(title_prop))
    if title_prop and title_prop.get('title'):
        print('title text:', ''.join([t.get('plain_text', '') for t in title_prop.get('title')]))
else:
    print('no pages returned from query')
