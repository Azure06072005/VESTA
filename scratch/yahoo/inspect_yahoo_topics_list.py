import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_path = 'd:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har'
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

# Entry 790 has the editorialTopics
e790 = data['log']['entries'][790]
js = json.loads(e790['response']['content']['text'])
topics = js['data']['cdsData']['topics']
print(f"Total topics: {len(topics)}")

macro_finance_topics = []
for t in topics:
    name = t.get('topicName')
    title = t.get('title')
    lid = t.get('listId')
    if lid:
        macro_finance_topics.append((name, title, lid))

print(f"Topics with listId: {len(macro_finance_topics)}")
print("\nSample top 30 topics:")
for idx, (name, title, lid) in enumerate(macro_finance_topics[:30]):
    print(f"  [{idx+1}] {name:<30} | {title:<35} | listId: {lid}")
