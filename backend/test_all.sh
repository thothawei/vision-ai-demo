#!/usr/bin/env bash
# 自動化測試兩個功能：街景辨識 + 文件擷取（兩種模式）
# 用法：bash backend/test_all.sh
# 遇到 Gemini 免費層配額限制（每分鐘 20 次）會自動間隔重試，不會誤判成失敗。
#
# 注意：腳本執行期間不要同時手動打 /api/scan 或 /api/extract，
# 免費層配額是整個 API key 共用的，手動請求會跟腳本的重試搶額度，
# 導致重試次數用盡卻一直沒等到配額真正清空。

set -uo pipefail

BASE_URL="http://127.0.0.1:8000"
# 測試圖片路徑：換機器或換測試圖片時用環境變數覆蓋，例如
# IMG_DIR=~/Pictures/test-photos bash backend/test_all.sh
IMG_DIR="${IMG_DIR:-/private/tmp/claude-501/-Users-mac-Documents-vision-ai-demo/408b653b-700d-4562-8165-2c1f07cb1fd4/images}"
MAX_RETRIES=10
RETRY_WAIT=20

# call_api <endpoint_path_with_query> <file_path> <mime_type>
call_api() {
  local path="$1" file="$2" mime="$3"
  local attempt=1 http_code body

  while (( attempt <= MAX_RETRIES )); do
    body=$(curl -s -w "\n%{http_code}" -X POST -F "file=@${file};type=${mime}" "${BASE_URL}${path}")
    http_code=$(echo "$body" | tail -1)
    body=$(echo "$body" | sed '$d')

    if [[ "$http_code" == "200" ]]; then
      echo "$body"
      return 0
    fi

    if echo "$body" | grep -qi "quota\|high demand\|UNAVAILABLE"; then
      echo "  [重試 ${attempt}/${MAX_RETRIES}] Gemini 暫時性錯誤（配額或過載），等 ${RETRY_WAIT} 秒..." >&2
      sleep "$RETRY_WAIT"
      ((attempt++))
      continue
    fi

    echo "  [失敗] HTTP ${http_code}: ${body}" >&2
    return 1
  done

  echo "  [放棄] 重試 ${MAX_RETRIES} 次後仍失敗" >&2
  return 1
}

echo "=== 1. 健康檢查 ==="
if ! curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/" | grep -q "200"; then
  echo "伺服器沒有回應，請先啟動：uvicorn main:app --reload"
  exit 1
fi
echo "伺服器正常"

echo ""
echo "=== 2. 街景辨識測試（真實街景照片） ==="
for img in "street_test.jpg" "taiwan_test.jpg"; do
  echo "-- ${img} --"
  call_api "/api/scan" "${IMG_DIR}/${img}" "image/jpeg"
  echo ""
done

echo "=== 3. 文件擷取測試（OCR 模式） ==="
call_api "/api/extract?mode=ocr" "${IMG_DIR}/2.webp" "image/webp"
echo ""

echo "=== 4. 文件擷取測試（端到端模式） ==="
call_api "/api/extract?mode=end_to_end" "${IMG_DIR}/2.webp" "image/webp"
echo ""

echo "=== 測試完成 ==="
