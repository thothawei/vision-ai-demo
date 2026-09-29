import { setupPreview, callApi, callBatchApi } from "../common.js";

// ⑦ 安全帽偵測
const ppeFile = document.getElementById("ppe-file");
setupPreview(ppeFile, document.getElementById("ppe-preview"));
document.getElementById("ppe-btn").addEventListener("click", () => {
  const files = Array.from(ppeFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("ppe-status");
  const resultEl = document.getElementById("ppe-result");
  const btn = document.getElementById("ppe-btn");
  if (files.length > 1) { callBatchApi("ppe", files, {}, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/safety/ppe", formData, statusEl, resultEl, btn);
});

