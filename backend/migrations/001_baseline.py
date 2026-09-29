"""001 baseline：Phase 1–20 累積的完整 schema（建表、補欄位、索引）。

可重複執行：任何舊狀態的資料庫（從 Phase 1 的六欄位一路到 Phase 20）跑完都會到位；
`schema_version` 表不存在的舊資料庫，第一次連線就從這一號開始。之後的 schema 變更一律新增
`NNN_*.py`，不要再改這一支。
"""

NAME = "baseline"

_BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    module TEXT NOT NULL,
    verdict TEXT NOT NULL,
    engine TEXT NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    summary_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inspections_module_time ON inspections(module, created_at);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('operator', 'qc', 'admin')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    before_json TEXT,
    after_json TEXT,
    request_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);

CREATE TABLE IF NOT EXISTS parts (
    part_no TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    spec TEXT NOT NULL DEFAULT '',
    customer TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_orders (
    work_order_no TEXT PRIMARY KEY,
    part_no TEXT NOT NULL REFERENCES parts(part_no),
    quantity INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'in_progress', 'done', 'cancelled')),
    start_date TEXT,
    end_date TEXT,
    lot_no TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_no TEXT NOT NULL REFERENCES parts(part_no),
    version INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (part_no, version)
);

CREATE TABLE IF NOT EXISTS recipe_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id),
    position INTEGER NOT NULL,
    action TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    image_slot TEXT NOT NULL DEFAULT 'main',
    label TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS inspection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id),
    part_no TEXT NOT NULL,
    work_order TEXT,
    lot_no TEXT,
    station TEXT,
    operator TEXT,
    created_by TEXT,
    request_id TEXT,
    adhoc INTEGER,
    status TEXT NOT NULL DEFAULT 'running',
    verdict TEXT NOT NULL DEFAULT 'INFO',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    steps_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON inspection_runs(created_at);

CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL REFERENCES inspections(id),
    run_id INTEGER,
    created_at TEXT NOT NULL,
    module TEXT NOT NULL,
    part_no TEXT,
    work_order TEXT,
    lot_no TEXT,
    station TEXT,
    characteristic TEXT NOT NULL,
    value REAL NOT NULL,
    lsl REAL,
    usl REAL,
    target REAL,
    unit TEXT
);
CREATE INDEX IF NOT EXISTS idx_measurements_part_char ON measurements(part_no, characteristic, created_at);

CREATE TABLE IF NOT EXISTS webhook_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    next_retry_at TEXT NOT NULL,
    given_up INTEGER NOT NULL DEFAULT 0
);
"""

# inspections 在 Phase 9 之後陸續新增的欄位：全部可 NULL，用 ALTER TABLE ADD COLUMN 補進舊 db。
_NEW_COLUMNS = [
    "work_order", "part_no", "lot_no", "station", "operator",
    "image_path", "annotated_path",
    "review_verdict", "reviewer", "reviewed_at", "review_note",
    "images_json", "request_id", "created_by", "run_id", "adhoc",
]

_COLUMN_TYPES = {"run_id": "INTEGER", "adhoc": "INTEGER"}  # 其餘補進舊 db 的欄位都是 TEXT



def upgrade(conn) -> None:
    conn.executescript(_BASE_SCHEMA)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(inspections)").fetchall()}
    for col in _NEW_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE inspections ADD COLUMN {col} {_COLUMN_TYPES.get(col, 'TEXT')}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inspections_work_order ON inspections(work_order)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inspections_part_no_time ON inspections(part_no, created_at)")
    conn.commit()
