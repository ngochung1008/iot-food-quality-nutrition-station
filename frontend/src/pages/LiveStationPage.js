/**
 * Màn hình Trạm Tiếp Nhận & Kiểm Định Chính (POS / B2B Kitchen SaaS):
 * - Cột trái (55%): Camera AI 4:3 + 4 Thẻ Kết Quả Real-time + Đồng hồ cân & Vertical Stepper 4 bước + Dinh dưỡng.
 * - Cột phải (45%): Phiếu Yêu Cầu Nguyên Liệu từ Nhà Bếp (tự động sáng xanh & tích xanh khi cân đạt chuẩn).
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
    this.lastOrderStatus = null;
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
      if (this.activeOrderId) {
        apiClient.setActiveOrder(this.activeOrderId).catch(() => {});
      }
    } catch {
      this.foodsList = [];
      this.orders = [];
    }

    rootEl.innerHTML = `
      <div class="station-pos-grid">
        <!-- Cột trái (55%): Khu vực Cân & Nhận diện trực tiếp -->
        <div class="col-stack">
          <div id="camera-card-slot"></div>
          <div id="weight-gauge-slot"></div>
          <div id="nutrition-table-slot"></div>
        </div>

        <!-- Cột phải (45%): Danh Sách Nguyên Liệu Cần Nhập (Từ Nhà Bếp) -->
        <div class="col-stack">
          <div class="card">
            <div class="card-head">
              <h3 class="card-title">Danh Sách Nguyên Liệu Cần Nhập</h3>
              <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                <select id="station-order-select" class="select" style="min-height:40px; min-width:220px;"></select>
                <button id="btn-reload-orders" class="btn btn-sm btn-outline" type="button">Tải lại</button>
              </div>
            </div>

            <div id="order-header-summary"></div>
            <div id="order-banner-slot"></div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Tích</th>
                    <th>Tên nguyên liệu</th>
                    <th>Chuẩn (g)</th>
                    <th>Đơn giá</th>
                    <th>Thực cân (g)</th>
                  </tr>
                </thead>
                <tbody id="order-checklist-tbody">
                  <tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Chưa có phiếu yêu cầu nguyên liệu</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `;

    renderLiveCameraCard(document.getElementById("camera-card-slot"), this.foodsList);
    renderWeightGauge(document.getElementById("weight-gauge-slot"));
    renderNutritionTable(document.getElementById("nutrition-table-slot"));

    this._renderOrderSelector();
    this._renderOrderChecklist();
    this._bindEvents();
    this.update(initialSnapshot, true);
  }

  _renderOrderSelector() {
    const sel = document.getElementById("station-order-select");
    if (!sel) return;
    if (!this.orders.length) {
      sel.innerHTML = `<option value="">-- Chưa có phiếu từ Nhà bếp --</option>`;
      return;
    }
    sel.innerHTML = this.orders
      .map(
        (o) =>
          `<option value="${o.id}">${o.order_code} — ${o.title} (${o.progress.completed}/${o.progress.total})</option>`
      )
      .join("");
    sel.value = this.activeOrderId;
  }

  _renderOrderChecklist() {
    const order = this.orders.find((o) => o.id === this.activeOrderId);
    const summaryEl = document.getElementById("order-header-summary");
    const bannerSlot = document.getElementById("order-banner-slot");
    const tbody = document.getElementById("order-checklist-tbody");
    if (!summaryEl || !bannerSlot || !tbody) return;

    if (!order) {
      summaryEl.innerHTML = "";
      bannerSlot.innerHTML = `
        <div class="status-banner warning">
          <div style="font-weight:700; font-size:16px;">Chưa chọn Phiếu Yêu Cầu Nguyên Liệu</div>
          <div style="font-size:15px; margin-top:4px;">
            Nhà bếp cần tạo thực đơn ở mục Thực Đơn &amp; Phiếu Nguyên Liệu, hoặc bạn có thể cân và nhấn Xác nhận thủ công để lưu phiếu lẻ.
          </div>
        </div>`;
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Không có nguyên liệu cần đối chiếu</td></tr>`;
      return;
    }

    const kcalPerServing = order.servings > 0 ? Math.round(order.total_kcal / order.servings) : 0;
    const targetKcal = Math.round(order.target_kcal_per_serving || 650);
    const isDone = order.status === "COMPLETED";

    summaryEl.innerHTML = `
      <div style="background:var(--bg-muted); border:1px solid var(--border); border-radius:var(--radius-sm); padding:16px; margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap;">
          <div>
            <div style="font-size:18px; font-weight:700; color:var(--text-primary);">${order.title}</div>
            <div style="font-size:15px; color:var(--text-secondary); margin-top:4px;">
              Ngày: <strong>${order.meal_date}</strong> | Ca: <strong>${order.meal_shift}</strong>
            </div>
          </div>
          <span class="badge ${isDone ? "badge-success" : "badge-info"}">${order.order_code}</span>
        </div>

        <div style="display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin-top:14px;">
          <div style="background:#FFFFFF; padding:10px 12px; border-radius:8px; border:1px solid var(--border);">
            <div style="font-size:14px; color:var(--text-muted); font-weight:600;">Tổng suất ăn</div>
            <div class="tabular-nums" style="font-size:18px; font-weight:700;">${order.servings} suất</div>
          </div>
          <div style="background:#FFFFFF; padding:10px 12px; border-radius:8px; border:1px solid var(--border);">
            <div style="font-size:14px; color:var(--text-muted); font-weight:600;">Mục tiêu Calo/suất</div>
            <div class="tabular-nums" style="font-size:18px; font-weight:700;">${kcalPerServing} / ${targetKcal} kcal</div>
          </div>
          <div style="background:#FFFFFF; padding:10px 12px; border-radius:8px; border:1px solid var(--border);">
            <div style="font-size:14px; color:var(--text-muted); font-weight:600;">Tiến độ nhập</div>
            <div class="tabular-nums" style="font-size:18px; font-weight:700; color:var(--brand);">${order.progress.completed} / ${order.progress.total} món</div>
          </div>
        </div>

        <div class="progress-track">
          <div class="progress-fill" style="width:${order.progress.percent}%;"></div>
        </div>
      </div>
    `;

    if (isDone) {
      bannerSlot.innerHTML = `
        <div class="status-banner success">
          <div style="font-size:18px; font-weight:800;">ĐÃ NHẬP ĐỦ NGUYÊN LIỆU CHO BẾP</div>
          <div style="font-size:15px; margin-top:4px;">
            Toàn bộ ${order.progress.total} nguyên liệu trong phiếu đã được kiểm định đạt chuẩn và lưu vào hệ thống.
          </div>
        </div>`;
    } else {
      bannerSlot.innerHTML = "";
    }

    const insp = this.lastSnapshot?.current_inspection;
    const detectedClass = insp?.food_name_en || insp?.nutrition?.class_name || insp?.detected_class || "";
    const currentWeight = Number(this.lastSnapshot?.weight_gram || 0);

    tbody.innerHTML = order.items
      .map((it) => {
        const done = it.status === "COMPLETED";
        const classMatch = detectedClass && detectedClass.toLowerCase() === it.class_name.toLowerCase();
        const rowCls = done ? "row-completed" : classMatch ? "row-matched" : "";
        const minG = Number(it.min_acceptable_gram || it.required_gram * 0.95);

        const checkCell = `<span class="check-circle ${done ? "done" : ""}" aria-label="${done ? "Hoàn thành" : "Chờ cân"}"></span>`;
        const unitPriceStr = Number(it.unit_price_per_kg || 40000).toLocaleString("vi-VN");
        const actualStr = done
          ? `<strong class="tabular-nums" style="color:var(--brand);">${Number(it.actual_gram).toFixed(1)} g</strong>`
          : classMatch
          ? `<span class="tabular-nums" style="font-weight:700; color:${currentWeight >= minG ? "var(--brand)" : "var(--accent)"};">${currentWeight.toFixed(1)} g</span>`
          : `<span style="color:var(--text-muted);">Chờ cân</span>`;

        return `
          <tr class="${rowCls}" data-item-id="${it.id}">
            <td>${checkCell}</td>
            <td>
              <div style="font-weight:700; color:var(--text-primary);">${it.food_name_vi}</div>
              <div style="font-size:14px; color:var(--text-muted);">${it.class_name} (tối thiểu ${minG.toFixed(0)}g)</div>
            </td>
            <td class="tabular-nums" style="font-weight:700;">${Number(it.required_gram).toLocaleString("vi-VN")} g</td>
            <td class="tabular-nums">${unitPriceStr} đ/kg</td>
            <td>${actualStr}</td>
          </tr>
        `;
      })
      .join("");
  }

  _notifyInspectionFeedback(insp) {
    if (!insp || insp.batch_code === this.lastInspectionCode) return;
    this.lastInspectionCode = insp.batch_code;

    if (insp.warning) {
      playRejectAlarm();
      this.toast(insp.warning, "error");
      return;
    }

    const qStatus = insp.quality_status || insp.quality?.status || "FRESH";
    if (qStatus === "REJECTED") {
      playRejectAlarm();
      this.toast(`Cảnh báo: ${insp.food_name_vi || insp.detected_class} có dấu hiệu hư hỏng, không thể nhập kho.`, "error");
      return;
    }

    const conf = Number(insp.confidence || 0);
    if (conf < 0.5) {
      this.toast(
        `AI chưa nhận diện rõ (${(conf * 100).toFixed(0)}%). Vui lòng kiểm tra cảm quan hoặc chọn lại tên nguyên liệu.`,
        "warning"
      );
    }

    const order = this.orders.find((o) => o.id === this.activeOrderId);
    if (!order || order.status === "COMPLETED") {
      playSuccessBeep();
      return;
    }

    const cls = (insp.food_name_en || insp.detected_class || "").toLowerCase();
    const pendingMatch = order.items.find((it) => it.status === "PENDING" && it.class_name.toLowerCase() === cls);
    const completedMatch = order.items.find((it) => it.status === "COMPLETED" && it.class_name.toLowerCase() === cls);

    if (insp.committed && completedMatch) {
      playSuccessBeep();
      this.toast(`Đã đối chiếu và tích xanh: ${completedMatch.food_name_vi}`, "success");
      return;
    }

    if (!pendingMatch && !completedMatch && cls && cls !== "unknown") {
      this.toast(
        `Thực phẩm "${insp.food_name_vi || insp.detected_class}" không nằm trong danh sách cần nhập của phiếu hiện tại.`,
        "warning"
      );
      return;
    }

    if (pendingMatch) {
      const w = Number(insp.weight_g ?? insp.weight_gram ?? 0);
      const minG = Number(pendingMatch.min_acceptable_gram || pendingMatch.required_gram * 0.95);
      if (w < minG) {
        this.toast(
          `${pendingMatch.food_name_vi} chưa đủ khối lượng yêu cầu (${w.toFixed(1)}g / tối thiểu ${minG.toFixed(0)}g).`,
          "warning"
        );
      } else {
        playSuccessBeep();
      }
    }
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
        apiClient.setActiveOrder(this.activeOrderId).catch(() => {});
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
      apiClient.setActiveOrder(this.activeOrderId).catch(() => {});
      this._renderOrderChecklist();
    });

    document.getElementById("btn-reload-orders")?.addEventListener("click", () => this.reloadOrders());

    document.getElementById("btn-tare")?.addEventListener("click", async () => {
      try {
        await apiClient.tare();
        this.toast("Đã đưa cân về 0.0g (Tare)", "success");
      } catch (e) {
        this.toast(`Lỗi Tare: ${e.message}`, "error");
      }
    });

    document.getElementById("btn-inspect-now")?.addEventListener("click", async () => {
      try {
        const res = await apiClient.inspectNow();
        if (res.snapshot) {
          this.update(res.snapshot);
        }
        await this.reloadOrders();
      } catch (e) {
        this.toast(`Lỗi nhận diện AI: ${e.message}`, "error");
      }
    });

    document.getElementById("btn-manual-confirm")?.addEventListener("click", async () => {
      try {
        const selectEl = document.getElementById("nt-food-select");
        const overrideClass = selectEl?.value || null;
        const order = this.orders.find((o) => o.id === this.activeOrderId);
        const targetClass = (
          overrideClass ||
          this.lastSnapshot?.current_inspection?.food_name_en ||
          ""
        ).toLowerCase();

        const pendingMatch = order?.items.find(
          (it) => it.status === "PENDING" && it.class_name.toLowerCase() === targetClass
        );

        if (order && pendingMatch) {
          const res = await apiClient.checkOrderItem(order.id, pendingMatch.id, overrideClass || null);
          playSuccessBeep();
          if (res.order) this.onOrderEvent(res.order);
          this.toast(`Đã xác nhận & tích xanh: ${pendingMatch.food_name_vi}`, "success");
        } else {
          const res = await apiClient.commitReceipt({ override_class: overrideClass });
          if (res.ok) {
            playSuccessBeep();
            this.toast(`Đã lưu phiếu nhập lẻ: ${res.receipt.food_name_vi}`, "success");
          }
        }
      } catch (e) {
        playRejectAlarm();
        this.toast(e.message, "error");
      }
    });

    document.getElementById("nt-food-select")?.addEventListener("change", async (e) => {
      const cls = e.target.value;
      if (!cls) return;
      try {
        await apiClient.overrideFood(cls);
        this.toast(`Đã chuyển nguyên liệu sang ${cls}`, "info");
      } catch (err) {
        this.toast(err.message, "error");
      }
    });
  }

  update(snapshot, silent = false) {
    if (!snapshot) return;
    this.lastSnapshot = snapshot;
    updateWeightGauge(snapshot);
    updateLiveCameraCard(snapshot);
    updateNutritionTable(snapshot);
    this._renderOrderChecklist();

    if (!silent && snapshot.current_inspection) {
      this._notifyInspectionFeedback(snapshot.current_inspection);
    }
  }

  onOrderEvent(order) {
    if (!order) {
      this.reloadOrders();
      return;
    }
    const idx = this.orders.findIndex((o) => o.id === order.id);
    if (idx >= 0) {
      this.orders[idx] = order;
    } else {
      this.orders.unshift(order);
      this.activeOrderId = order.id;
      apiClient.setActiveOrder(this.activeOrderId).catch(() => {});
    }
    this._renderOrderSelector();
    this._renderOrderChecklist();
    if (order.status === "COMPLETED" && this.lastOrderStatus !== "COMPLETED") {
      this.lastOrderStatus = "COMPLETED";
      this.toast("ĐÃ NHẬP ĐỦ NGUYÊN LIỆU CHO BẾP", "success");
    } else {
      this.lastOrderStatus = order.status;
    }
  }
}
