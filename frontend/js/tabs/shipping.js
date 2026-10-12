import { setupPreview, callApi, callBatchApi } from "../common.js";

// ⑯ 出貨標籤 vs 工單比對（M12）
const shippingFile = document.getElementById("shipping-file");
setupPreview(shippingFile, document.getElementById("shipping-preview"));
document.getElementById("shipping-check-btn").addEventListener("click", () => {
  const files = Array.from(shippingFile.files);
  if (files.length === 0) { alert("請先選擇照片"); return; }
  const statusEl = document.getElementById("shipping-status");
  const resultEl = document.getElementById("shipping-result");
  const btn = document.getElementById("shipping-check-btn");

  const params = new URLSearchParams();
  const expectedPartNo = document.getElementById("shipping-expected-part-no").value.trim();
  const expectedLotNo = document.getElementById("shipping-expected-lot-no").value.trim();
  const expectedQuantity = document.getElementById("shipping-expected-quantity").value;
  if (expectedPartNo) params.set("expected_part_no", expectedPartNo);
  if (expectedLotNo) params.set("expected_lot_no", expectedLotNo);
  if (expectedQuantity) params.set("expected_quantity", expectedQuantity);

  if (files.length > 1) { callBatchApi("shipping", files, Object.fromEntries(params), {}, statusEl, resultEl, btn); return; }
  const formData = new FormData();
  formData.append("file", files[0]);
  const url = "/api/shipping/check-label" + (params.toString() ? "?" + params.toString() : "");
  callApi(url, formData, statusEl, resultEl, btn);
});

