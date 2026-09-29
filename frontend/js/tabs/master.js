import { apiFetch } from "../api.js";
import { loadCatalog } from "../catalog.js";
import { loadMe } from "../session.js";

const me = await loadMe();
const isAdmin = me.role === "admin";
if (!isAdmin) document.querySelectorAll("#panel-master .admin-only").forEach((el) => { el.style.display = "none"; });

async function send(url, method, payload) {
  const res = await apiFetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

function report(el, message, isError) {
  el.textContent = message;
  el.className = "status" + (isError ? " error" : "");
}

function cells(values) {
  const tr = document.createElement("tr");
  values.forEach((v) => { const td = document.createElement("td"); td.textContent = v ?? ""; tr.appendChild(td); });
  return tr;
}

// --- 料號 ---
let parts = [];
async function refreshParts() {
  parts = await (await apiFetch("/api/master/parts")).json();
  const body = document.getElementById("master-parts-body");
  body.innerHTML = "";
  parts.forEach((p) => {
    const tr = cells([p.part_no, p.name, p.spec, p.customer, p.is_active ? "是" : "否"]);
    tr.classList.add("clickable");
    tr.addEventListener("click", () => {
      if (!isAdmin) return;
      document.getElementById("part-no").value = p.part_no;
      document.getElementById("part-name").value = p.name;
      document.getElementById("part-spec").value = p.spec;
      document.getElementById("part-customer").value = p.customer;
      document.getElementById("part-active").checked = p.is_active;
    });
    body.appendChild(tr);
  });
  for (const id of ["wo-part", "recipe-part-select"]) {
    const sel = document.getElementById(id);
    const keep = sel.value;
    sel.innerHTML = "";
    parts.forEach((p) => { const o = document.createElement("option"); o.value = p.part_no; o.textContent = `${p.part_no} ${p.name}`; sel.appendChild(o); });
    if (keep) sel.value = keep;
  }
}

document.getElementById("part-save-btn").addEventListener("click", async () => {
  const st = document.getElementById("part-status");
  try {
    await send("/api/master/parts", "POST", {
      part_no: document.getElementById("part-no").value.trim(),
      name: document.getElementById("part-name").value.trim(),
      spec: document.getElementById("part-spec").value.trim(),
      customer: document.getElementById("part-customer").value.trim(),
      is_active: document.getElementById("part-active").checked,
    });
    report(st, "已儲存");
    await refreshParts();
    await refreshRecipes();
  } catch (err) { report(st, "錯誤：" + err.message, true); }
});

// --- 工單 ---
async function refreshWorkOrders() {
  const list = await (await apiFetch("/api/master/work-orders")).json();
  const body = document.getElementById("master-wo-body");
  body.innerHTML = "";
  list.forEach((w) => body.appendChild(cells([w.work_order_no, w.part_no, w.quantity, w.status, w.start_date, w.end_date, w.lot_no])));
}

document.getElementById("wo-save-btn").addEventListener("click", async () => {
  const st = document.getElementById("wo-status-msg");
  try {
    await send("/api/master/work-orders", "POST", {
      work_order_no: document.getElementById("wo-no").value.trim(),
      part_no: document.getElementById("wo-part").value,
      quantity: parseInt(document.getElementById("wo-qty").value || "0", 10),
      status: document.getElementById("wo-status").value,
      start_date: document.getElementById("wo-start").value || null,
      end_date: document.getElementById("wo-end").value || null,
      lot_no: document.getElementById("wo-lot").value.trim() || null,
    });
    report(st, "已儲存");
    await refreshWorkOrders();
  } catch (err) { report(st, "錯誤：" + err.message, true); }
});

// --- 配方版本 ---
const partSelect = document.getElementById("recipe-part-select");
async function refreshRecipes() {
  const body = document.getElementById("recipe-versions-body");
  body.innerHTML = "";
  document.getElementById("recipe-detail").style.display = "none";
  if (!partSelect.value) return;
  const res = await apiFetch("/api/recipes?part_no=" + encodeURIComponent(partSelect.value));
  if (!res.ok) return;
  (await res.json()).forEach((r) => {
    const tr = cells([`v${r.version}`, r.is_active ? "啟用中" : "", r.step_count, r.note, r.created_by, r.created_at, ""]);
    const act = tr.lastChild;
    const view = document.createElement("button");
    view.type = "button"; view.textContent = "檢視";
    view.addEventListener("click", async () => {
      const detail = await (await apiFetch(`/api/recipes/${r.id}`)).json();
      const pre = document.getElementById("recipe-detail");
      pre.textContent = JSON.stringify(detail.steps, null, 2);
      pre.style.display = "block";
    });
    act.appendChild(view);
    if (isAdmin) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.textContent = r.is_active ? "停用" : "啟用";
      toggle.addEventListener("click", async () => {
        const st = document.getElementById("recipe-save-status");
        try {
          await send(`/api/recipes/${r.id}/${r.is_active ? "deactivate" : "activate"}`, "POST");
          report(st, "已更新");
          await refreshRecipes();
        } catch (err) { report(st, "錯誤：" + err.message, true); }
      });
      act.append(" ", toggle);
    }
    body.appendChild(tr);
  });
}
partSelect.addEventListener("change", refreshRecipes);

// --- 新增版本：依註冊表的參數 schema 產生表單 ---
const catalog = await loadCatalog();
const recipeActions = catalog.actions.filter((a) => a.recipe_capable);
const stepsBox = document.getElementById("recipe-builder-steps");

function fieldType(prop) {
  const candidates = prop.anyOf ? prop.anyOf.filter((s) => s.type !== "null") : [prop];
  return (candidates[0] || {}).type || "string";
}

function buildParamFields(container, schema) {
  container.innerHTML = "";
  if (!schema || !schema.properties) return;
  Object.entries(schema.properties).forEach(([name, prop]) => {
    const type = fieldType(prop);
    const label = document.createElement("label");
    label.textContent = name + " ";
    let input;
    if (type === "boolean") { input = document.createElement("input"); input.type = "checkbox"; input.checked = Boolean(prop.default); }
    else if (type === "integer" || type === "number") { input = document.createElement("input"); input.type = "number"; input.step = "any"; if (prop.default != null) input.placeholder = String(prop.default); }
    else if (type === "string") { input = document.createElement("input"); input.type = "text"; }
    else { input = document.createElement("textarea"); input.rows = 1; input.placeholder = "JSON，例如 [0.1, 0.1, 0.5, 0.5]"; }
    input.dataset.param = name;
    input.dataset.type = type;
    label.appendChild(input);
    container.appendChild(label);
  });
}

function collectParams(container) {
  const params = {};
  container.querySelectorAll("[data-param]").forEach((el) => {
    const { param, type } = el.dataset;
    if (type === "boolean") { if (el.checked) params[param] = true; return; }
    const raw = el.value.trim();
    if (raw === "") return;
    if (type === "integer") params[param] = parseInt(raw, 10);
    else if (type === "number") params[param] = parseFloat(raw);
    else if (type === "string") params[param] = raw;
    else params[param] = JSON.parse(raw);
  });
  return params;
}

function addStepRow() {
  const row = document.createElement("div");
  row.className = "row";
  row.style.alignItems = "flex-start";
  const actionSel = document.createElement("select");
  recipeActions.forEach((a) => { const o = document.createElement("option"); o.value = a.action; o.textContent = `${a.label}（${a.action}）`; actionSel.appendChild(o); });
  const slot = Object.assign(document.createElement("input"), { type: "text", value: "main", size: 8, title: "圖片槽" });
  const label = Object.assign(document.createElement("input"), { type: "text", placeholder: "步驟標籤（選填）" });
  const params = document.createElement("span");
  const remove = Object.assign(document.createElement("button"), { type: "button", textContent: "移除" });
  remove.addEventListener("click", () => row.remove());
  const refill = () => buildParamFields(params, recipeActions.find((a) => a.action === actionSel.value).params_schema);
  actionSel.addEventListener("change", refill);
  refill();
  row.append(actionSel, slot, label, params, remove);
  row._collect = () => ({ action: actionSel.value, image_slot: slot.value.trim() || "main", label: label.value.trim(), params: collectParams(params) });
  stepsBox.appendChild(row);
}

document.getElementById("recipe-add-step-btn").addEventListener("click", addStepRow);
document.getElementById("recipe-save-btn").addEventListener("click", async () => {
  const st = document.getElementById("recipe-save-status");
  try {
    const steps = [...stepsBox.children].map((row) => row._collect());
    const recipe = await send("/api/recipes", "POST", {
      part_no: partSelect.value, steps,
      note: document.getElementById("recipe-note").value.trim(),
      activate: document.getElementById("recipe-activate").checked,
    });
    report(st, `已儲存為 v${recipe.version}${recipe.is_active ? "（啟用中）" : ""}`);
    stepsBox.innerHTML = "";
    await refreshRecipes();
  } catch (err) { report(st, "錯誤：" + err.message, true); }
});
if (isAdmin) addStepRow();

async function refreshAll() {
  await refreshParts();
  await Promise.all([refreshWorkOrders(), refreshRecipes()]);
}
document.addEventListener("tab-activated", (e) => { if (e.detail === "master") refreshAll(); });
