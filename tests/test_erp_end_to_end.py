"""Phase 24：ERP 端到端（SQLite 版）。

規劃書要求以 SQL Server 容器跑 docs/erp-integration-sample/；Apple Silicon 上官方 x86_64 映像在 QEMU 下無法啟動
（見 docs/erp-integration.md「端到端驗證」），所以改用 SQLite 當 ERP 端資料庫，照 erp-integration.md 第 2 節的流程
（since_id 增量輪詢 → UPSERT → reviews 同步 → 游標續傳）完整跑一遍，證明輪詢邏輯與 API 契約正確。
SQL 方言（MERGE vs ON CONFLICT）以外的邏輯與 C# 範例一致。
"""

import sqlite3

import pytest


class ErpPoller:
    """ERP 端的背景輪詢服務：游標（last_id、last_review_sync）存在 ERP 自己的資料庫，重啟後從游標續傳。"""

    def __init__(self, http, db_path):
        self.http = http
        self.db = sqlite3.connect(db_path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS QualityInspections (
                VisionInspectionId INTEGER PRIMARY KEY, InspectionModule TEXT, AiVerdict TEXT, FinalVerdict TEXT,
                WorkOrderNo TEXT, PartNo TEXT, LotNo TEXT, StationCode TEXT, InspectedAt TEXT, ReviewedAt TEXT);
            CREATE TABLE IF NOT EXISTS SyncState (Name TEXT PRIMARY KEY, Value TEXT);""")

    def _state(self, name, default):
        row = self.db.execute("SELECT Value FROM SyncState WHERE Name = ?", (name,)).fetchone()
        return row[0] if row else default

    def _set_state(self, name, value):
        self.db.execute(
            "INSERT INTO SyncState VALUES (?, ?) ON CONFLICT(Name) DO UPDATE SET Value = excluded.Value",
            (name, str(value)),
        )

    def poll_once(self) -> int:
        last_id = int(self._state("last_id", 0))
        res = self.http.get("/api/inspections", params={"since_id": last_id, "limit": 200})
        assert res.status_code == 200, res.text
        records = res.json()
        ids = [r["id"] for r in records]
        assert ids == sorted(ids), "since_id 必須 id 升冪"
        for r in records:
            self.db.execute(
                "INSERT INTO QualityInspections (VisionInspectionId, InspectionModule, AiVerdict, FinalVerdict, WorkOrderNo,"
                " PartNo, LotNo, StationCode, InspectedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(VisionInspectionId) DO UPDATE SET AiVerdict = excluded.AiVerdict,"
                " FinalVerdict = excluded.FinalVerdict, InspectedAt = excluded.InspectedAt",
                (
                    r["id"],
                    r["module"],
                    r["verdict"],
                    r["review_verdict"] or r["verdict"],
                    r["work_order"],
                    r["part_no"],
                    r["lot_no"],
                    r["station"],
                    r["created_at"],
                ),
            )
            last_id = max(last_id, r["id"])
        self._set_state("last_id", last_id)
        self.db.commit()
        return len(records)

    def sync_reviews(self) -> int:
        since = self._state("last_review_sync", "1970-01-01T00:00:00")
        res = self.http.get("/api/inspections/reviews", params={"since": since, "limit": 200})
        assert res.status_code == 200, res.text
        records = res.json()
        for r in records:
            self.db.execute(
                "UPDATE QualityInspections SET FinalVerdict = ?, ReviewedAt = ? WHERE VisionInspectionId = ?",
                (r["review_verdict"], r["reviewed_at"], r["id"]),
            )
            since = max(since, r["reviewed_at"])
        self._set_state("last_review_sync", since)
        self.db.commit()
        return len(records)

    def rows(self):
        return {
            r[0]: r[1:]
            for r in self.db.execute(
                "SELECT VisionInspectionId, AiVerdict, FinalVerdict, WorkOrderNo, ReviewedAt FROM QualityInspections"
            )
        }


def _inspect(client, png, work_order):
    res = client.post(
        "/api/codes/decode", files={"file": ("a.png", png, "image/png")}, headers={"X-Work-Order": work_order}
    )
    assert res.status_code == 200, res.text
    return res.json()["inspection_id"]


def test_erp_polls_upserts_syncs_reviews_and_resumes_after_restart(
    client, qc_client, tmp_path, gs1_valid_png_fields, gs1_expired_png_fields
):
    ok_png, _ = gs1_valid_png_fields
    ng_png, _ = gs1_expired_png_fields  # 已過期的追溯碼 → NG
    erp_db = tmp_path / "erp.db"
    erp = ErpPoller(client, erp_db)

    assert erp.poll_once() == 0  # 空資料不出錯
    first = [_inspect(client, ok_png, "WO-1"), _inspect(client, ng_png, "WO-1"), _inspect(client, ok_png, "WO-2")]
    assert erp.poll_once() == 3
    rows = erp.rows()
    assert set(rows) == set(first)
    assert rows[first[0]][:2] == ("OK", "OK") and rows[first[1]][:2] == ("NG", "NG")
    assert erp.poll_once() == 0  # 沒有新資料：游標生效，不重複拉

    # 事後人工複判：since_id 抓不到，要靠 reviews 同步
    res = qc_client.patch(f"/api/inspections/{first[1]}/review", json={"review_verdict": "OK", "review_note": "誤判"})
    assert res.status_code == 200, res.text
    assert erp.poll_once() == 0
    assert erp.rows()[first[1]][1] == "NG"  # 還沒同步
    assert erp.sync_reviews() == 1
    assert erp.rows()[first[1]][1:3] == ("OK", "WO-1")  # 最終判定變 OK，AI 判定仍保留 NG
    assert erp.rows()[first[1]][0] == "NG" and erp.rows()[first[1]][3] is not None
    assert erp.sync_reviews() == 0  # 同步游標生效

    # ERP 服務重啟：新的程序只靠 ERP 資料庫裡的游標續傳，不漏、不重複
    erp.db.close()
    second = [_inspect(client, ng_png, "WO-3"), _inspect(client, ok_png, "WO-3")]
    restarted = ErpPoller(client, erp_db)
    assert restarted.poll_once() == 2
    assert set(restarted.rows()) == set(first + second)
    count = restarted.db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT VisionInspectionId) FROM QualityInspections"
    ).fetchone()
    assert count == (5, 5)


def test_erp_pushes_masters_and_traceability_reaches_erp_rows(client, tmp_path, gs1_valid_png_fields):
    # ERP 推送料號與工單（只有名為 erp 的 key 可以），之後該工單的檢驗不是臨時檢驗，ERP 輪詢得到工單號
    res = client.post("/api/master/parts:bulk-upsert", json={"parts": [{"part_no": "SC-M6-20", "name": "六角螺栓"}]})
    assert res.status_code == 200, res.text
    res = client.post(
        "/api/master/work-orders:bulk-upsert",
        json={
            "work_orders": [
                {
                    "work_order_no": "WO-9",
                    "part_no": "SC-M6-20",
                    "quantity": 500,
                    "status": "in_progress",
                    "lot_no": "LOT-A1",
                }
            ]
        },
    )
    assert res.status_code == 200 and res.json()["created"], res.text
    png, _ = gs1_valid_png_fields
    inspection_id = _inspect(client, png, "WO-9")

    erp = ErpPoller(client, tmp_path / "erp.db")
    assert erp.poll_once() == 1
    assert erp.rows()[inspection_id][2] == "WO-9"
    assert client.get(f"/api/inspections/{inspection_id}").json()["adhoc"] == 0


@pytest.mark.parametrize("wrong_key", [None, "wrong"])
def test_erp_poll_without_valid_key_is_rejected(api_client, wrong_key):
    from fastapi.testclient import TestClient
    from main import app

    headers = {"X-API-Key": wrong_key} if wrong_key else {}
    assert TestClient(app).get("/api/inspections", headers=headers).status_code == 401
