import { apiFetch } from "./api.js";

// 目前登入者（GET /api/auth/me），整個頁面只查一次
let mePromise = null;

export function loadMe() {
  if (!mePromise) {
    mePromise = apiFetch("/api/auth/me").then((res) => {
      if (!res.ok) throw new Error("讀取登入身分失敗（HTTP " + res.status + "）");
      return res.json();
    });
  }
  return mePromise;
}

export const ROLE_LABELS = { operator: "操作員", qc: "品管", admin: "管理員" };

export async function logout() {
  await apiFetch("/api/auth/logout", { method: "POST" });
  location.href = "/login.html";
}
