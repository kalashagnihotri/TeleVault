import os

path = 'src/database.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Insert _adopt_or_apply_007 before hash_exists
insert_pos = content.find('    def hash_exists(self, sha256: str) -> bool:')

code_to_insert = '''
    def _adopt_or_apply_007(self, sql_file: Path, version: str) -> None:
        with self.connect() as conn:
            # Safely check if the column already exists
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "face_calibrations" not in tables:
                self._apply_migration(sql_file, version)
                return
                
            columns_fc = {r["name"] for r in conn.execute("PRAGMA table_info(face_calibrations)").fetchall()}
        
        if "individual_strong_support_threshold" in columns_fc:
            self._mark_applied(version)
        else:
            self._apply_migration(sql_file, version)

'''
new_content = content[:insert_pos] + code_to_insert + content[insert_pos:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)
