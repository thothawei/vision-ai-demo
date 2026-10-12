import { apiFetch } from "./api.js";

// 追溯資訊列的「工單」選單：從主檔的進行中工單選，料號與批號自動帶入；
// 選「臨時檢驗」或手動輸入不在主檔的工單號仍可檢驗，但會標記為臨時檢驗。
const select = document.getElementById("trace-work-order-select");
const woInput = document.getElementById("trace-work-order");
const partInput = document.getElementById("trace-part-no");
const lotInput = document.getElementById("trace-lot-no");
const badge = document.getElementById("trace-adhoc-badge");

let workOrders = [];

function setValue(input, value) {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true })); // 觸發 localStorage 儲存
}

function refreshBadge() {
  const typed = woInput.value.trim();
  if (!typed) badge.textContent = "臨時檢驗（無工單）";
  else if (workOrders.some((w) => w.work_order_no === typed)) badge.textContent = "";
  else badge.textContent = "臨時檢驗（此工單不在主檔）";
}

function applySelection() {
  const wo = workOrders.find((w) => w.work_order_no === select.value);
  woInput.readOnly = Boolean(wo);
  if (wo) {
    setValue(woInput, wo.work_order_no);
    setValue(partInput, wo.part_no);
    if (wo.lot_no) setValue(lotInput, wo.lot_no);
  }
  refreshBadge();
}

async function load() {
  try {
    const res = await apiFetch("/api/master/work-orders?open_only=true");
    if (!res.ok) return;
    workOrders = await res.json();
  } catch (e) { return; }
  workOrders.forEach((w) => {
    const opt = document.createElement("option");
    opt.value = w.work_order_no;
    opt.textContent = `${w.work_order_no}（${w.part_no}，${w.quantity} 件）`;
    select.appendChild(opt);
  });
  // 還原上次填的工單：在主檔就選起來，否則維持臨時
  const saved = woInput.value.trim();
  if (saved && workOrders.some((w) => w.work_order_no === saved)) select.value = saved;
  woInput.readOnly = Boolean(select.value);
  refreshBadge();
}

select.addEventListener("change", applySelection);
woInput.addEventListener("input", () => {
  const match = workOrders.find((w) => w.work_order_no === woInput.value.trim());
  if (match && select.value !== match.work_order_no) select.value = match.work_order_no;
  refreshBadge();
});
load();
