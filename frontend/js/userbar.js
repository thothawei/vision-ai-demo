import { apiFetch } from "./api.js";
import { loadMe, logout, ROLE_LABELS } from "./session.js";

const me = await loadMe();
document.getElementById("userbar-name").textContent =
  `${me.display_name || me.username}（${ROLE_LABELS[me.role] || me.role}）`;
// 操作員欄位留空時，伺服器會帶登入者；在畫面上明說，避免使用者以為沒填就是空白
document.getElementById("trace-operator").placeholder = `留空＝${me.display_name || me.username}`;

document.getElementById("userbar-logout-btn").addEventListener("click", logout);

const card = document.getElementById("password-card");
const statusEl = document.getElementById("pw-status");
document.getElementById("userbar-password-btn").addEventListener("click", () => {
  card.style.display = card.style.display === "none" ? "block" : "none";
});
document.getElementById("pw-cancel-btn").addEventListener("click", () => { card.style.display = "none"; });
document.getElementById("pw-submit-btn").addEventListener("click", async () => {
  statusEl.className = "status";
  statusEl.textContent = "送出中…";
  try {
    const res = await apiFetch("/api/auth/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: document.getElementById("pw-current").value,
        new_password: document.getElementById("pw-new").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "修改失敗");
    statusEl.textContent = "已修改";
    document.getElementById("pw-current").value = "";
    document.getElementById("pw-new").value = "";
  } catch (err) {
    statusEl.textContent = "錯誤：" + err.message;
    statusEl.className = "status error";
  }
});
