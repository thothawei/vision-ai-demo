import { apiFetch } from "../api.js";
import { renderResult, traceHeaders } from "../common.js";

const partInput = document.getElementById("trace-part-no");
const info = document.getElementById("recipe-info");
const slotsBox = document.getElementById("recipe-slots");
const runBtn = document.getElementById("recipe-run-btn");
const statusEl = document.getElementById("recipe-status");
const resultEl = document.getElementById("recipe-result");
let recipe = null;

async function loadRecipe() {
  recipe = null;
  slotsBox.innerHTML = "";
  resultEl.innerHTML = "";
  runBtn.disabled = true;
  const part = partInput.value.trim();
  if (!part) {
    info.textContent = "請先在上方追溯資訊列選一張工單，或填入料號。";
    return;
  }
  const res = await apiFetch("/api/recipes/active?part_no=" + encodeURIComponent(part));
  const data = await res.json();
  if (!res.ok) {
    info.textContent = typeof data.detail === "string" ? data.detail : "讀取配方失敗";
    return;
  }
  recipe = data;
  info.textContent = `料號 ${data.part_no}：配方 v${data.version}（${data.steps.length} 個步驟）` + (data.note ? `，${data.note}` : "");
  const list = document.createElement("ol");
  data.steps.forEach((s) => {
    const li = document.createElement("li");
    li.textContent = `${s.label || s.action}（${s.action}，圖片槽 ${s.image_slot}）`;
    list.appendChild(li);
  });
  slotsBox.appendChild(list);
  data.slots.forEach((slot) => {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<label>圖片「<b></b>」 <input type="file" accept="image/*" data-slot=""></label>`;
    row.querySelector("b").textContent = slot;
    row.querySelector("input").dataset.slot = slot;
    slotsBox.appendChild(row);
  });
  runBtn.disabled = false;
}

document.getElementById("recipe-load-btn").addEventListener("click", loadRecipe);
document.addEventListener("tab-activated", (e) => { if (e.detail === "recipe") loadRecipe(); });

function stepBadge(step) {
  const span = document.createElement("span");
  span.className = "verdict-badge verdict-" + (step.status === "error" ? "INFO" : step.verdict);
  span.textContent = step.status === "error" ? "無法判定" : step.verdict;
  return span;
}

runBtn.addEventListener("click", async () => {
  const formData = new FormData();
  for (const input of slotsBox.querySelectorAll("input[type=file]")) {
    if (!input.files[0]) { alert(`請選擇圖片槽「${input.dataset.slot}」的照片`); return; }
    formData.append(input.dataset.slot, input.files[0]);
  }
  statusEl.className = "status";
  statusEl.textContent = "檢驗中…請稍候（各步驟依序執行，含 AI 的步驟較慢）";
  resultEl.innerHTML = "";
  runBtn.disabled = true;
  try {
    const res = await apiFetch("/api/inspect/recipe", { method: "POST", body: formData, headers: traceHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    statusEl.textContent = `完成（run #${data.run_id}，配方 v${data.version}）`;

    const head = document.createElement("div");
    head.innerHTML = `<span class="verdict-badge verdict-${data.verdict}">合併判定 ${data.verdict}</span>`;
    resultEl.appendChild(head);
    if (data.reasons.length) {
      const ul = document.createElement("ul");
      data.reasons.forEach((r) => { const li = document.createElement("li"); li.textContent = r; ul.appendChild(li); });
      resultEl.appendChild(ul);
    }
    data.steps.forEach((step) => {
      const box = document.createElement("div");
      box.className = "card";
      const title = document.createElement("h3");
      title.textContent = `步驟 ${step.position}：${step.label || step.action} `;
      title.appendChild(stepBadge(step));
      box.appendChild(title);
      if (step.status === "error") {
        const p = document.createElement("div");
        p.className = "status error";
        p.textContent = step.error;
        box.appendChild(p);
      } else {
        const holder = document.createElement("div");
        renderResult(holder, step.result);
        box.appendChild(holder);
      }
      resultEl.appendChild(box);
    });
  } catch (err) {
    statusEl.textContent = "錯誤：" + err.message;
    statusEl.className = "status error";
  } finally {
    runBtn.disabled = false;
  }
});
