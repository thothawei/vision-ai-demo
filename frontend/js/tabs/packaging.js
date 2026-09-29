import { setupPreview, callApi, callBatchApi } from "../common.js";

// ⑫ 包裝追溯碼檢核
const packagingFile = document.getElementById("packaging-file");
setupPreview(packagingFile, document.getElementById("packaging-preview"));
document.getElementById("packaging-btn").addEventListener("click", () => {
  const files = Array.from(packagingFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("packaging-status");
  const resultEl = document.getElementById("packaging-result");
  const btn = document.getElementById("packaging-btn");
  if (files.length > 1) { callBatchApi("packaging", files, {}, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/medical/packaging-check", formData, statusEl, resultEl, btn);
});

