import { loadCatalog } from "./catalog.js";
import { loadMe } from "./session.js";

// 管理類頁面不是辨識動作，不在註冊表內；依角色顯示（伺服器端另有權限檢查，這裡只是不顯示按鈕）
function adminTabs(role) {
  const tabs = [{ tab: "dashboard", label: role === "operator" ? "我的檢驗紀錄" : "品檢紀錄與看板" }];
  if (role !== "operator") tabs.push({ tab: "master", label: "主檔與配方" }, { tab: "spc", label: "SPC 管制圖" });
  if (role === "admin") tabs.push({ tab: "users", label: "使用者" }, { tab: "audit", label: "稽核紀錄" });
  return tabs;
}

function tabsByCategory(catalog, role) {
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
  // 依配方檢驗不是單一辨識動作，獨立成一組並放在最前面（所有角色都能用）
  result.unshift(["配方檢驗", [{ tab: "recipe", label: "依配方檢驗" }]]);
  result.push(["管理", adminTabs(role)]);
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
    const [catalog, me] = await Promise.all([loadCatalog(), loadMe()]);
    groups = tabsByCategory(catalog, me.role);
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
