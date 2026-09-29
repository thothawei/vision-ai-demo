// fetch 的薄包裝：session 過期或未登入（401）就導回登入頁；其餘照常交給呼叫端處理。
export async function apiFetch(url, options) {
  const res = await fetch(url, options);
  if (res.status === 401 && !location.pathname.endsWith("/login.html")) {
    location.href = "/login.html";
    throw new Error("請先登入");
  }
  return res;
}
