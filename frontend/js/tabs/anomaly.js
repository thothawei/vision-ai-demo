import { setupPreview, traceHeaders, callApi, callBatchApi } from "../common.js";

// ⑥ 異常檢測
const anomalyFile = document.getElementById("anomaly-file");
setupPreview(anomalyFile, document.getElementById("anomaly-preview"));
document.getElementById("anomaly-btn").addEventListener("click", () => {
  const files = Array.from(anomalyFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const category = document.getElementById("anomaly-category").value;
  const statusEl = document.getElementById("anomaly-status");
  const resultEl = document.getElementById("anomaly-result");
  const btn = document.getElementById("anomaly-btn");
  if (files.length > 1) { callBatchApi("anomaly", files, { category }, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/anomaly/inspect?category=" + category, formData, statusEl, resultEl, btn);
});

// ⑥ 異常檢測：Phase 12 自訂類別（上傳 zip → 背景排隊擬合 → 門檻調校）
const STATUS_LABELS = { queued: "排隊中", fitting: "擬合中…", done: "完成", failed: "失敗" };
let anomalyPollTimer = null;
let currentThresholdScores = null;
let currentThresholdCategory = null;
let thresholdChart = null;

async function refreshAnomalyCategoryDropdown() {
  const res = await fetch("/api/anomaly/categories/all");
  const data = await res.json();
  const select = document.getElementById("anomaly-category");
  const current = select.value;
  const builtinValues = new Set(["metal_nut", "screw", "tile"]);
  Array.from(select.options).forEach((opt) => {
    if (!builtinValues.has(opt.value)) opt.remove();
  });
  data.categories.filter((c) => !builtinValues.has(c)).forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name; opt.textContent = name + "（自訂）";
    select.appendChild(opt);
  });
  if (Array.from(select.options).some((o) => o.value === current)) select.value = current;
}

async function refreshAnomalyCategoryTable() {
  const res = await fetch("/api/anomaly/categories");
  const categories = await res.json();
  const tbody = document.getElementById("anomaly-category-tbody");
  tbody.innerHTML = "";
  let hasPending = false;
  categories.forEach((c) => {
    if (c.status === "queued" || c.status === "fitting") hasPending = true;
    const tr = document.createElement("tr");
    const auroc = c.image_auroc != null ? c.image_auroc : "—";
    const threshold = c.threshold != null ? c.threshold.toFixed(4) : "—";
    const countLabel = `${c.good_count ?? "—"} / ${c.defect_count ?? 0}`;
    const tuneBtn = c.status === "done" ? `<button type="button" class="anomaly-tune-btn" data-name="${c.name}">門檻調校</button>` : "";
    const errorHint = c.status === "failed" && c.error ? `<div class="hint" style="color:#ff3b30;">${c.error}</div>` : "";
    tr.innerHTML = `<td>${c.name}</td><td>${STATUS_LABELS[c.status] || c.status}${errorHint}</td>
      <td>${countLabel}</td><td>${auroc}</td><td>${threshold}</td><td>${tuneBtn}</td>`;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll(".anomaly-tune-btn").forEach((btn) => {
    btn.addEventListener("click", () => openThresholdPanel(btn.dataset.name));
  });

  if (hasPending && !anomalyPollTimer) {
    anomalyPollTimer = setInterval(async () => {
      await refreshAnomalyCategoryTable();
      await refreshAnomalyCategoryDropdown();
    }, 3000);
  } else if (!hasPending && anomalyPollTimer) {
    clearInterval(anomalyPollTimer);
    anomalyPollTimer = null;
  }
}

document.getElementById("anomaly-create-btn").addEventListener("click", async () => {
  const name = document.getElementById("anomaly-new-name").value.trim();
  const goodFile = document.getElementById("anomaly-good-zip").files[0];
  const defectFile = document.getElementById("anomaly-defect-zip").files[0];
  const statusEl = document.getElementById("anomaly-create-status");
  if (!name) { alert("請輸入類別名稱"); return; }
  if (!goodFile) { alert("請上傳良品照片 zip"); return; }
  const formData = new FormData();
  formData.append("good_zip", goodFile);
  if (defectFile) formData.append("defect_zip", defectFile);
  statusEl.textContent = "送出中…";
  statusEl.className = "status";
  try {
    const res = await fetch("/api/anomaly/categories?name=" + encodeURIComponent(name), {
      method: "POST", body: formData, headers: traceHeaders(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "送出失敗");
    statusEl.textContent = `已排隊：${data.name}（${data.good_count} 張良品／${data.defect_count} 張 NG）`;
    document.getElementById("anomaly-new-name").value = "";
    document.getElementById("anomaly-good-zip").value = "";
    document.getElementById("anomaly-defect-zip").value = "";
    await refreshAnomalyCategoryTable();
  } catch (err) {
    statusEl.textContent = "錯誤：" + err.message;
    statusEl.className = "status error";
  }
});

function computeThresholdRates(scores, threshold) {
  const good = scores.filter((s) => s.label === "good");
  const defect = scores.filter((s) => s.label === "defect");
  const falsePositive = good.filter((s) => s.score >= threshold).length; // 良品被誤判 NG
  const falseNegative = defect.filter((s) => s.score < threshold).length; // NG 被漏判成 OK
  return {
    goodTotal: good.length, defectTotal: defect.length,
    falsePositiveRate: good.length ? falsePositive / good.length : null,
    falseNegativeRate: defect.length ? falseNegative / defect.length : null,
  };
}

function renderThresholdChart(scores) {
  const good = scores.filter((s) => s.label === "good").map((s) => s.score);
  const defect = scores.filter((s) => s.label === "defect").map((s) => s.score);
  const all = scores.map((s) => s.score);
  const min = Math.min(...all), max = Math.max(...all);
  const binCount = 15;
  const binSize = (max - min) / binCount || 1;
  const bins = Array.from({ length: binCount }, (_, i) => min + i * binSize);
  const countIn = (arr, lo, hi) => arr.filter((v) => v >= lo && (v < hi || (hi === max && v <= hi))).length;
  const goodCounts = bins.map((lo, i) => countIn(good, lo, i === binCount - 1 ? max : bins[i + 1]));
  const defectCounts = bins.map((lo, i) => countIn(defect, lo, i === binCount - 1 ? max : bins[i + 1]));

  if (thresholdChart) thresholdChart.destroy();
  thresholdChart = new Chart(document.getElementById("anomaly-threshold-chart"), {
    type: "bar",
    data: {
      labels: bins.map((b) => b.toFixed(3)),
      datasets: [
        { label: "良品分數分佈", data: goodCounts, backgroundColor: "#34c75999" },
        { label: "NG 分數分佈", data: defectCounts, backgroundColor: "#ff3b3099" },
      ],
    },
    options: { responsive: true, scales: { x: { stacked: false }, y: { title: { display: true, text: "張數" } } } },
  });
}

async function openThresholdPanel(name) {
  const panel = document.getElementById("anomaly-threshold-panel");
  const statusEntry = (await (await fetch("/api/anomaly/categories/" + name + "/status")).json());
  const res = await fetch("/api/anomaly/categories/" + name + "/scores");
  if (!res.ok) { alert("讀取評分資料失敗"); return; }
  const scores = await res.json();
  currentThresholdScores = scores;
  currentThresholdCategory = name;
  document.getElementById("anomaly-threshold-category-name").textContent = name;
  panel.style.display = "block";
  renderThresholdChart(scores);

  const allScores = scores.map((s) => s.score);
  const slider = document.getElementById("anomaly-threshold-slider");
  slider.min = Math.min(...allScores);
  slider.max = Math.max(...allScores);
  slider.step = (slider.max - slider.min) / 200 || 0.001;
  slider.value = statusEntry.threshold != null ? statusEntry.threshold : (slider.min + slider.max) / 2;
  updateThresholdDisplay();
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function updateThresholdDisplay() {
  const slider = document.getElementById("anomaly-threshold-slider");
  const threshold = parseFloat(slider.value);
  document.getElementById("anomaly-threshold-value").textContent = threshold.toFixed(4);
  const rates = computeThresholdRates(currentThresholdScores, threshold);
  const fpPct = rates.falsePositiveRate != null ? (rates.falsePositiveRate * 100).toFixed(1) + "%" : "—";
  const fnPct = rates.falseNegativeRate != null ? (rates.falseNegativeRate * 100).toFixed(1) + "%" : "—";
  document.getElementById("anomaly-threshold-rates").textContent =
    `良品誤判率（誤判成 NG）：${fpPct}（${rates.goodTotal} 張良品）／NG 漏判率（漏判成 OK）：${fnPct}（${rates.defectTotal} 張 NG）`;
}

document.getElementById("anomaly-threshold-slider").addEventListener("input", updateThresholdDisplay);

document.getElementById("anomaly-threshold-save-btn").addEventListener("click", async () => {
  const threshold = parseFloat(document.getElementById("anomaly-threshold-slider").value);
  const statusEl = document.getElementById("anomaly-threshold-save-status");
  statusEl.textContent = "儲存中…";
  try {
    const res = await fetch(`/api/anomaly/categories/${currentThresholdCategory}/threshold`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threshold }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "儲存失敗");
    statusEl.textContent = "已儲存";
    await refreshAnomalyCategoryTable();
  } catch (err) {
    statusEl.textContent = "錯誤：" + err.message;
  }
});

refreshAnomalyCategoryTable();
refreshAnomalyCategoryDropdown();

