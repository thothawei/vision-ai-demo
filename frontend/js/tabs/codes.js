import { setupPreview, callApi, callBatchApi } from "../common.js";

// ③ 追溯碼辨識
const codesFile = document.getElementById("codes-file");
setupPreview(codesFile, document.getElementById("codes-preview"));
document.getElementById("codes-btn").addEventListener("click", () => {
  const files = Array.from(codesFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("codes-status");
  const resultEl = document.getElementById("codes-result");
  const btn = document.getElementById("codes-btn");
  if (files.length > 1) { callBatchApi("codes", files, {}, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/codes/decode", formData, statusEl, resultEl, btn);
});

