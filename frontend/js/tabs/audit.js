import { apiFetch } from "../api.js";
import { loadMe } from "../session.js";

const me = await loadMe();
const body = document.getElementById("audit-body");
const statusEl = document.getElementById("audit-status");
const actionSel = document.getElementById("audit-filter-action");

const ACTION_LABELS = {
  "inspection.review": "複判", "inspection.operator_override": "操作員代簽",
  "user.create": "新增使用者", "user.role_change": "改角色", "user.disable": "停用使用者",
  "user.enable": "啟用使用者", "user.password_reset": "重設密碼", "user.password_change": "自行改密碼",
  "anomaly_threshold.update": "調整異常門檻", "anomaly_category.create": "建立自訂類別",
  "golden_sample.create": "建立黃金樣本", "golden_sample.update": "覆寫黃金樣本",
};
Object.entries(ACTION_LABELS).forEach(([value, label]) => {
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = label;
  actionSel.appendChild(opt);
});

async function refresh() {
  if (me.role !== "admin") return;
  const params = new URLSearchParams();
  const set = (key, id) => { const v = document.getElementById(id).value; if (v) params.set(key, v); };
  set("action", "audit-filter-action");
  set("actor", "audit-filter-actor");
  set("date_from", "audit-filter-from");
  set("date_to", "audit-filter-to");
  statusEl.textContent = "載入中…";
  const res = await apiFetch("/api/audit?" + params.toString());
  const entries = await res.json();
  body.innerHTML = "";
  entries.forEach((e) => {
    const tr = document.createElement("tr");
    for (let i = 0; i < 5; i++) tr.appendChild(document.createElement("td"));
    tr.children[0].textContent = e.at;
    tr.children[1].textContent = e.actor;
    tr.children[2].textContent = ACTION_LABELS[e.action] || e.action;
    tr.children[3].textContent = `${e.target_type} ${e.target_id ?? ""}`;
    tr.children[4].textContent = `${e.before ? JSON.stringify(e.before) : "—"} → ${e.after ? JSON.stringify(e.after) : "—"}`;
    body.appendChild(tr);
  });
  statusEl.textContent = `共 ${entries.length} 筆`;
}

document.getElementById("audit-refresh-btn").addEventListener("click", refresh);
document.addEventListener("tab-activated", (e) => { if (e.detail === "audit") refresh(); });
