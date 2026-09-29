import { setupPreview, callApi, callBatchApi } from "../common.js";

// ④ 計數
const countFile = document.getElementById("count-file");
setupPreview(countFile, document.getElementById("count-preview"));
document.getElementById("count-btn").addEventListener("click", () => {
  const files = Array.from(countFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const expected = document.getElementById("count-expected").value;
  const statusEl = document.getElementById("count-status");
  const resultEl = document.getElementById("count-result");
  const btn = document.getElementById("count-btn");
  if (files.length > 1) {
    callBatchApi("count", files, { expected_count: expected }, {}, statusEl, resultEl, btn);
    return;
  }
  const formData = new FormData();
  formData.append("file", files[0]);
  const url = "/api/measure/count" + (expected ? "?expected_count=" + expected : "");
  callApi(url, formData, statusEl, resultEl, btn);
});

// ④ 量測
const measureFile = document.getElementById("measure-file");
setupPreview(measureFile, document.getElementById("measure-preview"));
document.getElementById("measure-btn").addEventListener("click", () => {
  const files = Array.from(measureFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("measure-status");
  const resultEl = document.getElementById("measure-result");
  const btn = document.getElementById("measure-btn");
  const extraParams = {
    marker_size_mm: document.getElementById("measure-marker").value || "30",
    target_length_mm: document.getElementById("measure-length").value,
    target_width_mm: document.getElementById("measure-width").value,
    tolerance_mm: document.getElementById("measure-tol").value || "1",
  };
  if (files.length > 1) { callBatchApi("measure", files, extraParams, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  const params = new URLSearchParams();
  Object.entries(extraParams).forEach(([k, v]) => { if (v) params.set(k, v); });
  callApi("/api/measure/measure?" + params.toString(), formData, statusEl, resultEl, btn);
});

