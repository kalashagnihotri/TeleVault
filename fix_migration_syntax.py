import os

path = 'tests/test_migration_007.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "conn.execute('INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))', (version,))",
    'conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime(\'now\'))", (version,))'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
