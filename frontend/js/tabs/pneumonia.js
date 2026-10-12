import { setupPreview, callApi, callBatchApi } from "../common.js";

// ⑬ 醫學影像分類展示
const pneumoniaFile = document.getElementById("pneumonia-file");
setupPreview(pneumoniaFile, document.getElementById("pneumonia-preview"));
document.getElementById("pneumonia-btn").addEventListener("click", () => {
  const files = Array.from(pneumoniaFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("pneumonia-status");
  const resultEl = document.getElementById("pneumonia-result");
  const btn = document.getElementById("pneumonia-btn");
  if (files.length > 1) { callBatchApi("pneumonia", files, {}, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/medical/pneumonia-demo", formData, statusEl, resultEl, btn);
});

