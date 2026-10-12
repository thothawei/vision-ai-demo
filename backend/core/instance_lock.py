"""單一實例鎖：同一個資料庫同一時間只允許一個服務程序使用。

背景工作（擬合）的恢復邏輯與輪詢式 worker 都假設單一程序：新啟動的程序會把「還在 running」的工作視為被中斷。
如果不小心在同一個資料庫上再啟動第二個程序（例如埠號衝突、多開 `--workers`），它會把第一個程序正在做的工作
誤標成中斷。所以改成強制：用檔案鎖（`<資料庫>.lock`）保證同一時間只有一個程序，拿不到鎖就拒絕啟動並說明原因。

鎖由作業系統在程序結束（包含被 kill）時自動釋放，不會留下永遠卡住的鎖。
"""

import os
from pathlib import Path


class InstanceLockError(RuntimeError):
    pass


def _try_lock(handle) -> bool:
    try:
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except ImportError:  # Windows（尚未實測）
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    except OSError:
        return False


def acquire(db_path: Path):
    """取得資料庫的單一實例鎖，回傳要一直持有的檔案物件（釋放就呼叫 `release`）；拿不到就丟 InstanceLockError。"""
    lock_path = db_path.with_name(db_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")
    if not _try_lock(handle):
        handle.seek(0)
        holder = handle.read().strip() or "未知"
        handle.close()
        raise InstanceLockError(
            f"另一個程序（PID {holder}）正在使用這個資料庫（{db_path.name}），本系統同一個資料庫同一時間只能有一個服務程序；"
            "請先停止另一個程序（不要用多個 uvicorn worker），確定沒有程序在跑再重試"
        )
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def release(handle) -> None:
    try:
        handle.close()  # 關閉檔案就會釋放鎖
    except OSError:
        pass
