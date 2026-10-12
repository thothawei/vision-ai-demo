import { apiFetch } from "../api.js";
import { loadMe } from "../session.js";

const me = await loadMe();
const isAdmin = me.role === "admin";
const CHECK_LABELS = { sqlite: "資料庫（可寫入）", migrations: "資料庫版本", llm: "AI（Ollama／Gemini）", disk: "磁碟空間", jobs: "背景工作" };
const JOB_LABELS = { anomaly_fit: "異常檢測擬合" };
const JOB_STATUS = { queued: "排隊中", running: "執行中", done: "完成", failed: "失敗", interrupted: "已中斷" };

function row(cells) {
  const tr = document.createElement("tr");
  cells.forEach((c) => {
    const td = document.createElement("td");
    if (c instanceof Node) td.appendChild(c); else td.textContent = c ?? "";
    tr.appendChild(td);
  });
  return tr;
}

function badge(text, kind) {
  const span = document.createElement("span");
  span.className = "verdict-badge verdict-" + kind;
  span.textContent = text;
  return span;
}

async function refreshJobs() {
  const res = await apiFetch("/api/jobs?limit=30");
  const body = document.getElementById("system-jobs");
  body.innerHTML = "";
  if (!res.ok) return;
  (await res.json()).forEach((j) => {
    const act = document.createElement("span");
    if (isAdmin && (j.status === "failed" || j.status === "interrupted")) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "重試";
      btn.addEventListener("click", async () => {
        const st = document.getElementById("system-jobs-status");
        const r = await apiFetch(`/api/jobs/${j.id}/retry`, { method: "POST" });
        const data = await r.json();
        st.className = "status" + (r.ok ? "" : " error");
        st.textContent = r.ok ? `已重新排隊工作 #${j.id}` : "錯誤：" + (data.detail || "重試失敗");
        await refresh();
      });
      act.appendChild(btn);
    }
    body.appendChild(row([j.id, JOB_LABELS[j.kind] || j.kind, j.payload.name || "", JOB_STATUS[j.status] || j.status, j.attempts,
      j.finished_at || j.started_at || j.created_at, j.error || "", act]));
  });
}

async function refresh() {
  const res = await apiFetch("/api/system/status?force=true");
  if (!res.ok) return;
  const status = await res.json();
  document.getElementById("system-checked-at").textContent = `檢查時間 ${status.checked_at}（${status.ready ? "就緒" : "未就緒"}${status.degraded ? "，部分功能受影響" : ""}）`;
  const checks = document.getElementById("system-checks");
  checks.innerHTML = "";
  Object.entries(status.checks).forEach(([name, c]) => {
    const kind = c.ok ? "OK" : (c.warning || !["sqlite", "migrations"].includes(name) ? "INFO" : "NG");
    checks.appendChild(row([CHECK_LABELS[name] || name, badge(c.ok ? "正常" : (kind === "NG" ? "失敗" : "注意"), kind), c.message]));
  });
  const features = document.getElementById("system-features");
  features.innerHTML = "";
  status.features.forEach((f) => features.appendChild(row([f.label, badge(f.available ? "可用" : "不可用", f.available ? "OK" : "NG"), f.reason || ""])));
  await refreshJobs();
}

document.getElementById("system-refresh-btn").addEventListener("click", refresh);
document.addEventListener("tab-activated", (e) => { if (e.detail === "system") refresh(); });
