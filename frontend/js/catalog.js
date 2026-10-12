// 辨識動作註冊表（GET /api/modules）：導覽與模組名稱都由這裡來，前端不寫死。
import { apiFetch } from "./api.js";
let catalogPromise = null;

export function loadCatalog() {
  if (!catalogPromise) {
    catalogPromise = apiFetch("/api/modules").then((res) => {
      if (!res.ok) throw new Error("讀取功能清單失敗（HTTP " + res.status + "）");
      return res.json();
    });
  }
  return catalogPromise;
}
