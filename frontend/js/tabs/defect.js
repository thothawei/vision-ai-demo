import { setupPreview, callApi, callBatchApi } from "../common.js";

// ⑧ PCB 瑕疵偵測
const defectFile = document.getElementById("defect-file");
setupPreview(defectFile, document.getElementById("defect-preview"));
document.getElementById("defect-btn").addEventListener("click", () => {
  const files = Array.from(defectFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("defect-status");
  const resultEl = document.getElementById("defect-result");
  const btn = document.getElementById("defect-btn");
  if (files.length > 1) { callBatchApi("defect", files, {}, {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/defect/pcb", formData, statusEl, resultEl, btn);
});

