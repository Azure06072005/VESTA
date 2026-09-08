import codecs
import os

files_to_patch = [
    'tests/test_market_crawler.py',
    'tests/test_fundamental_crawler.py',
    'tests/test_corporate_events.py'
]

for fp in files_to_patch:
    if not os.path.exists(fp):
        print(f"File not found: {fp}")
        continue
    with codecs.open(fp, 'r', 'utf-8') as f:
        content = f.read()

    # Add import if missing
    if 'from etl.retry_failed_jobs import EmptyResultError' not in content:
        content = content.replace('from etl import db', 'from etl import db\nfrom etl.retry_failed_jobs import EmptyResultError')

    # Replace ValueError with EmptyResultError
    content = content.replace('pytest.raises(ValueError, match="empty DataFrame")', 'pytest.raises(EmptyResultError)')
    content = content.replace("pytest.raises(ValueError, match='empty DataFrame')", "pytest.raises(EmptyResultError)")

    with codecs.open(fp, 'w', 'utf-8') as f:
        f.write(content)
