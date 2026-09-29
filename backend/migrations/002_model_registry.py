"""002：模型登錄表（`model_versions`）與檢驗紀錄的模型版本欄位。"""

NAME = "model_registry"


def upgrade(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            weights_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
            note TEXT NOT NULL DEFAULT '',
            registered_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (model_id, version)
        )""")
    # 每個模型同時只有一個啟用版本，由資料庫保證
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_model ON model_versions(model_id) WHERE status = 'active'")
    existing = {row[1] for row in conn.execute("PRAGMA table_info(inspections)").fetchall()}
    if "model_id" not in existing:
        conn.execute("ALTER TABLE inspections ADD COLUMN model_id TEXT")
    if "model_version" not in existing:
        conn.execute("ALTER TABLE inspections ADD COLUMN model_version INTEGER")
    conn.commit()
