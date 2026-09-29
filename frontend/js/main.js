// 進入點：先載入各功能分頁的事件綁定，再依 /api/modules 建立左側導覽。
import "./tabs/general.js";
import "./tabs/docs.js";
import "./tabs/anomaly.js";
import "./tabs/codes.js";
import "./tabs/measure.js";
import "./tabs/safety.js";
import "./tabs/ppe.js";
import "./tabs/defect.js";
import "./tabs/nameplate.js";
import "./tabs/packaging.js";
import "./tabs/pneumonia.js";
import "./tabs/assembly.js";
import "./tabs/colordiff.js";
import "./tabs/shipping.js";
import "./tabs/dashboard.js";
import "./tabs/users.js";
import "./tabs/audit.js";
import "./userbar.js";
import { buildNav } from "./nav.js";

buildNav();
