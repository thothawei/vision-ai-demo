import { callApi } from "../common.js";

// ⑤ 危險區域入侵：canvas 點擊畫多邊形
const safetyFile = document.getElementById("safety-file");
const safetyCanvas = document.getElementById("safety-canvas");
const safetyCtx = safetyCanvas.getContext("2d");
const safetyHint = document.getElementById("safety-zone-hint");
let safetyImg = null;
let zonePoints = []; // 正規化座標 [[x,y],...]
let zoneClosed = false;

function redrawSafetyCanvas() {
  safetyCtx.clearRect(0, 0, safetyCanvas.width, safetyCanvas.height);
  safetyCtx.drawImage(safetyImg, 0, 0, safetyCanvas.width, safetyCanvas.height);
  if (zonePoints.length === 0) return;
  safetyCtx.beginPath();
  zonePoints.forEach(([x, y], i) => {
    const px = x * safetyCanvas.width, py = y * safetyCanvas.height;
    if (i === 0) safetyCtx.moveTo(px, py); else safetyCtx.lineTo(px, py);
  });
  if (zoneClosed) safetyCtx.closePath();
  safetyCtx.strokeStyle = "#ff3b30";
  safetyCtx.lineWidth = 2;
  safetyCtx.stroke();
  if (zoneClosed) {
    safetyCtx.fillStyle = "rgba(255,59,48,0.2)";
    safetyCtx.fill();
  }
  zonePoints.forEach(([x, y]) => {
    safetyCtx.beginPath();
    safetyCtx.arc(x * safetyCanvas.width, y * safetyCanvas.height, 4, 0, Math.PI * 2);
    safetyCtx.fillStyle = "#ff3b30";
    safetyCtx.fill();
  });
}

safetyFile.addEventListener("change", () => {
  const file = safetyFile.files[0];
  if (!file) return;
  zonePoints = [];
  zoneClosed = false;
  safetyImg = new Image();
  safetyImg.onload = () => {
    const maxW = 860;
    const scale = Math.min(1, maxW / safetyImg.width);
    safetyCanvas.width = safetyImg.width * scale;
    safetyCanvas.height = safetyImg.height * scale;
    safetyCanvas.style.display = "block";
    safetyHint.textContent = "在圖上點擊至少 3 個點畫出危險區域，再按「完成區域」";
    redrawSafetyCanvas();
  };
  safetyImg.src = URL.createObjectURL(file);
});

safetyCanvas.addEventListener("click", (e) => {
  if (zoneClosed || !safetyImg) return;
  const rect = safetyCanvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const y = (e.clientY - rect.top) / rect.height;
  zonePoints.push([x, y]);
  redrawSafetyCanvas();
});

document.getElementById("safety-zone-done-btn").addEventListener("click", () => {
  if (zonePoints.length < 3) { alert("至少要點 3 個點才能構成區域"); return; }
  zoneClosed = true;
  safetyHint.textContent = `區域已完成（${zonePoints.length} 個頂點）`;
  redrawSafetyCanvas();
});

document.getElementById("safety-zone-clear-btn").addEventListener("click", () => {
  zonePoints = [];
  zoneClosed = false;
  safetyHint.textContent = safetyImg ? "在圖上點擊至少 3 個點畫出危險區域，再按「完成區域」" : "尚未選擇圖片";
  if (safetyImg) redrawSafetyCanvas();
});

document.getElementById("safety-btn").addEventListener("click", () => {
  const file = safetyFile.files[0];
  if (!file) { alert("請先選擇照片"); return; }
  const formData = new FormData();
  formData.append("file", file);
  if (zoneClosed && zonePoints.length >= 3) {
    formData.append("zone", JSON.stringify(zonePoints));
  }
  callApi("/api/safety/intrusion", formData, document.getElementById("safety-status"),
    document.getElementById("safety-result"), document.getElementById("safety-btn"));
});

