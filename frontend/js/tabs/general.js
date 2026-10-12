import { setupPreview, callApi, callBatchApi } from "../common.js";

const generalFile = document.getElementById("general-file");
setupPreview(generalFile, document.getElementById("general-preview"));
document.getElementById("general-btn").addEventListener("click", () => {
  const files = Array.from(generalFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("general-status");
  const resultEl = document.getElementById("general-result");
  const btn = document.getElementById("general-btn");
  if (files.length > 1) { callBatchApi("general", files, {}, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/general/describe", formData, statusEl, resultEl, btn);
});

