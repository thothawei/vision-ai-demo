import { apiFetch } from "../api.js";
import { loadMe } from "../session.js";

const me = await loadMe();
const body = document.getElementById("users-body");
const statusEl = document.getElementById("users-status");

async function call(url, method, payload) {
  const res = await apiFetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

async function refresh() {
  if (me.role !== "admin") return;
  const list = await (await apiFetch("/api/users")).json();
  body.innerHTML = "";
  list.forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td></td><td></td><td><select>
        <option value="operator">operator</option><option value="qc">qc</option><option value="admin">admin</option>
      </select></td><td></td><td></td>`;
    tr.children[0].textContent = u.username;
    tr.children[1].textContent = u.display_name;
    tr.children[3].textContent = u.is_active ? "啟用" : "已停用";
    const roleSel = tr.querySelector("select");
    roleSel.value = u.role;
    const act = tr.children[4];
    const run = async (fn) => {
      statusEl.className = "status";
      try { await fn(); statusEl.textContent = "已更新"; await refresh(); }
      catch (err) { statusEl.textContent = "錯誤：" + err.message; statusEl.className = "status error"; await refresh(); }
    };
    roleSel.addEventListener("change", () => run(() => call(`/api/users/${u.id}`, "PATCH", { role: roleSel.value })));
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.textContent = u.is_active ? "停用" : "啟用";
    toggle.addEventListener("click", () => run(() => call(`/api/users/${u.id}`, "PATCH", { is_active: !u.is_active })));
    const reset = document.createElement("button");
    reset.type = "button";
    reset.textContent = "重設密碼";
    reset.addEventListener("click", () => {
      const pw = prompt(`為「${u.username}」設定新密碼（至少 10 個字元）`);
      if (pw) run(() => call(`/api/users/${u.id}/password`, "POST", { new_password: pw }));
    });
    act.append(toggle, " ", reset);
    body.appendChild(tr);
  });
}

document.getElementById("new-user-btn").addEventListener("click", async () => {
  const st = document.getElementById("new-user-status");
  st.className = "status";
  try {
    await call("/api/users", "POST", {
      username: document.getElementById("new-user-username").value.trim(),
      display_name: document.getElementById("new-user-display").value.trim(),
      password: document.getElementById("new-user-password").value,
      role: document.getElementById("new-user-role").value,
    });
    st.textContent = "已建立";
    ["new-user-username", "new-user-display", "new-user-password"].forEach((id) => { document.getElementById(id).value = ""; });
    await refresh();
  } catch (err) {
    st.textContent = "錯誤：" + err.message;
    st.className = "status error";
  }
});

document.addEventListener("tab-activated", (e) => { if (e.detail === "users") refresh(); });
