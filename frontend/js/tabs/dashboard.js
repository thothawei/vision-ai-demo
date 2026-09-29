import { loadCatalog } from "../catalog.js";

// ⑰ 品檢紀錄與看板

// Phase 10：/api/inspections* 現在需要 X-API-Key，這組 key 要跟後端 .env 的 API_KEYS
// 裡 frontend: 那組一致（單機部署的取捨：兩邊各自一份設定，換 key 要兩邊一起改）。
const FRONTEND_API_KEY = "dev-frontend-key-change-me";

function apiKeyHeaders(extra) {
  return Object.assign({ "X-API-Key": FRONTEND_API_KEY }, extra || {});
}

function withApiKeyParam(params) {
  params.set("api_key", FRONTEND_API_KEY); // <img src> 與純連結下載無法帶自訂 header，退回 query 參數
  return params;
}

const dashModuleSelect = document.getElementById("dash-filter-module");
const { modules: MODULE_LABELS } = await loadCatalog();
Object.entries(MODULE_LABELS).forEach(([value, label]) => {
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = label;
  dashModuleSelect.appendChild(opt);
});

let dashCharts = {};

function dashFilterParams() {
  const params = new URLSearchParams();
  const module = document.getElementById("dash-filter-module").value;
  const verdict = document.getElementById("dash-filter-verdict").value;
  const workOrder = document.getElementById("dash-filter-work-order").value.trim();
  const partNo = document.getElementById("dash-filter-part-no").value.trim();
  const dateFrom = document.getElementById("dash-filter-from").value;
  const dateTo = document.getElementById("dash-filter-to").value;
  if (module) params.set("module", module);
  if (verdict) params.set("verdict", verdict);
  if (workOrder) params.set("work_order", workOrder);
  if (partNo) params.set("part_no", partNo);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  return params;
}

function renderDashChart(id, config) {
  if (dashCharts[id]) dashCharts[id].destroy();
  dashCharts[id] = new Chart(document.getElementById(id), config);
}

async function fetchStats(groupBy) {
  const params = dashFilterParams();
  params.set("group_by", groupBy);
  const res = await fetch("/api/inspections/stats?" + params.toString(), { headers: apiKeyHeaders() });
  if (!res.ok) throw new Error((await res.json()).detail || "看板統計失敗");
  return res.json();
}

function renderStatRow(overall) {
  const row = document.getElementById("dash-stat-row");
  const pct = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
  const cards = [
    ["總筆數", overall.total],
    ["AI 良率", pct(overall.ai_yield)],
    ["最終良率（含複判）", pct(overall.final_yield)],
    ["已複判筆數", overall.reviewed_count],
    ["AI／人工一致率", pct(overall.consistency_rate)],
  ];
  row.innerHTML = "";
  cards.forEach(([label, value]) => {
    const div = document.createElement("div");
    div.className = "dash-stat";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
    row.appendChild(div);
  });
}

async function refreshDashboard() {
  const statusEl = document.getElementById("dash-status");
  statusEl.textContent = "載入中…";
  statusEl.className = "status";
  try {
    const [byModule, byDay, byDefect] = await Promise.all([
      fetchStats("module"), fetchStats("day"), fetchStats("defect"),
    ]);
    renderStatRow(byModule);

    renderDashChart("dash-chart-day", {
      type: "line",
      data: {
        labels: byDay.groups.map((g) => g.day),
        datasets: [{
          label: "每日良率（最終判定）",
          data: byDay.groups.map((g) => g.yield == null ? null : g.yield * 100),
          borderColor: "#0071e3", backgroundColor: "#0071e355", tension: 0.2,
        }],
      },
      options: { responsive: true, scales: { y: { min: 0, max: 100, title: { display: true, text: "良率 %" } } } },
    });

    renderDashChart("dash-chart-defect", {
      type: "bar",
      data: {
        labels: byDefect.groups.map((g) => g.label),
        datasets: [
          { type: "bar", label: "NG 原因次數", data: byDefect.groups.map((g) => g.count), backgroundColor: "#ff3b3099", yAxisID: "y" },
          { type: "line", label: "累積百分比", data: byDefect.groups.map((g) => g.cum_pct), borderColor: "#ff9500", yAxisID: "y1" },
        ],
      },
      options: {
        responsive: true,
        plugins: { title: { display: true, text: "NG 原因柏拉圖" } },
        scales: {
          y: { position: "left", title: { display: true, text: "次數" } },
          y1: { position: "right", min: 0, max: 100, grid: { drawOnChartArea: false }, title: { display: true, text: "累積 %" } },
        },
      },
    });

    renderDashChart("dash-chart-module", {
      type: "bar",
      data: {
        labels: byModule.groups.map((g) => MODULE_LABELS[g.module] || g.module),
        datasets: [
          { label: "OK", data: byModule.groups.map((g) => g.OK), backgroundColor: "#34c759" },
          { label: "NG", data: byModule.groups.map((g) => g.NG), backgroundColor: "#ff3b30" },
          { label: "INFO", data: byModule.groups.map((g) => g.INFO), backgroundColor: "#0071e3" },
        ],
      },
      options: { responsive: true, plugins: { title: { display: true, text: "各模組件數" } }, scales: { x: { stacked: true }, y: { stacked: true } } },
    });

    await refreshDashTable();
    statusEl.textContent = "完成";
  } catch (err) {
    statusEl.textContent = "錯誤：" + err.message;
    statusEl.className = "status error";
  }
}

function verdictBadgeHtml(verdict) {
  return `<span class="verdict-badge verdict-${verdict}">${verdict}</span>`;
}

async function refreshDashTable() {
  const params = dashFilterParams();
  const res = await fetch("/api/inspections?" + params.toString(), { headers: apiKeyHeaders() });
  const records = await res.json();
  const tbody = document.getElementById("dash-table-body");
  tbody.innerHTML = "";
  records.forEach((r) => {
    const finalVerdict = r.review_verdict || r.verdict;
    const tr = document.createElement("tr");
    tr.className = "clickable";
    tr.innerHTML = `<td>${r.id}</td><td>${r.created_at}</td><td>${MODULE_LABELS[r.module] || r.module}</td>
      <td>${verdictBadgeHtml(r.verdict)}</td><td>${verdictBadgeHtml(finalVerdict)}</td>
      <td>${r.work_order || ""}</td><td>${r.part_no || ""}</td>`;
    const detailRow = document.createElement("tr");
    const detailTd = document.createElement("td");
    detailTd.colSpan = 7;
    detailTd.appendChild(buildDetailPanel(r));
    detailRow.appendChild(detailTd);
    detailRow.style.display = "none";
    tr.addEventListener("click", () => {
      detailRow.style.display = detailRow.style.display === "none" ? "table-row" : "none";
    });
    tbody.appendChild(tr);
    tbody.appendChild(detailRow);
  });
}

function buildDetailPanel(record) {
  const wrap = document.createElement("div");
  wrap.className = "dash-detail";

  if (record.image_path) {
    const img = document.createElement("img");
    img.src = `/api/inspections/${record.id}/image?` + withApiKeyParam(new URLSearchParams({ kind: "raw" })).toString();
    img.alt = "原圖";
    wrap.appendChild(img);
  }
  if (record.annotated_path) {
    const img = document.createElement("img");
    img.src = `/api/inspections/${record.id}/image?` + withApiKeyParam(new URLSearchParams({ kind: "annotated" })).toString();
    img.alt = "標註圖";
    wrap.appendChild(img);
  }
  const extraLabels = { golden: "黃金樣本", reference: "參考圖" };
  Object.keys(record.images || {}).forEach((role) => {
    const img = document.createElement("img");
    img.src = `/api/inspections/${record.id}/image?` + withApiKeyParam(new URLSearchParams({ kind: role })).toString();
    img.alt = extraLabels[role] || role;
    wrap.appendChild(img);
  });

  const pre = document.createElement("pre");
  pre.style.whiteSpace = "pre-wrap";
  pre.style.fontSize = "12px";
  pre.textContent = JSON.stringify(record.summary, null, 2);
  wrap.appendChild(pre);

  const reviewForm = document.createElement("div");
  reviewForm.className = "row";
  reviewForm.innerHTML = `
    <select class="review-verdict"><option value="OK">複判為 OK</option><option value="NG">複判為 NG</option></select>
    <input type="text" class="review-reviewer" placeholder="複判人">
    <input type="text" class="review-note" placeholder="備註（選填）">
    <button type="button" class="review-submit-btn">送出複判</button>
    <span class="review-msg hint"></span>
  `;
  wrap.appendChild(reviewForm);
  if (record.review_verdict) {
    const info = document.createElement("div");
    info.className = "hint";
    info.textContent = `已複判：${record.review_verdict}（${record.reviewer || "未填"}，${record.reviewed_at}）${record.review_note ? " － " + record.review_note : ""}`;
    wrap.appendChild(info);
  }

  reviewForm.querySelector(".review-submit-btn").addEventListener("click", async (e) => {
    e.stopPropagation();
    const verdict = reviewForm.querySelector(".review-verdict").value;
    const reviewer = reviewForm.querySelector(".review-reviewer").value.trim();
    const note = reviewForm.querySelector(".review-note").value.trim();
    const msg = reviewForm.querySelector(".review-msg");
    msg.textContent = "送出中…";
    try {
      const res = await fetch(`/api/inspections/${record.id}/review`, {
        method: "PATCH",
        headers: apiKeyHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ review_verdict: verdict, reviewer: reviewer || null, review_note: note || null }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "複判失敗");
      msg.textContent = "已送出，良率統計更新中…";
      await refreshDashboard();
    } catch (err) {
      msg.textContent = "錯誤：" + err.message;
    }
  });
  wrap.addEventListener("click", (e) => e.stopPropagation());

  return wrap;
}

document.getElementById("dash-refresh-btn").addEventListener("click", refreshDashboard);
document.getElementById("dash-export-btn").addEventListener("click", () => {
  const params = withApiKeyParam(dashFilterParams());
  window.open("/api/inspections/export.csv?" + params.toString(), "_blank");
});
document.addEventListener("tab-activated", (e) => { if (e.detail === "dashboard") refreshDashboard(); });
