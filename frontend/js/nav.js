import { loadCatalog } from "./catalog.js";

// 管理類頁面不是辨識動作，不在註冊表內，先固定列出（後續版本會擴充）
const ADMIN_TABS = [{ tab: "dashboard", label: "品檢紀錄與看板" }];

function tabsByCategory(catalog) {
  const groups = new Map(catalog.categories.map((c) => [c, new Map()]));
  catalog.actions.forEach((a) => {
    const tabs = groups.get(a.category);
    if (!tabs) return;
    if (!tabs.has(a.tab)) tabs.set(a.tab, { tab: a.tab, labels: [], batchable: false });
    const entry = tabs.get(a.tab);
    entry.labels.push(a.label);
    entry.batchable = entry.batchable || a.batchable;
  });
  const result = [];
  groups.forEach((tabs, category) => {
    if (tabs.size) result.push([category, [...tabs.values()].map((t) => ({ tab: t.tab, label: t.labels.join("／") }))]);
  });
  result.push(["管理", ADMIN_TABS]);
  return result;
}

// 註冊表有、但 index.html 沒有專用畫面的動作：產生說明用的預設面板，導覽照樣出現
function ensurePanel(tab, label) {
  if (document.getElementById("panel-" + tab)) return;
  const panel = document.createElement("div");
  panel.className = "panel";
  panel.id = "panel-" + tab;
  panel.innerHTML = `<div class="card"><h2></h2><p class="hint">此功能尚未提供專用畫面，可直接使用 API（批次端點 <code>/api/batch/&lt;action&gt;</code>，說明見 <code>/docs</code>）。</p></div>`;
  panel.querySelector("h2").textContent = label;
  document.getElementById("content").appendChild(panel);
}

export function activateTab(tab) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "panel-" + tab));
  history.replaceState(null, "", "#" + tab);
  document.dispatchEvent(new CustomEvent("tab-activated", { detail: tab }));
}

export async function buildNav() {
  const nav = document.getElementById("side-nav");
  let groups;
  try {
    groups = tabsByCategory(await loadCatalog());
  } catch (err) {
    nav.textContent = "無法載入功能清單：" + err.message;
    return;
  }
  const allTabs = [];
  groups.forEach(([category, tabs]) => {
    const group = document.createElement("div");
    group.className = "nav-group";
    const heading = document.createElement("div");
    heading.className = "nav-heading";
    heading.textContent = category;
    group.appendChild(heading);
    tabs.forEach(({ tab, label }) => {
      ensurePanel(tab, label);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tab-btn";
      btn.dataset.tab = tab;
      btn.textContent = label;
      btn.addEventListener("click", () => activateTab(tab));
      group.appendChild(btn);
      allTabs.push(tab);
    });
    nav.appendChild(group);
  });
  const fromHash = () => location.hash.slice(1);
  activateTab(allTabs.includes(fromHash()) ? fromHash() : allTabs[0]);
  // 瀏覽器上一頁／手動改網址列的 #分頁 也要切換
  window.addEventListener("hashchange", () => {
    if (allTabs.includes(fromHash())) activateTab(fromHash());
  });
}
