import { apiFetch } from "../api.js";

const select = document.getElementById("spc-characteristic");
const statusEl = document.getElementById("spc-status");
let charts = {};

function draw(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), config);
}

function lineSet(label, value, count, color, dash) {
  return { label, data: Array(count).fill(value), borderColor: color, borderDash: dash, pointRadius: 0, borderWidth: 1.5, fill: false };
}

function chartConfig(title, labels, chart, violations, extraLines) {
  const n = chart.points.length;
  const flagged = new Map();
  violations.forEach((v) => flagged.set(v.index, [...(flagged.get(v.index) || []), v.rule]));
  const pointColors = chart.points.map((_, i) => (flagged.has(i) ? "#ff3b30" : "#0071e3"));
  return {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: title, data: chart.points, borderColor: "#0071e3", backgroundColor: "#0071e3", tension: 0,
          pointBackgroundColor: pointColors, pointRadius: chart.points.map((_, i) => (flagged.has(i) ? 6 : 3)) },
        lineSet("UCL", chart.ucl, n, "#ff9500", [6, 4]),
        lineSet("CL", chart.center, n, "#34c759", []),
        lineSet("LCL", chart.lcl, n, "#ff9500", [6, 4]),
        ...(extraLines || []),
      ],
    },
    options: {
      responsive: true,
      plugins: {
        title: { display: true, text: title },
        tooltip: { callbacks: { afterLabel: (ctx) => (ctx.datasetIndex === 0 && flagged.has(ctx.dataIndex) ? "觸發規則 " + flagged.get(ctx.dataIndex).join("、") : "") } },
      },
    },
  };
}

function fmt(v, d = 3) { return v == null ? "—" : Number(v).toFixed(d); }

function renderStats(data) {
  const cap = data.capability;
  const cards = [
    ["資料筆數", data.count],
    [data.type === "xbar_r" ? `子群數（n=${data.subgroup_size}）` : "觀測值", data.subgroups],
    ["規格下限／上限", `${fmt(cap.lsl, 2)} ／ ${fmt(cap.usl, 2)}`],
    ["Cp", fmt(cap.cp)], ["Cpk", fmt(cap.cpk)],
  ];
  const row = document.getElementById("spc-stats");
  row.innerHTML = "";
  cards.forEach(([label, value]) => {
    const div = document.createElement("div");
    div.className = "dash-stat";
    div.innerHTML = `<div class="label"></div><div class="value"></div>`;
    div.querySelector(".label").textContent = label;
    div.querySelector(".value").textContent = value;
    row.appendChild(div);
  });
  const notes = [];
  if (cap.reference_only && cap.cpk != null) notes.push("子群少於 25 組，能力指標僅供參考");
  if (cap.note) notes.push(cap.note);
  if (data.spec.changed) notes.push("這段期間規格有變動，能力指標採用最近的規格");
  if (data.ignored_tail) notes.push(`最後 ${data.ignored_tail} 筆不足一個子群，未納入`);
  statusEl.className = "status";
  statusEl.textContent = notes.join("；");
}

async function loadCharacteristics() {
  const res = await apiFetch("/api/spc/characteristics");
  if (!res.ok) return;
  const list = await res.json();
  const keep = select.value;
  select.innerHTML = "";
  list.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = JSON.stringify([c.part_no, c.characteristic]);
    opt.textContent = `${c.part_label}／${c.characteristic}（${c.count} 筆${c.has_spec ? "" : "，無規格"}）`;
    select.appendChild(opt);
  });
  if (keep) select.value = keep;
  if (!list.length) statusEl.textContent = "還沒有量測資料：做過尺寸量測、色差、指針錶或七段顯示器辨識後就會出現。";
}

async function refresh() {
  if (!select.value) return;
  const [partNo, characteristic] = JSON.parse(select.value);
  const params = new URLSearchParams({
    characteristic, chart: document.getElementById("spc-chart").value,
    subgroup_size: document.getElementById("spc-subgroup").value || "5",
    run_length: document.getElementById("spc-run").value || "8",
  });
  if (partNo) params.set("part_no", partNo);
  const setIf = (key, id) => { const v = document.getElementById(id).value.trim(); if (v) params.set(key, v); };
  setIf("station", "spc-station"); setIf("from", "spc-from"); setIf("to", "spc-to");
  statusEl.className = "status";
  statusEl.textContent = "載入中…";
  const res = await apiFetch("/api/spc?" + params.toString());
  const data = await res.json();
  const tbody = document.getElementById("spc-violations");
  tbody.innerHTML = "";
  if (!res.ok) {
    statusEl.textContent = "錯誤：" + (typeof data.detail === "string" ? data.detail : "查詢失敗");
    statusEl.className = "status error";
    return;
  }
  if (data.insufficient_data) {
    Object.values(charts).forEach((c) => c.destroy());
    charts = {};
    document.getElementById("spc-stats").innerHTML = "";
    statusEl.textContent = data.message;
    return;
  }
  renderStats(data);
  const unit = data.unit ? `（${data.unit}）` : "";
  const isXbar = data.type === "xbar_r";
  draw("spc-chart-x", chartConfig(isXbar ? `X̄ 圖${unit}` : `個別值圖 I${unit}`, data.labels, data.x_chart, data.violations));
  const rangeLabels = isXbar ? data.labels : data.labels.slice(1);
  draw("spc-chart-r", chartConfig(isXbar ? "R 圖（全距）" : "MR 圖（移動全距）", rangeLabels, data.range_chart, data.range_violations));
  const rules = { 1: "1 一點超出 3σ", 2: "2 三點中兩點超出 2σ", 3: "3 五點中四點超出 1σ", 4: `4 連續 ${data.run_length} 點同側` };
  [["X̄／I", data.violations], ["R／MR", data.range_violations]].forEach(([chart, list]) => {
    list.forEach((v) => {
      const tr = document.createElement("tr");
      [chart, rules[v.rule], v.position, Number(v.value).toFixed(3), v.side + "側"].forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  });
}

document.getElementById("spc-refresh-btn").addEventListener("click", refresh);
select.addEventListener("change", refresh);
document.addEventListener("tab-activated", async (e) => {
  if (e.detail !== "spc") return;
  await loadCharacteristics();
  await refresh();
});
