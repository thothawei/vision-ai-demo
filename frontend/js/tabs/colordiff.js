import { callApi } from "../common.js";
import { createRectCanvasController } from "../rect-canvas.js";

// ⑮ 烤漆/陽極色差 ΔE（M11）
const colordiffFile = document.getElementById("colordiff-file");
const colordiffCanvas = document.getElementById("colordiff-canvas");
const colordiffCtl = createRectCanvasController(colordiffCanvas);
const colordiffHint = document.getElementById("colordiff-hint");

colordiffFile.addEventListener("change", async () => {
  const file = colordiffFile.files[0];
  if (!file) return;
  await colordiffCtl.loadFile(file);
  colordiffHint.textContent = "按「畫標準色區」或「畫量測區」後在圖上拖曳畫框";
});

document.getElementById("colordiff-draw-ref-btn").addEventListener("click", () => {
  colordiffCtl.setTag("ref");
  colordiffHint.textContent = "現在拖曳畫「標準色區」";
});
document.getElementById("colordiff-draw-measure-btn").addEventListener("click", () => {
  colordiffCtl.setTag("measure");
  colordiffHint.textContent = "現在拖曳畫「量測區」";
});
document.getElementById("colordiff-rect-clear-btn").addEventListener("click", () => colordiffCtl.clear());

document.getElementById("colordiff-manual-lab").addEventListener("change", (e) => {
  document.getElementById("colordiff-manual-lab-fields").style.display = e.target.checked ? "inline" : "none";
});

document.getElementById("colordiff-check-btn").addEventListener("click", () => {
  const file = colordiffFile.files[0];
  if (!file) { alert("請先選擇照片"); return; }
  const useManualLab = document.getElementById("colordiff-manual-lab").checked;
  const measureRect = colordiffCtl.getRect("measure");
  if (!measureRect) { alert("請先按「畫量測區」並在圖上拖曳畫框"); return; }

  const params = new URLSearchParams();
  params.set("threshold", document.getElementById("colordiff-threshold").value || "3.0");
  params.set("measure_rect", JSON.stringify(measureRect));
  if (useManualLab) {
    const l = document.getElementById("colordiff-lab-l").value || "50";
    const a = document.getElementById("colordiff-lab-a").value || "0";
    const b = document.getElementById("colordiff-lab-b").value || "0";
    params.set("ref_lab", JSON.stringify([parseFloat(l), parseFloat(a), parseFloat(b)]));
  } else {
    const refRect = colordiffCtl.getRect("ref");
    if (!refRect) { alert("請先按「畫標準色區」並在圖上拖曳畫框，或勾選手動輸入標準 Lab 值"); return; }
    params.set("ref_rect", JSON.stringify(refRect));
  }

  const formData = new FormData();
  formData.append("file", file);
  callApi("/api/color/check?" + params.toString(), formData,
    document.getElementById("colordiff-status"), document.getElementById("colordiff-result"),
    document.getElementById("colordiff-check-btn"));
});

