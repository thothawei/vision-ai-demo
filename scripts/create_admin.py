"""建立（第一個）admin 帳號。密碼用互動輸入，不會出現在指令列或程式碼裡。

用法：
    python scripts/create_admin.py --username admin --display-name 系統管理員

沒有任何 admin 時，這是唯一建立第一個帳號的方式（程式內不寫預設帳密）。
之後的使用者請由 admin 在「管理 → 使用者」建立。
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from core import audit, users  # noqa: E402


def create_admin(username: str, display_name: str, password: str) -> dict:
    user = users.create_user(username, display_name, password, "admin")
    audit.record("script:create_admin", "user.create", "user", user["id"],
                 after={k: user[k] for k in ("username", "display_name", "role", "is_active")})
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description="建立 admin 帳號")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", dest="display_name", required=True)
    args = parser.parse_args()

    password = getpass.getpass(f"密碼（至少 {users.MIN_PASSWORD_LENGTH} 字元）：")
    if password != getpass.getpass("再輸入一次："):
        sys.exit("兩次輸入的密碼不一致")
    try:
        user = create_admin(args.username, args.display_name, password)
    except ValueError as e:
        sys.exit(f"建立失敗：{e}")
    print(f"已建立 admin：{user['username']}（{user['display_name']}）")


if __name__ == "__main__":
    main()
