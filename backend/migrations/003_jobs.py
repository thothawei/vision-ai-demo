"""003：持久化工作佇列（`jobs`）。擬合這類背景工作的狀態存在資料庫，重啟後才知道哪些被中斷、哪些還在排隊。"""

NAME = "jobs"


def upgrade(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed', 'interrupted')),
            attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, id)")
    conn.commit()
