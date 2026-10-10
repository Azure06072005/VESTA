import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import urllib.request
import json

res = urllib.request.urlopen('http://127.0.0.1:8899/api/symbol/FPT/detail')
d = json.loads(res.read().decode('utf-8'))
print('symbol:', d.get('symbol'))
print('company_name:', d.get('overview', {}).get('company_name'))
print('current_price:', d.get('ohlcv', {}).get('metrics', {}).get('current_price'))
print('change_pct:', d.get('ohlcv', {}).get('metrics', {}).get('change_pct'))
print('fundamentals pe:', d.get('fundamentals', {}).get('pe'), 'pb:', d.get('fundamentals', {}).get('pb'))
print('shareholders:', len(d.get('shareholders', [])))
print('foreign_flow:', len(d.get('foreign_flow', [])))
print('events:', len(d.get('events', [])))
print('news count:', len(d.get('news', {}).get('items', [])))
print('recommendation:', d.get('feedback_recommendation', {}).get('recommendation_title'))
