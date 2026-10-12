import { setupPreview, callApi, callBatchApi } from "../common.js";

const docsFile = document.getElementById("docs-file");
setupPreview(docsFile, document.getElementById("docs-preview"));
document.getElementById("docs-btn").addEventListener("click", () => {
  const files = Array.from(docsFile.files);
  if (files.length === 0) { alert("請先選擇圖檔"); return; }
  const mode = document.getElementById("docs-mode").value;
  const statusEl = document.getElementById("docs-status");
  const resultEl = document.getElementById("docs-result");
  const btn = document.getElementById("docs-btn");
  if (files.length > 1) { callBatchApi("docs", files, { mode }, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/docs/extract?mode=" + mode, formData, statusEl, resultEl, btn);
});

