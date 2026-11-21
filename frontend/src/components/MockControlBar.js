/**
 * Ngăn kéo giả lập (MockControlBar) thu gọn thành 1 nút nhỏ ở góc dưới bên phải khi MOCK_HARDWARE=True.
 * Tự động ẩn 100% khi chạy trên Raspberry Pi 4 (MOCK_HARDWARE=False).
 */
import { apiClient } from "../services/apiClient.js";

let isDrawerOpen = false;

export function mountMockDrawer(rootEl, isMockMode, foodsList = [], onToast) {
  if (!isMockMode) {
    rootEl.innerHTML = "";
    return;
  }

  const options = (foodsList.length ? foodsList : [
    { class_name: "Fish", vietnamese_name: "Cá phi lê" },
    { class_name: "Beef", vietnamese_name: "Thịt bò nạc" },
    { class_name: "Pork", vietnamese_name: "Thịt lợn nạc" },
    { class_name: "Chicken", vietnamese_name: "Thịt gà tươi" },
    { class_name: "Egg", vietnamese_name: "Trứng gà" },
    { class_name: "Tomato", vietnamese_name: "Cà chua chín" },
    { class_name: "Carrot", vietnamese_name: "Cà rốt" },
    { class_name: "Cabbage", vietnamese_name: "Bắp cải trắng" },
  ])
    .map((f) => `<option value="${f.class_name}">${f.vietnamese_name} (${f.class_name})</option>`)
    .join("");

  rootEl.innerHTML = `
    <div class="mock-drawer-wrap">
      <div id="mock-drawer-panel" class="mock-drawer-panel" style="display:${isDrawerOpen ? "block" : "none"};">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <strong style="font-size:15px;">Giả lập Phần Cứng (Dev PC)</strong>
          <button id="mock-close-btn" class="btn btn-sm btn-outline" type="button">Thu gọn</button>
        </div>

        <div style="font-size:14px; font-weight:600; color:var(--text-muted); margin-bottom:6px;">Trọng lượng cân (gram)</div>
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px;">
          <button class="btn btn-sm btn-outline mock-w-btn" data-w="0" type="button">0g</button>
          <button class="btn btn-sm btn-outline mock-w-btn" data-w="45" type="button">45g</button>
          <button class="btn btn-sm btn-outline mock-w-btn" data-w="500" type="button">500g</button>
          <button class="btn btn-sm btn-outline mock-w-btn" data-w="1000" type="button">1kg</button>
          <button class="btn btn-sm btn-outline mock-w-btn" data-w="5000" type="button">5kg</button>
        </div>
        <div style="display:flex; gap:8px; margin-bottom:14px;">
          <input id="mock-custom-w" type="number" class="input" style="flex:1; min-height:38px;" placeholder="Nhập gram..." value="1000" />
          <button id="mock-apply-w" class="btn btn-sm btn-primary" type="button">Đặt cân</button>
        </div>

        <div style="font-size:14px; font-weight:600; color:var(--text-muted); margin-bottom:6px;">Loại thực phẩm &amp; Chất lượng AI</div>
        <select id="mock-food-select" class="select" style="width:100%; min-height:40px; margin-bottom:10px;">
          ${options}
        </select>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
          <button id="mock-ai-fresh" class="btn btn-sm btn-green" type="button">Giả lập TƯƠI</button>
          <button id="mock-ai-rotten" class="btn btn-sm btn-danger" type="button">Giả lập HỎNG</button>
        </div>
      </div>

      <button id="mock-drawer-toggle" class="mock-drawer-toggle" type="button">
        Giả lập phần cứng
      </button>
    </div>
  `;

  const toggleBtn = document.getElementById("mock-drawer-toggle");
  const panel = document.getElementById("mock-drawer-panel");
  const closeBtn = document.getElementById("mock-close-btn");

  const setOpen = (open) => {
    isDrawerOpen = open;
    if (panel) panel.style.display = open ? "block" : "none";
  };

  toggleBtn?.addEventListener("click", () => setOpen(!isDrawerOpen));
  closeBtn?.addEventListener("click", () => setOpen(false));

  rootEl.querySelectorAll(".mock-w-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await apiClient.simulateWeight(Number(btn.dataset.w || 0));
      } catch (e) {
        onToast?.(e.message, "error");
      }
    });
  });

  document.getElementById("mock-apply-w")?.addEventListener("click", async () => {
    const w = Number(document.getElementById("mock-custom-w")?.value || 0);
    try {
      await apiClient.simulateWeight(w);
    } catch (e) {
      onToast?.(e.message, "error");
    }
  });

  document.getElementById("mock-ai-fresh")?.addEventListener("click", async () => {
    const label = document.getElementById("mock-food-select")?.value || "Fish";
    try {
      await apiClient.simulateAI(label, "FRESH");
      await apiClient.inspectNow({ override_label: label, override_quality: "FRESH" });
    } catch (e) {
      onToast?.(e.message, "error");
    }
  });

  document.getElementById("mock-ai-rotten")?.addEventListener("click", async () => {
    const label = document.getElementById("mock-food-select")?.value || "Fish";
    try {
      await apiClient.simulateAI(label, "REJECTED");
      await apiClient.inspectNow({ override_label: `Rotten_${label}`, override_quality: "REJECTED" });
    } catch (e) {
      onToast?.(e.message, "error");
    }
  });
}
