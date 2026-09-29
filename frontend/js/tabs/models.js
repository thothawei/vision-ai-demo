import { apiFetch } from "../api.js";
import { loadMe } from "../session.js";

const me = await loadMe();
const isAdmin = me.role === "admin";
const listEl = document.getElementById("models-list");
const statusEl = document.getElementById("models-status");

function metricSummary(metrics) {
  return Object.entries(metrics || {})
    .filter(([k, v]) => k !== "來源" && k !== "weights_path" && typeof v !== "object")
    .slice(0, 5)
    .map(([k, v]) => `${k}=${v}`)
    .join("，");
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text ?? "";
  return td;
}

async function activate(modelId, version) {
  statusEl.className = "status";
  statusEl.textContent = "切換中…";
  const res = await apiFetch(`/api/models/${encodeURIComponent(modelId)}/versions/${version}/activate`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) {
    statusEl.textContent = "錯誤：" + (typeof data.detail === "string" ? data.detail : "切換失敗");
    statusEl.className = "status error";
    return;
  }
  statusEl.textContent = `已啟用 ${modelId} v${version}`;
  await refresh();
}

async function refresh() {
  const res = await apiFetch("/api/models");
  if (!res.ok) return;
  const models = await res.json();
  listEl.innerHTML = "";
  if (!models.length) {
    listEl.textContent = "還沒有登錄任何模型：第一次使用內建模型（PCB、安全帽、人員、異常檢測、肺炎展示）時會自動登錄成 v1。";
    return;
  }
  models.forEach((m) => {
    const box = document.createElement("div");
    box.className = "card";
    const title = document.createElement("h3");
    title.textContent = `${m.title}（${m.model_id}）`;
    box.appendChild(title);
    const table = document.createElement("table");
    table.className = "dash-table";
    table.innerHTML = "<thead><tr><th>版本</th><th>狀態</th><th>指標</th><th>SHA-256</th><th>大小</th><th>備註</th><th>登錄</th><th></th></tr></thead>";
    const body = document.createElement("tbody");
    m.versions.forEach((v) => {
      const tr = document.createElement("tr");
      tr.append(cell(`v${v.version}`), cell(v.status === "active" ? "啟用中" : "封存"), cell(metricSummary(v.metrics)),
        cell(v.sha256.slice(0, 12)), cell(`${(v.size_bytes / 1024 / 1024).toFixed(1)} MB`), cell(v.note),
        cell(`${v.registered_by}，${v.created_at}`));
      const act = document.createElement("td");
      if (isAdmin && v.status !== "active") {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = "啟用（回滾）";
        btn.addEventListener("click", () => {
          if (confirm(`確定要把 ${m.model_id} 切換到 v${v.version}？之後的檢驗會使用這個版本。`)) activate(m.model_id, v.version);
        });
        act.appendChild(btn);
      }
      tr.appendChild(act);
      body.appendChild(tr);
    });
    table.appendChild(body);
    box.appendChild(table);
    listEl.appendChild(box);
  });
}

document.addEventListener("tab-activated", (e) => { if (e.detail === "models") refresh(); });
