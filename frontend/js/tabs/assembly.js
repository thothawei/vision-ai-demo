import { setupPreview, traceHeaders, callApi } from "../common.js";
import { createRectCanvasController } from "../rect-canvas.js";
import { apiFetch } from "../api.js";

// ⑭ 組裝防呆比對（M10）
const assemblyGoldenFile = document.getElementById("assembly-golden-file");
const assemblyGoldenCanvas = document.getElementById("assembly-golden-canvas");
const assemblyGoldenCtl = createRectCanvasController(assemblyGoldenCanvas);
const assemblyGoldenHint = document.getElementById("assembly-golden-hint");

assemblyGoldenFile.addEventListener("change", async () => {
  const file = assemblyGoldenFile.files[0];
  if (!file) return;
  await assemblyGoldenCtl.loadFile(file);
  assemblyGoldenHint.textContent = "在圖上拖曳畫出每個零件應該在的 ROI，可以畫多個";
});

document.getElementById("assembly-roi-undo-btn").addEventListener("click", () => assemblyGoldenCtl.removeLast());
document.getElementById("assembly-roi-clear-btn").addEventListener("click", () => assemblyGoldenCtl.clear());

async function refreshAssemblyPartTable() {
  const res = await apiFetch("/api/assembly/golden-samples");
  const parts = await res.json();
  const tbody = document.getElementById("assembly-part-tbody");
  tbody.innerHTML = "";
  parts.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${p.part_no}</td><td>${p.roi_count}</td>`;
    tbody.appendChild(tr);
  });
  const select = document.getElementById("assembly-inspect-part");
  const current = select.value;
  select.innerHTML = "";
  parts.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.part_no; opt.textContent = p.part_no;
    select.appendChild(opt);
  });
  if (parts.some((p) => p.part_no === current)) select.value = current;
}

document.getElementById("assembly-save-golden-btn").addEventListener("click", async () => {
  const partNo = document.getElementById("assembly-part-no").value.trim();
  const statusEl = document.getElementById("assembly-save-status");
  const file = assemblyGoldenFile.files[0];
  const rois = assemblyGoldenCtl.getAllRects();
  if (!partNo) { alert("請輸入料號"); return; }
  if (!file) { alert("請先選擇黃金樣本照片"); return; }
  if (rois.length === 0) { alert("至少要畫 1 個 ROI"); return; }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("rois", JSON.stringify(rois));
  statusEl.textContent = "儲存中…";
  statusEl.className = "status";
  try {
    const res = await apiFetch("/api/assembly/golden-samples?part_no=" + encodeURIComponent(partNo), {
      method: "POST", body: formData, headers: traceHeaders(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "儲存失敗");
    statusEl.textContent = `已儲存：${data.part_no}（${data.roi_count} 個 ROI）`;
    await refreshAssemblyPartTable();
  } catch (err) {
    statusEl.textContent = "錯誤：" + err.message;
    statusEl.className = "status error";
  }
});

const assemblyInspectFile = document.getElementById("assembly-inspect-file");
setupPreview(assemblyInspectFile, document.getElementById("assembly-inspect-preview"));
document.getElementById("assembly-inspect-btn").addEventListener("click", () => {
  const files = Array.from(assemblyInspectFile.files);
  const partNo = document.getElementById("assembly-inspect-part").value;
  if (files.length === 0) { alert("請先選擇照片"); return; }
  if (!partNo) { alert("請先建立至少一個料號設定"); return; }
  const statusEl = document.getElementById("assembly-inspect-status");
  const resultEl = document.getElementById("assembly-inspect-result");
  const btn = document.getElementById("assembly-inspect-btn");
  const formData = new FormData();
  formData.append("file", files[0]);
  callApi("/api/assembly/inspect?part_no=" + encodeURIComponent(partNo), formData, statusEl, resultEl, btn);
});

refreshAssemblyPartTable();

