// 共用工具：預覽、結果渲染、追溯資訊 header、API 呼叫（單張／批次）、拍照
export function setupPreview(fileInput, previewImg) {
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) { previewImg.style.display = "none"; return; }
    previewImg.src = URL.createObjectURL(file);
    previewImg.style.display = "block";
  });
}

export function renderResult(container, data) {
  container.innerHTML = "";
  const badge = document.createElement("span");
  badge.textContent = `${data.module} · ${data.verdict} · ${data.engine} · ${data.elapsed_ms}ms`;
  badge.className = "verdict-badge verdict-" + data.verdict;
  container.appendChild(badge);

  const table = document.createElement("table");
  table.style.marginTop = "10px";
  const item = data.items[0] || {};
  for (const [key, value] of Object.entries(item)) {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.textContent = key;
    const td = document.createElement("td");
    td.textContent = typeof value === "object" ? JSON.stringify(value, null, 2) : value;
    tr.appendChild(th);
    tr.appendChild(td);
    table.appendChild(tr);
  }
  container.appendChild(table);

  if (data.annotated_image) {
    const img = document.createElement("img");
    img.src = data.annotated_image;
    img.className = "annotated";
    container.appendChild(img);
  }
}

// 追溯資訊（工單/料號/批號/站別/操作員）：存 localStorage，每次呼叫 API 自動帶 header
const TRACE_FIELDS = [
  ["trace-work-order", "X-Work-Order"],
  ["trace-part-no", "X-Part-No"],
  ["trace-lot-no", "X-Lot-No"],
  ["trace-station", "X-Station"],
  ["trace-operator", "X-Operator"],
];

export function loadTraceFromStorage() {
  try {
    TRACE_FIELDS.forEach(([id]) => {
      const saved = localStorage.getItem("trace:" + id);
      if (saved != null) document.getElementById(id).value = saved;
    });
  } catch (e) { /* 私密瀏覽模式等環境可能無法存取，忽略即可 */ }
}

TRACE_FIELDS.forEach(([id]) => {
  document.getElementById(id).addEventListener("input", (e) => {
    try { localStorage.setItem("trace:" + id, e.target.value); } catch (err) { /* 忽略 */ }
  });
});
loadTraceFromStorage();

export function traceHeaders() {
  const headers = {};
  TRACE_FIELDS.forEach(([id, headerName]) => {
    const value = document.getElementById(id).value.trim();
    if (value) headers[headerName] = encodeURIComponent(value);
  });
  return headers;
}

export async function callApi(url, formData, statusEl, resultEl, button) {
  statusEl.textContent = "辨識中…請稍候（本機模型第一次呼叫較慢）";
  statusEl.className = "status";
  resultEl.innerHTML = "";
  button.disabled = true;
  try {
    const res = await fetch(url, { method: "POST", body: formData, headers: traceHeaders() });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "辨識失敗");
    }
    statusEl.textContent = "完成";
    renderResult(resultEl, data);
  } catch (err) {
    statusEl.textContent = "錯誤：" + err.message;
    statusEl.className = "status error";
  } finally {
    button.disabled = false;
  }
}

export function renderBatchResult(container, data) {
  container.innerHTML = "";
  const grid = document.createElement("div");
  grid.style.cssText = "display:flex; flex-wrap:wrap; gap:10px;";
  data.results.forEach((r) => {
    const card = document.createElement("div");
    card.style.cssText = "width:170px; border:1px solid var(--border); border-radius:8px; padding:8px; font-size:12px;";
    if (r.status === "ok") {
      const badge = `<span class="verdict-badge verdict-${r.result.verdict}">${r.result.verdict}</span>`;
      const img = r.result.annotated_image
        ? `<img src="${r.result.annotated_image}" style="width:100%; border-radius:6px; margin-top:6px; display:block;">`
        : "";
      card.innerHTML = `<div style="word-break:break-all;">${r.filename}</div>${badge}${img}`;
    } else {
      card.innerHTML = `<div style="word-break:break-all;">${r.filename}</div>
        <span class="verdict-badge verdict-NG">錯誤</span>
        <div style="color:var(--muted); margin-top:4px;">${r.error}</div>`;
    }
    grid.appendChild(card);
  });
  container.appendChild(grid);
}

// 批次上傳：選超過一張圖時走這個路徑，單張仍走原本的 callApi（結果呈現方式不同，故意分開）。
export async function callBatchApi(action, files, extraParams, extraFormFields, statusEl, resultEl, button) {
  statusEl.textContent = `批次辨識中…（共 ${files.length} 張，請稍候）`;
  statusEl.className = "status";
  resultEl.innerHTML = "";
  button.disabled = true;
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  if (extraFormFields) {
    Object.entries(extraFormFields).forEach(([k, v]) => { if (v != null && v !== "") formData.append(k, v); });
  }
  const params = new URLSearchParams();
  if (extraParams) {
    Object.entries(extraParams).forEach(([k, v]) => { if (v != null && v !== "") params.set(k, v); });
  }
  try {
    const res = await fetch(`/api/batch/${action}?` + params.toString(), {
      method: "POST", body: formData, headers: traceHeaders(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "批次辨識失敗");
    statusEl.textContent = `完成：共 ${data.total} 張，OK ${data.ok}／NG ${data.ng}／INFO ${data.info}／失敗 ${data.failed}`;
    renderBatchResult(resultEl, data);
  } catch (err) {
    statusEl.textContent = "錯誤：" + err.message;
    statusEl.className = "status error";
  } finally {
    button.disabled = false;
  }
}

// 📷 拍照：共用一個 modal，拍下的照片用 DataTransfer 塞回目標分頁既有的 <input type=file>，
// 下游的預覽/上傳邏輯完全不用改。非 localhost 的 http 網址瀏覽器會擋相機權限。
let cameraStream = null;
let cameraTargetInputId = null;

export async function openCamera(targetInputId) {
  cameraTargetInputId = targetInputId;
  const modal = document.getElementById("camera-modal");
  const video = document.getElementById("camera-video");
  const hint = document.getElementById("camera-hint");
  hint.textContent = "";
  modal.style.display = "flex";
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    video.srcObject = cameraStream;
  } catch (err) {
    hint.textContent = "無法開啟相機：" + err.message + "（非 localhost 的 http 網址瀏覽器會擋相機權限）";
  }
}

export function closeCamera() {
  document.getElementById("camera-modal").style.display = "none";
  if (cameraStream) {
    cameraStream.getTracks().forEach((t) => t.stop());
    cameraStream = null;
  }
}

document.getElementById("camera-close-btn").addEventListener("click", closeCamera);

document.getElementById("camera-capture-btn").addEventListener("click", () => {
  const video = document.getElementById("camera-video");
  const canvas = document.getElementById("camera-canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  canvas.toBlob((blob) => {
    if (!blob) return;
    const file = new File([blob], `camera-${Date.now()}.jpg`, { type: "image/jpeg" });
    const input = document.getElementById(cameraTargetInputId);
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    closeCamera();
  }, "image/jpeg", 0.9);
});

document.querySelectorAll(".camera-btn").forEach((btn) => {
  btn.addEventListener("click", () => openCamera(btn.dataset.target));
});

