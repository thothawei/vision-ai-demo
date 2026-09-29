import { setupPreview, callApi, callBatchApi } from "../common.js";

// ⑨ 銘牌讀取
const nameplateFile = document.getElementById("nameplate-file");
setupPreview(nameplateFile, document.getElementById("nameplate-preview"));
document.getElementById("nameplate-btn").addEventListener("click", () => {
  const files = Array.from(nameplateFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("nameplate-status");
  const resultEl = document.getElementById("nameplate-result");
  const btn = document.getElementById("nameplate-btn");
  if (files.length > 1) { callBatchApi("nameplate", files, {}, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/nameplate/read", formData, statusEl, resultEl, btn);
});

// ⑩ 七段顯示器
const sevensegFile = document.getElementById("sevenseg-file");
setupPreview(sevensegFile, document.getElementById("sevenseg-preview"));
document.getElementById("sevenseg-btn").addEventListener("click", () => {
  const files = Array.from(sevensegFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("sevenseg-status");
  const resultEl = document.getElementById("sevenseg-result");
  const btn = document.getElementById("sevenseg-btn");
  if (files.length > 1) { callBatchApi("seven_segment", files, {}, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/nameplate/seven-segment", formData, statusEl, resultEl, btn);
});

// ⑪ 指針錶
const gaugeFile = document.getElementById("gauge-file");
setupPreview(gaugeFile, document.getElementById("gauge-preview"));
document.getElementById("gauge-btn").addEventListener("click", () => {
  const files = Array.from(gaugeFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("gauge-status");
  const resultEl = document.getElementById("gauge-result");
  const btn = document.getElementById("gauge-btn");
  const extraParams = {
    min_value: document.getElementById("gauge-min-value").value || "0",
    max_value: document.getElementById("gauge-max-value").value || "100",
    min_angle: document.getElementById("gauge-min-angle").value || "135",
    max_angle: document.getElementById("gauge-max-angle").value || "45",
  };
  if (files.length > 1) { callBatchApi("gauge", files, extraParams, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  const params = new URLSearchParams(extraParams);
  callApi("/api/nameplate/gauge?" + params.toString(), formData, statusEl, resultEl, btn);
});

