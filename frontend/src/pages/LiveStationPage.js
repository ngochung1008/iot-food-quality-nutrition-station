/**
 * Trang Trạm Vận Hành Chính (Receiver / QC):
 * - Bên trái: Phiếu Yêu Cầu Nguyên Liệu đang thực hiện (Checklist cần cân + nút Xác nhận Tích xanh) + Camera AI.
 * - Bên phải: Đồng hồ trọng lượng real-time + Bảng đánh giá chất lượng & giá trị dinh dưỡng.
 */
import { playRejectAlarm, playSuccessBeep } from "../assets/js/alertSound.js";
import { renderLiveCameraCard, updateLiveCameraCard } from "../components/LiveCameraCard.js";
import { renderNutritionTable, updateNutritionTable } from "../components/NutritionTable.js";
import { renderWeightGauge, updateWeightGauge } from "../components/WeightGauge.js";
import { apiClient } from "../services/apiClient.js";

export class LiveStationPage {
  constructor(toast) {
    this.toast = toast;
    this.foodsList = [];
    this.orders = [];
    this.activeOrderId = "";
    this.lastSnapshot = null;
    this.lastInspectionCode = null;
  }

  async mount(rootEl, initialSnapshot) {
    this.lastSnapshot = initialSnapshot;
    try {
      const [foods, orders] = await Promise.all([apiClient.getFoods(), apiClient.getOrders()]);
      this.foodsList = foods;
      this.orders = orders;
      const preferred =
        orders.find((o) => o.status === "IN_PROGRESS") ||
        orders.find((o) => o.status === "PENDING") ||
        orders[0];
      if (!this.activeOrderId || !orders.some((o) => o.id === this.activeOrderId)) {
        this.activeOrderId = preferred ? preferred.id : "";
      }
    } catch {
      this.foodsList = [];
      this.orders = [];
    }

    rootEl.innerHTML = `
      <div class="station-grid">
        <!-- Cột trái: Checklist Phiếu Yêu Cầu Nguyên Liệu + Camera AI -->
        <div style="display:flex; flex-direction:column; gap:18px;">
          <div class="card">
            <div class="card-head">
              <h3 class="card-title">Phiếu Yêu Cầu Nguyên Liệu Cần Cân</h3>
              <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <select id="station-order-select" class="select" style="min-height:36px; min-width:230px;"></select>
                <button id="btn-reload-orders" class="btn btn-sm btn-outline" type="button">Tải lại</button>
              </div>
            </div>

            <div id="order-banner-slot"></div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Trạng thái</th>
                    <th>Nguyên liệu cần nhập</th>
                    <th>Chuẩn / Tối thiểu (95%)</th>
                    <th>Thực cân</th>
                    <th>Thao tác</th>
                  </tr>
                </thead>
                <tbody id="order-checklist-tbody">
                  <tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Chưa có phiếu yêu cầu nguyên liệu</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div id="camera-card-slot"></div>
        </div>

        <!-- Cột phải: Đồng hồ trọng lượng + Định lượng dinh dưỡng & Chất lượng -->
        <div style="display:flex; flex-direction:column; gap:18px;">
          <div id="weight-gauge-slot"></div>
          <div id="nutrition-table-slot"></div>
        </div>
      </div>
    `;

    renderLiveCameraCard(document.getElementById("camera-card-slot"));
    renderWeightGauge(document.getElementById("weight-gauge-slot"));
    renderNutritionTable(document.getElementById("nutrition-table-slot"), this.foodsList);

    this._renderOrderSelector();
    this._renderOrderChecklist();
    this._bindEvents();
    this.update(initialSnapshot);
  }

  _renderOrderSelector() {
    const sel = document.getElementById("station-order-select");
    if (!sel) return;
    if (!this.orders.length) {
      sel.innerHTML = `<option value="">-- Chưa có phiếu từ Đầu bếp --</option>`;
      return;
    }
    sel.innerHTML = this.orders
      .map(
        (o) =>
          `<option value="${o.id}">${o.order_code} - ${o.title} (${o.progress.completed}/${o.progress.total})</option>`
      )
      .join("");
    sel.value = this.activeOrderId;
  }

  _renderOrderChecklist() {
    const order = this.orders.find((o) => o.id === this.activeOrderId);
    const bannerSlot = document.getElementById("order-banner-slot");
    const tbody = document.getElementById("order-checklist-tbody");
    if (!bannerSlot || !tbody) return;

    if (!order) {
      bannerSlot.innerHTML = `
        <div class="quality-banner warning" style="margin-bottom:10px;">
          <div style="font-weight:700; font-size:13px;">Chưa có Phiếu Yêu Cầu Nguyên Liệu đang hoạt động</div>
          <div style="font-size:12px;">Đầu bếp cần tạo thực đơn ở trang Quản lý thực đơn hoặc bạn có thể cân nhập lẻ bằng nút "Lưu phiếu nhập lẻ".</div>
        </div>`;
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Không có dòng nguyên liệu</td></tr>`;
      return;
    }

    const isDone = order.status === "COMPLETED";
    bannerSlot.innerHTML = `
      <div class="quality-banner ${isDone ? "success" : "warning"}" style="margin-bottom:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <div>
          <div style="font-weight:800; font-size:13.5px;">
            ${isDone ? "HOÀN THÀNH ĐƠN HÀNG" : `ĐANG TIẾP NHẬN: ${order.title}`} (${order.servings} suất | ${order.meal_shift})
          </div>
          <div style="font-size:12px;">
            Tiến độ tích xanh: <strong>${order.progress.completed} / ${order.progress.total}</strong> nguyên liệu (${order.progress.percent}%)
          </div>
        </div>
        <span class="badge ${isDone ? "badge-success" : "badge-warning"}">${order.status}</span>
      </div>
    `;

    const insp = this.lastSnapshot?.current_inspection;
    const detectedClass = insp?.nutrition?.class_name || insp?.detected_class || "";
    const currentWeight = Number(this.lastSnapshot?.weight_gram || 0);
    const qualityStatus = insp?.quality?.status || "FRESH";

    tbody.innerHTML = order.items
      .map((it) => {
        const done = it.status === "COMPLETED";
        const classMatch = detectedClass && detectedClass.toLowerCase() === it.class_name.toLowerCase();
        const weightOk = currentWeight >= Number(it.min_acceptable_gram || 0);
        const qualOk = qualityStatus !== "REJECTED";
        const readyToCheck = !done && classMatch && weightOk && qualOk;

        const rowCls = done ? "row-completed" : classMatch ? "row-matched" : "";
        const statusCell = done
          ? `<span class="check-circle" title="Hoàn thành">OK</span>`
          : classMatch
          ? `<span class="badge badge-warning">Đang khớp AI</span>`
          : `<span class="badge badge-neutral">Chờ cân</span>`;

        const actualCell = done
          ? `<strong class="tabular-nums">${Number(it.actual_gram).toFixed(1)} g</strong>`
          : classMatch
          ? `<span class="tabular-nums" style="font-weight:700; color:${weightOk ? "var(--brand)" : "var(--danger)"};">${currentWeight.toFixed(1)} g</span>`
          : `—`;

        const actionBtn = done
          ? `<span class="badge badge-success">Đã tích xanh</span>`
          : `<button class="btn btn-sm ${readyToCheck ? "btn-primary" : "btn-outline"} btn-check-item" data-item-id="${it.id}" data-cls="${it.class_name}" type="button">
               ${readyToCheck ? "Xác nhận & Tích xanh" : "Đối chiếu & Tích xanh"}
             </button>`;

        return `
          <tr class="${rowCls}">
            <td>${statusCell}</td>
            <td><strong>${it.food_name_vi}</strong><br><span style="font-size:11.5px; color:var(--text-muted);">${it.class_name}</span></td>
            <td class="tabular-nums"><strong>${Number(it.required_gram).toLocaleString("vi-VN")} g</strong><br><span style="font-size:11.5px; color:var(--text-muted);">Tối thiểu: ${Number(it.min_acceptable_gram).toLocaleString("vi-VN")} g</span></td>
            <td>${actualCell}</td>
            <td>${actionBtn}</td>
          </tr>
        `;
      })
      .join("");

    tbody.querySelectorAll(".btn-check-item").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const itemId = btn.dataset.itemId;
        try {
          const res = await apiClient.checkOrderItem(order.id, itemId);
          playSuccessBeep();
          if (res.order) {
            const idx = this.orders.findIndex((o) => o.id === res.order.id);
            if (idx >= 0) this.orders[idx] = res.order;
            this._renderOrderSelector();
            this._renderOrderChecklist();
            if (res.order.status === "COMPLETED") {
              this.toast(`HOÀN THÀNH ĐƠN HÀNG ${res.order.order_code}!`, "success");
            } else {
              this.toast(`Đã tích xanh nguyên liệu (${res.receipt.food_name_vi})`, "success");
            }
          }
        } catch (e) {
          playRejectAlarm();
          this.toast(e.message, "error");
        }
      });
    });
  }

  async reloadOrders() {
    try {
      this.orders = await apiClient.getOrders();
      if (!this.activeOrderId && this.orders.length) {
        const preferred =
          this.orders.find((o) => o.status === "IN_PROGRESS") ||
          this.orders.find((o) => o.status === "PENDING") ||
          this.orders[0];
        this.activeOrderId = preferred.id;
      }
      this._renderOrderSelector();
      this._renderOrderChecklist();
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  _bindEvents() {
    document.getElementById("station-order-select")?.addEventListener("change", (e) => {
      this.activeOrderId = e.target.value;
      this._renderOrderChecklist();
    });

    document.getElementById("btn-reload-orders")?.addEventListener("click", () => this.reloadOrders());

    document.getElementById("btn-tare")?.addEventListener("click", async () => {
      try {
        await apiClient.tare();
        this.toast("Đã trừ bì (Tare) về 0.0g", "success");
      } catch (e) {
        this.toast(`Lỗi Tare: ${e.message}`, "error");
      }
    });

    document.getElementById("btn-inspect-now")?.addEventListener("click", async () => {
      try {
        await apiClient.inspectNow();
        this.toast("Đã hoàn tất kiểm định AI", "success");
      } catch (e) {
        this.toast(`Lỗi nhận diện AI: ${e.message}`, "error");
      }
    });

    document.getElementById("btn-commit-receipt")?.addEventListener("click", async () => {
      try {
        const selectEl = document.getElementById("nt-food-select");
        const overrideClass = selectEl?.value || null;
        const res = await apiClient.commitReceipt({ override_class: overrideClass });
        if (res.ok) {
          playSuccessBeep();
          this.toast(`Đã lưu phiếu nhập lẻ ${res.receipt.batch_code}`, "success");
        }
      } catch (e) {
        this.toast(`Lỗi lưu phiếu: ${e.message}`, "error");
      }
    });

    document.getElementById("nt-food-select")?.addEventListener("change", async (e) => {
      const cls = e.target.value;
      if (!cls) return;
      try {
        await apiClient.overrideFood(cls);
        this.toast(`Đã chuyển loại thực phẩm sang ${cls}`, "info");
      } catch (err) {
        this.toast(err.message, "error");
      }
    });
  }

  update(snapshot) {
    if (!snapshot) return;
    this.lastSnapshot = snapshot;
    updateWeightGauge(snapshot);
    updateLiveCameraCard(snapshot);
    updateNutritionTable(snapshot);
    this._renderOrderChecklist();

    const insp = snapshot.current_inspection;
    if (insp && insp.batch_code !== this.lastInspectionCode) {
      this.lastInspectionCode = insp.batch_code;
      if (insp.quality?.status === "REJECTED") {
        playRejectAlarm();
      } else {
        playSuccessBeep();
      }
    }
  }

  onOrderEvent(order) {
    if (!order) {
      this.reloadOrders();
      return;
    }
    const idx = this.orders.findIndex((o) => o.id === order.id);
    if (idx >= 0) this.orders[idx] = order;
    else {
      this.orders.unshift(order);
      this.activeOrderId = order.id;
    }
    this._renderOrderSelector();
    this._renderOrderChecklist();
  }
}
