import sqlite3, json
c = sqlite3.connect(r"桌宠合集\阿尔卑斯桌宠自用\userdata\memory.db")
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute("SELECT id, content, importance, evidence_count, access_count, created_at, last_accessed_at, archived FROM memories WHERE type='topic' ORDER BY created_at").fetchall()]
print("topic count:", len(rows))
for r in rows:
    imp = r["importance"] or 0
    print(f"- [{r['id']}] imp={imp:.2f} ev={r['evidence_count']} acc={r['access_count']} arch={r['archived']} | {r['content']}")
