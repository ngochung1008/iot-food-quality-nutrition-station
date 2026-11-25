/**
 * Điểm khởi chạy FreshKitchen Enterprise SPA:
 * - Xác thực phiên đăng nhập JWT & Phân quyền RBAC cho 3 vai trò (ADMIN, CHEF, RECEIVER).
 * - Kết nối WebSocket real-time từ Raspberry Pi 4.
 * - Tích hợp ngăn kéo Mock thu gọn ở góc dưới bên phải khi MOCK_HARDWARE=True.
 */
import { mountMockDrawer } from "./components/MockControlBar.js";
import { ChefMenuPage } from "./pages/ChefMenuPage.js";
import { DiagnosticsPage } from "./pages/DiagnosticsPage.js";
import { HistoryReportsPage } from "./pages/HistoryReportsPage.js";
import { LiveStationPage } from "./pages/LiveStationPage.js";
import { LoginPage } from "./pages/LoginPage.js";
import { UsersPage } from "./pages/UsersPage.js";
import { apiClient, clearAuthSession, getAuthSession } from "./services/apiClient.js";
import { StationWebSocketClient } from "./services/wsClient.js";

const appShell = document.getElementById("app-shell");
const mockDrawerRoot = document.getElementById("mock-drawer-root");
const toastContainer = document.getElementById("toast-container");

function showToast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 3600);
}

const ROLE_TABS = {
  ADMIN: [
    { key: "station", label: "Trạm Cân & Kiểm Định" },
    { key: "chef", label: "Thực Đơn & Phiếu Nguyên Liệu" },
    { key: "reports", label: "Báo Cáo & Dữ Liệu" },
    { key: "diagnostics", label: "Phần Cứng & Hiệu Chuẩn" },
    { key: "users", label: "Quản Lý Tài Khoản" },
  ],
  CHEF: [
    { key: "chef", label: "Thực Đơn & Phiếu Nguyên Liệu" },
    { key: "station", label: "Giám Sát Trạm Cân" },
    { key: "reports", label: "Lịch Sử & Báo Cáo" },
  ],
  RECEIVER: [
    { key: "station", label: "Trạm Cân & Kiểm Định" },
    { key: "reports", label: "Lịch Sử Nhập Kho" },
  ],
};

const ROLE_LABEL = {
  ADMIN: "Quản trị viên",
  CHEF: "Đầu bếp trưởng",
  RECEIVER: "Nhân viên tiếp nhận",
};

const pages = {
  station: new LiveStationPage(showToast),
  chef: new ChefMenuPage(showToast),
  reports: new HistoryReportsPage(showToast),
  diagnostics: new DiagnosticsPage(showToast),
  users: new UsersPage(showToast),
};

let activePageKey = "station";
let latestSnapshot = null;
let wsClient = null;
let currentUser = null;

function renderLoginScreen() {
  if (wsClient) {
    wsClient.disconnect();
    wsClient = null;
  }
  mockDrawerRoot.innerHTML = "";
  const loginPage = new LoginPage(showToast, async (user) => {
    currentUser = user;
    await enterAuthenticatedShell();
  });
  loginPage.mount(appShell);
}

async function switchPage(key) {
  const allowedTabs = ROLE_TABS[currentUser?.role] || [];
  if (!allowedTabs.some((t) => t.key === key)) {
    key = allowedTabs[0]?.key || "station";
  }
  activePageKey = key;
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === key);
  });
  const rootEl = document.getElementById("app-root");
  if (rootEl && pages[key]) {
    await pages[key].mount(rootEl, latestSnapshot);
  }
}

function updateTopBadges(snap) {
  if (!snap) return;
  const sub = document.getElementById("station-subtitle");
  const modePill = document.getElementById("mode-pill");
  if (sub && snap.station_name) {
    sub.textContent = `${snap.station_name} (${snap.station_id})`;
  }
  if (modePill) {
    modePill.className = snap.mock_hardware ? "badge badge-warning" : "badge badge-success";
    modePill.textContent = snap.mock_hardware ? "MOCK_HARDWARE=True" : "PI 4 HARDWARE";
  }
}

async function enterAuthenticatedShell() {
  const tabs = ROLE_TABS[currentUser.role] || ROLE_TABS.RECEIVER;
  const tabsHtml = tabs
    .map((t) => `<button class="nav-tab" data-page="${t.key}" type="button">${t.label}</button>`)
    .join("");

  appShell.innerHTML = `
    <header class="topbar">
      <div class="brand-wrap">
        <div class="brand-mark">FK</div>
        <div>
          <h1 class="brand-title">FreshKitchen AI</h1>
          <p class="brand-sub" id="station-subtitle">Bếp Ăn Tập Thể | Raspberry Pi 4 Edge</p>
        </div>
      </div>

      <nav class="nav-tabs" aria-label="Điều hướng">${tabsHtml}</nav>

      <div class="user-cluster">
        <span id="ws-status-pill" class="badge badge-warning">
          <span class="dot dot-warn"></span> Đang kết nối WS
        </span>
        <span id="mode-pill" class="badge badge-neutral">MODE: —</span>
        <span class="badge badge-success">${currentUser.full_name} (${ROLE_LABEL[currentUser.role] || currentUser.role})</span>
        <button id="btn-logout" class="btn btn-sm btn-outline" type="button">Đăng xuất</button>
      </div>
    </header>

    <main class="container" id="app-root">
      <div class="card">Đang khởi tạo không gian làm việc...</div>
    </main>
  `;

  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchPage(btn.dataset.page));
  });

  document.getElementById("btn-logout")?.addEventListener("click", () => {
    clearAuthSession();
    currentUser = null;
    showToast("Đã đăng xuất", "info");
    renderLoginScreen();
  });

  let foodsList = [];
  try {
    const [snap, foods] = await Promise.all([apiClient.getState(), apiClient.getFoods()]);
    latestSnapshot = snap;
    foodsList = foods;
    updateTopBadges(latestSnapshot);
  } catch (e) {
    showToast(`Cảnh báo kết nối trạm: ${e.message}`, "error");
  }

  mountMockDrawer(mockDrawerRoot, Boolean(latestSnapshot?.mock_hardware), foodsList, showToast);

  await switchPage(tabs[0].key);

  wsClient = new StationWebSocketClient(
    (msg) => {
      if (!msg?.data) return;
      if (msg.event === "order_created" || msg.event === "order_updated") {
        pages[activePageKey]?.onOrderEvent?.(msg.data.order);
        return;
      }
      if (msg.event === "receipt_committed") {
        latestSnapshot = msg.data.snapshot;
      } else if (msg.event === "telemetry") {
        latestSnapshot = { ...(latestSnapshot || {}), ...msg.data };
      } else {
        latestSnapshot = msg.data;
      }
      updateTopBadges(latestSnapshot);
      pages[activePageKey]?.update?.(latestSnapshot, msg.event === "telemetry");
    },
    (connected) => {
      const wsPill = document.getElementById("ws-status-pill");
      if (!wsPill) return;
      if (connected) {
        wsPill.className = "badge badge-success";
        wsPill.innerHTML = `<span class="dot dot-ok"></span> WebSocket Online`;
      } else {
        wsPill.className = "badge badge-danger";
        wsPill.innerHTML = `<span class="dot dot-err"></span> Mất kết nối WS`;
      }
    }
  );
  wsClient.connect();
}

window.addEventListener("auth:unauthorized", () => {
  if (currentUser) {
    currentUser = null;
    showToast("Phiên đăng nhập hết hạn, vui lòng đăng nhập lại.", "error");
    renderLoginScreen();
  }
});

async function bootstrap() {
  const { token, user } = getAuthSession();
  if (!token || !user) {
    renderLoginScreen();
    return;
  }
  try {
    const res = await apiClient.getMe();
    currentUser = res.user;
    await enterAuthenticatedShell();
  } catch {
    clearAuthSession();
    renderLoginScreen();
  }
}

bootstrap();
