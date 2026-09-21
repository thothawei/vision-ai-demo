#!/usr/bin/env bash
# 自動化測試兩個功能：街景辨識 + 文件擷取（兩種模式）
# 用法：bash backend/test_all.sh
#
# Gemini gemini-3.6-flash 免費層實測限制：RPM=5（每分鐘 5 次）、RPD=20（每日 20 次）。
# 數字來自 https://aistudio.google.com/rate-limit 儀表板，不是錯誤訊息文字猜的。
# RPM 是短暫限制，等幾十秒會恢復；RPD 用完後等多久都沒用，只能等隔天重置。
# 這支腳本重試幾次後如果還失敗，會直接判斷是 RPD 用完並中止，不會傻傻重試到天荒地老。
#
# 注意：腳本執行期間不要同時手動打 /api/scan 或 /api/extract，
# 免費層配額是整個 API key 共用的，手動請求會跟腳本的重試搶額度。

set -uo pipefail

BASE_URL="http://127.0.0.1:8000"
# 測試圖片路徑：換機器或換測試圖片時用環境變數覆蓋，例如
# IMG_DIR=~/Pictures/test-photos bash backend/test_all.sh
IMG_DIR="${IMG_DIR:-/private/tmp/claude-501/-Users-mac-Documents-vision-ai-demo/408b653b-700d-4562-8165-2c1f07cb1fd4/images}"
MAX_RETRIES=4
RETRY_WAIT=20

# call_api <endpoint_path_with_query> <file_path> <mime_type>
# 回傳值：0=成功, 1=一般失敗, 2=疑似 RPD 每日配額用完（呼叫端應中止整個腳本）
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

  echo "  [疑似每日配額（RPD）用完] 重試 ${MAX_RETRIES} 次、等了 $((MAX_RETRIES * RETRY_WAIT)) 秒仍失敗。" >&2
  echo "  這已經超過 RPM 的恢復時間，很可能是當天 20 次的 RPD 額度用光了，等多久都沒用。" >&2
  echo "  請去 https://aistudio.google.com/rate-limit 確認用量，明天再測或設定計費方案。" >&2
  return 2
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
  status=$?
  echo ""
  if [[ $status -eq 2 ]]; then
    echo "=== 因每日配額用完中止測試，後續項目未執行 ==="
    exit 2
  fi
done

echo "=== 3. 文件擷取測試（OCR 模式） ==="
call_api "/api/extract?mode=ocr" "${IMG_DIR}/2.webp" "image/webp"
status=$?
echo ""
if [[ $status -eq 2 ]]; then
  echo "=== 因每日配額用完中止測試，後續項目未執行 ==="
  exit 2
fi

echo "=== 4. 文件擷取測試（端到端模式） ==="
call_api "/api/extract?mode=end_to_end" "${IMG_DIR}/2.webp" "image/webp"
status=$?
echo ""
if [[ $status -eq 2 ]]; then
  echo "=== 因每日配額用完中止測試 ==="
  exit 2
fi

echo "=== 測試完成 ==="
