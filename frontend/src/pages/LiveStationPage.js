/**
 * Màn hình Trạm Tiếp Nhận & Kiểm Định Chính (POS / B2B Kitchen SaaS):
 * - Cột trái (55%): Camera AI 4:3 + 4 Thẻ Kết Quả Real-time + Đồng hồ cân & Vertical Stepper 4 bước + Dinh dưỡng.
 * - Cột phải (45%): Phiếu Yêu Cầu Nguyên Liệu từ Nhà Bếp (tự động sáng xanh & tích xanh khi cân đạt chuẩn).
 */
import { playRejectAlarm, playSuccessBeep } from "../assets/js/alertSound.js";
import { renderLiveCameraCard, updateLiveCameraCard } from "../components/LiveCameraCard.js";
import { renderNutritionTable, updateNutritionTable } from "../components/NutritionTable.js";
import { renderWeightGauge, updateWeightGauge } from "../components/WeightGauge.js";
import { apiClient, getAuthSession } from "../services/apiClient.js";

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
            <div class="card-head" style="flex-direction:column; align-items:stretch; gap:12px;">
              <h3 class="card-title">Danh Sách Nguyên Liệu Cần Nhập</h3>
              <div class="order-picker-bar">
                <select id="station-order-select" class="select order-picker-select"></select>
                <button id="btn-reload-orders" class="btn btn-sm btn-outline" style="flex-shrink:0;" type="button">Tải lại</button>
              </div>
              <div class="order-actions-row">
                <button id="btn-header-reset-order" class="btn btn-sm btn-outline" type="button">Reset phiếu</button>
                <button id="btn-toggle-add-item" class="btn btn-sm btn-green" type="button">+ Thêm món vào phiếu</button>
              </div>
            </div>

            <div id="manual-add-item-panel" class="manual-add-panel" style="display:none;">
              <div style="font-size:15px; font-weight:700; color:var(--text-primary);">
                Bổ sung nhanh nguyên liệu vào phiếu (64 lớp chuẩn)
              </div>
              <div class="manual-add-grid">
                <select id="add-item-food-select" class="select" style="width:100%; min-width:0;"></select>
                <input id="add-item-grams" class="input" type="number" min="1" step="10" value="500" placeholder="Gram (g)" style="width:100%; min-width:0;" />
              </div>
              <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;">
                <button id="btn-submit-add-item" class="btn btn-sm btn-green" type="button">Lưu thêm vào phiếu</button>
                <button id="btn-cancel-add-item" class="btn btn-sm btn-outline" type="button">Đóng</button>
              </div>
            </div>

            <div id="order-header-summary"></div>
            <div id="extra-item-banner-slot"></div>
            <div id="order-banner-slot"></div>

            <div class="table-wrap">
              <table class="checklist-table">
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

    const addFoodSel = document.getElementById("add-item-food-select");
    if (addFoodSel) {
      addFoodSel.innerHTML = this.foodsList
        .map((f) => `<option value="${f.class_name}">${f.vietnamese_name} (${f.class_name})</option>`)
        .join("");
    }

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
    const extraSlot = document.getElementById("extra-item-banner-slot");
    const bannerSlot = document.getElementById("order-banner-slot");
    const tbody = document.getElementById("order-checklist-tbody");
    if (!summaryEl || !bannerSlot || !tbody) return;

    if (!order) {
      summaryEl.innerHTML = "";
      if (extraSlot) extraSlot.innerHTML = "";
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
      const actualSum = order.actual_summary || {};
      const sumGram =
        actualSum.total_gram ??
        order.items.reduce((acc, it) => acc + (it.status === "COMPLETED" ? Number(it.actual_gram || 0) : 0), 0);
      const sumCost =
        actualSum.total_cost_vnd ??
        order.items.reduce(
          (acc, it) =>
            acc +
            (it.status === "COMPLETED"
              ? Math.round((Number(it.actual_gram || 0) / 1000) * Number(it.unit_price_per_kg || 40000))
              : 0),
          0
        );
      const sumKcal = actualSum.total_kcal || order.total_kcal || 0;
      const nextOrder = this.orders.find(
        (o) => o.id !== order.id && o.status !== "COMPLETED"
      );

      bannerSlot.innerHTML = `
        <div class="completion-banner">
          <div style="font-size:19px; font-weight:800; color:#14532D;">
            ĐÃ NHẬP ĐỦ 100% NGUYÊN LIỆU CHO BẾP
          </div>
          <div style="font-size:15px; margin-top:4px; color:#166534;">
            Toàn bộ ${order.progress.total}/${order.progress.total} nguyên liệu trong phiếu đã được kiểm định đạt chuẩn và tích xanh hoàn tất.
          </div>

          <div class="completion-metrics">
            <div class="completion-metric-box">
              <div style="font-size:14px; color:var(--text-muted); font-weight:600;">Tổng khối lượng thực nhập</div>
              <div class="tabular-nums" style="font-size:17px; font-weight:800; color:#0F172A;">
                ${Number(sumGram).toLocaleString("vi-VN")} g
              </div>
            </div>
            <div class="completion-metric-box">
              <div style="font-size:14px; color:var(--text-muted); font-weight:600;">Tổng thành tiền</div>
              <div class="tabular-nums" style="font-size:17px; font-weight:800; color:var(--brand);">
                ${Number(sumCost).toLocaleString("vi-VN")} đ
              </div>
            </div>
            <div class="completion-metric-box">
              <div style="font-size:14px; color:var(--text-muted); font-weight:600;">Tổng Calo đã tiếp nhận</div>
              <div class="tabular-nums" style="font-size:17px; font-weight:800; color:#0F172A;">
                ${Number(sumKcal).toLocaleString("vi-VN")} kcal
              </div>
            </div>
          </div>

          <div class="completion-actions">
            <button id="btn-next-order" class="btn btn-sm btn-green" type="button" ${nextOrder ? "" : "disabled"}>
              ${nextOrder ? "Chuyển sang phiếu tiếp theo" : "Không còn phiếu chờ"}
            </button>
            <button id="btn-demo-reset-order" class="btn btn-sm btn-outline" type="button">
              Reset phiếu này để demo lại
            </button>
          </div>
        </div>`;

      document.getElementById("btn-next-order")?.addEventListener("click", () => {
        if (!nextOrder) return;
        this.activeOrderId = nextOrder.id;
        this.lastOrderStatus = nextOrder.status;
        apiClient.setActiveOrder(this.activeOrderId).catch(() => {});
        this._renderOrderSelector();
        this._renderOrderChecklist();
        this.toast(`Đã chuyển sang phiếu: ${nextOrder.title}`, "info");
      });

      document.getElementById("btn-demo-reset-order")?.addEventListener("click", async () => {
        if (!window.confirm("Bạn có chắc muốn reset toàn bộ tiến độ cân của phiếu này về 0%?")) return;
        try {
          const res = await apiClient.resetOrder(order.id);
          this.lastInspectionCode = null;
          this.lastOrderStatus = "PENDING";
          if (res?.order) this.onOrderEvent(res.order);
          if (res?.snapshot) this.update(res.snapshot, true);
          this.toast("Đã reset phiếu về 0% để demo lại.", "success");
        } catch (err) {
          this.toast(err.message, "error");
        }
      });
    } else {
      bannerSlot.innerHTML = "";
    }

    const rawInsp = this.lastSnapshot?.current_inspection;
    const currentWeight = Number(this.lastSnapshot?.weight_gram || 0);
    const insp = this.lastSnapshot?.state === "IDLE" && currentWeight < 8.0 ? null : rawInsp;
    const detectedClass = insp?.food_name_en || insp?.nutrition?.class_name || insp?.detected_class || "";
    const confPct = Number(insp?.confidence_percent ?? (insp?.confidence || 0) * 100);
    const isInOrder =
      Boolean(detectedClass) &&
      order.items.some((it) => it.class_name.toLowerCase() === detectedClass.toLowerCase());
    const showExtraAlert =
      Boolean(extraSlot) &&
      Boolean(insp) &&
      !insp.committed &&
      !insp.warning &&
      confPct >= 35.0 &&
      Boolean(detectedClass) &&
      detectedClass.toLowerCase() !== "unknown" &&
      !isInOrder;

    if (extraSlot) {
      if (showExtraAlert) {
        const foodVi = insp.food_name_vi || detectedClass;
        const wNum = Number(insp.weight_g ?? insp.weight_gram ?? currentWeight).toFixed(1);
        const priceNum = Number(insp.total_price_vnd || 0).toLocaleString("vi-VN");
        const isRejected = (insp.quality_status || insp.quality?.status) === "REJECTED";

        extraSlot.innerHTML = `
          <div class="extra-item-banner">
            <div style="font-size:16px; font-weight:700; color:#9A3412;">
              Phát hiện <strong>${foodVi}</strong> (<strong class="tabular-nums">${wNum}g</strong> — <strong class="tabular-nums">${priceNum}đ</strong>) chưa có trong phiếu yêu cầu của đầu bếp.
            </div>
            ${
              isRejected
                ? `<div style="font-size:14px; color:var(--danger); font-weight:600; margin-top:6px;">Lưu ý: Sản phẩm bị đánh giá hư hỏng (REJECTED), không thể tích xanh nhập kho.</div>`
                : ""
            }
            <div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:12px;">
              <button id="btn-add-extra-item" class="btn btn-sm btn-green" type="button" ${isRejected ? "disabled" : ""}>
                + Bổ sung vào phiếu &amp; Tích xanh
              </button>
              <button id="btn-commit-extra-loose" class="btn btn-sm ${isRejected ? "btn-danger" : "btn-outline"}" type="button">
                ${isRejected ? "Ghi nhận từ chối (Không nhập kho)" : "Lưu nhập lẻ ngoài phiếu"}
              </button>
            </div>
          </div>`;

        document.getElementById("btn-add-extra-item")?.addEventListener("click", async () => {
          const { user } = getAuthSession();
          try {
            const res = await apiClient.addExtraOrderItem(order.id, {
              class_name: detectedClass,
              mark_completed: true,
              note: "Bổ sung phát sinh tại trạm",
            });
            playSuccessBeep();
            if (this.lastSnapshot?.current_inspection) {
              this.lastSnapshot.current_inspection.committed = true;
            }
            if (res?.order) this.onOrderEvent(res.order);
            this.update(this.lastSnapshot, true);
            this.toast(`Đã bổ sung & tích xanh: ${foodVi}${user?.full_name ? ` (${user.full_name})` : ""}`, "success");
          } catch (err) {
            playRejectAlarm();
            this.toast(err.message, "error");
          }
        });

        document.getElementById("btn-commit-extra-loose")?.addEventListener("click", async () => {
          const { user } = getAuthSession();
          const actor = user?.full_name || "Nhân viên tiếp nhận";
          try {
            if (isRejected) {
              const res = await apiClient.rejectInspection({
                reason: "Hàng hư hỏng / không đạt cảm quan",
                confirmed_by: actor,
              });
              if (res?.ok) {
                playRejectAlarm();
                if (res.snapshot) this.update(res.snapshot, true);
                this.toast(`Đã ghi nhận từ chối (Không nhập kho): ${foodVi}`, "warning");
              }
              return;
            }
            const res = await apiClient.commitReceipt({
              override_class: detectedClass,
              note: "Nhập lẻ ngoài phiếu tại trạm",
              confirmed_by: actor,
            });
            if (res?.ok) {
              playSuccessBeep();
              if (this.lastSnapshot?.current_inspection) {
                this.lastSnapshot.current_inspection.committed = true;
              }
              this.update(this.lastSnapshot, true);
              this.toast(`Đã lưu nhập lẻ ngoài phiếu: ${foodVi}`, "success");
            }
          } catch (err) {
            playRejectAlarm();
            this.toast(err.message, "error");
          }
        });
      } else {
        extraSlot.innerHTML = "";
      }
    }

    tbody.innerHTML = order.items
      .map((it) => {
        const done = it.status === "COMPLETED";
        const partial = it.status === "PARTIAL";
        const classMatch = detectedClass && detectedClass.toLowerCase() === it.class_name.toLowerCase();
        const rowCls = done ? "row-completed" : partial ? "row-partial" : classMatch ? "row-matched" : "";
        const reqG = Number(it.required_gram || 0);
        const minG = Number(it.min_acceptable_gram || reqG * 0.95);
        const savedActual = Number(it.actual_gram || 0);
        const previewActual =
          done
            ? savedActual
            : partial
            ? savedActual + (classMatch && !insp?.committed ? currentWeight : 0)
            : classMatch
            ? currentWeight
            : 0;
        const pct = reqG > 0 ? Math.min(100, Math.round((savedActual / reqG) * 100)) : 0;
        const remainG = Math.max(0, reqG - savedActual);

        const checkCell = `<span class="check-circle ${done ? "done" : partial ? "partial" : ""}" aria-label="${
          done ? "Hoàn thành" : partial ? "Đang nhận dở" : "Chờ cân"
        }"></span>`;
        const unitPriceStr = Number(it.unit_price_per_kg || 40000).toLocaleString("vi-VN");
        const actualStr = done
          ? `<strong class="tabular-nums" style="color:var(--brand);">${savedActual.toFixed(1)} g</strong>
             <div class="item-progress-mini"><div class="item-progress-fill is-done" style="width:100%;"></div></div>
             <div style="font-size:12px; color:var(--brand); font-weight:700; margin-top:2px;">Đủ định lượng</div>`
          : partial
          ? `<strong class="tabular-nums" style="color:var(--info);">${savedActual.toFixed(1)} / ${reqG.toFixed(0)} g</strong>
             <div class="item-progress-mini"><div class="item-progress-fill" style="width:${pct}%;"></div></div>
             <div style="font-size:12px; color:var(--accent); font-weight:600; margin-top:2px;">Còn thiếu ${remainG.toFixed(1)}g${
               classMatch && !insp?.committed && currentWeight > 0 ? ` (+${currentWeight.toFixed(1)}g)` : ""
             }</div>`
          : classMatch
          ? `<span class="tabular-nums" style="font-weight:700; color:${previewActual >= minG ? "var(--brand)" : "var(--accent)"};">${currentWeight.toFixed(1)} g</span>
             <div class="item-progress-mini"><div class="item-progress-fill" style="width:${
               reqG > 0 ? Math.min(100, Math.round((currentWeight / reqG) * 100)) : 0
             }%;"></div></div>`
          : `<span style="color:var(--text-muted);">Chờ cân</span>
             <div class="item-progress-mini"><div class="item-progress-fill" style="width:0%;"></div></div>`;

        return `
          <tr class="${rowCls}" data-item-id="${it.id}">
            <td>${checkCell}</td>
            <td>
              <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                <span style="font-weight:700; color:var(--text-primary);">${it.food_name_vi}</span>
                ${partial ? `<span class="badge badge-info" style="padding:2px 8px; font-size:12px;">Đang cộng dồn</span>` : ""}
              </div>
              <div style="font-size:13px; color:var(--text-muted);">${it.class_name} (tối thiểu ${minG.toFixed(0)}g)</div>
            </td>
            <td class="tabular-nums" style="font-weight:700;">${reqG.toLocaleString("vi-VN")} g</td>
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
    const partialMatch = order.items.find((it) => it.status === "PARTIAL" && it.class_name.toLowerCase() === cls);
    const pendingMatch = order.items.find((it) => it.status === "PENDING" && it.class_name.toLowerCase() === cls);
    const completedMatch = order.items.find((it) => it.status === "COMPLETED" && it.class_name.toLowerCase() === cls);

    if (insp.committed && completedMatch) {
      playSuccessBeep();
      this.toast(`Đã đối chiếu đủ và tích xanh: ${completedMatch.food_name_vi}`, "success");
      return;
    }

    if (insp.committed && partialMatch) {
      playSuccessBeep();
      const remain = Math.max(0, Number(partialMatch.required_gram) - Number(partialMatch.actual_gram || 0));
      this.toast(
        `Đã cộng dồn ${partialMatch.food_name_vi}: ${Number(partialMatch.actual_gram).toFixed(1)} / ${Number(partialMatch.required_gram).toFixed(0)}g (còn thiếu ${remain.toFixed(1)}g).`,
        "info"
      );
      return;
    }

    if (!pendingMatch && !partialMatch && !completedMatch && cls && cls !== "unknown") {
      this.toast(
        `Thực phẩm "${insp.food_name_vi || insp.detected_class}" không nằm trong danh sách cần nhập của phiếu hiện tại.`,
        "warning"
      );
      return;
    }

    const activeMatch = partialMatch || pendingMatch;
    if (activeMatch) {
      const w = Number(insp.weight_g ?? insp.weight_gram ?? 0);
      const minG = Number(activeMatch.min_acceptable_gram || activeMatch.required_gram * 0.95);
      if (w < minG) {
        playSuccessBeep();
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

    document.getElementById("btn-header-reset-order")?.addEventListener("click", async () => {
      if (!this.activeOrderId) {
        this.toast("Chưa có phiếu đang chọn để reset.", "warning");
        return;
      }
      if (!window.confirm("Bạn có chắc muốn reset toàn bộ tiến độ cân của phiếu này về 0%?")) return;
      try {
        const res = await apiClient.resetOrder(this.activeOrderId);
        this.lastInspectionCode = null;
        this.lastOrderStatus = "PENDING";
        if (res?.order) this.onOrderEvent(res.order);
        if (res?.snapshot) this.update(res.snapshot, true);
        this.toast("Đã làm trống toàn bộ dấu tích xanh của phiếu!", "success");
      } catch (e) {
        this.toast(e.message, "error");
      }
    });

    const addPanel = document.getElementById("manual-add-item-panel");
    document.getElementById("btn-toggle-add-item")?.addEventListener("click", () => {
      if (!addPanel) return;
      addPanel.style.display = addPanel.style.display === "none" ? "block" : "none";
    });
    document.getElementById("btn-cancel-add-item")?.addEventListener("click", () => {
      if (addPanel) addPanel.style.display = "none";
    });
    document.getElementById("btn-submit-add-item")?.addEventListener("click", async () => {
      if (!this.activeOrderId) {
        this.toast("Vui lòng chọn một phiếu nguyên liệu trước.", "warning");
        return;
      }
      const cls = document.getElementById("add-item-food-select")?.value;
      const grams = Number(document.getElementById("add-item-grams")?.value || 0);
      if (!cls || grams <= 0) {
        this.toast("Vui lòng chọn nguyên liệu và nhập khối lượng > 0g.", "warning");
        return;
      }
      try {
        const res = await apiClient.addExtraOrderItem(this.activeOrderId, {
          class_name: cls,
          required_gram: grams,
          mark_completed: false,
        });
        if (res?.order) this.onOrderEvent(res.order);
        if (addPanel) addPanel.style.display = "none";
        this.toast(`Đã thêm ${cls} (${grams}g) vào phiếu yêu cầu.`, "success");
      } catch (e) {
        this.toast(e.message, "error");
      }
    });

    document.getElementById("btn-tare")?.addEventListener("click", async () => {
      const currentW = Number(this.lastSnapshot?.weight_gram || 0);
      if (currentW > 20.0) {
        const ok = window.confirm(
          `Đĩa cân đang có tải ${currentW.toFixed(1)}g (dùng để trừ bì rổ/khay đựng). Bạn có chắc chắn muốn đặt mức này về 0.0g?`
        );
        if (!ok) return;
      }
      try {
        const res = await apiClient.tare();
        this.lastInspectionCode = null;
        if (res?.snapshot) {
          this.update(res.snapshot, true);
        }
        this.toast("Đã đưa cân về 0.0g (Tare)", "success");
      } catch (e) {
        this.toast(`Lỗi Tare: ${e.message}`, "error");
      }
    });

    const rejectPanel = document.getElementById("wg-reject-panel");
    document.getElementById("btn-reject-goods")?.addEventListener("click", () => {
      if (rejectPanel) {
        rejectPanel.style.display = rejectPanel.style.display === "none" ? "block" : "none";
      }
    });
    document.getElementById("btn-cancel-reject")?.addEventListener("click", () => {
      if (rejectPanel) rejectPanel.style.display = "none";
    });
    document.getElementById("btn-confirm-reject")?.addEventListener("click", async () => {
      const reason = document.getElementById("reject-reason-select")?.value || "Không đạt cảm quan";
      const note = document.getElementById("reject-note-input")?.value.trim() || "";
      const { user } = getAuthSession();
      try {
        const res = await apiClient.rejectInspection({
          reason,
          note,
          confirmed_by: user?.full_name || "Nhân viên bếp",
        });
        playRejectAlarm();
        if (rejectPanel) rejectPanel.style.display = "none";
        const noteEl = document.getElementById("reject-note-input");
        if (noteEl) noteEl.value = "";
        if (res?.snapshot) this.update(res.snapshot, true);
        this.toast(`Đã ghi nhận từ chối hàng: ${reason}`, "warning");
      } catch (e) {
        this.toast(`Lỗi từ chối hàng: ${e.message}`, "error");
      }
    });

    document.getElementById("btn-reset-session")?.addEventListener("click", async () => {
      try {
        const res = await apiClient.resetStation({ reset_order: false });
        this.lastInspectionCode = null;
        if (res?.snapshot) {
          this.update(res.snapshot, true);
        }
        this.toast("Đã reset phiên trạm cân về trạng thái sẵn sàng (IDLE).", "info");

        const order = this.orders.find((o) => o.id === this.activeOrderId);
        const promptBox = document.getElementById("wg-reset-order-prompt");
        const promptMsg = document.getElementById("wg-reset-order-msg");
        if (promptBox) {
          if (order && order.progress?.completed > 0) {
            if (promptMsg) {
              promptMsg.textContent = `Phiếu "${order.title}" đang có ${order.progress.completed}/${order.progress.total} món tích xanh. Reset lại phiếu này để demo lặp lại?`;
            }
            promptBox.style.display = "block";
          } else {
            promptBox.style.display = "none";
          }
        }
      } catch (e) {
        this.toast(`Lỗi Reset phiên: ${e.message}`, "error");
      }
    });

    document.getElementById("btn-reset-active-order")?.addEventListener("click", async () => {
      if (!this.activeOrderId) return;
      if (!window.confirm("Bạn có chắc muốn reset toàn bộ tiến độ cân của phiếu này về 0%?")) return;
      const promptBox = document.getElementById("wg-reset-order-prompt");
      if (promptBox) promptBox.style.display = "none";
      try {
        const res = await apiClient.resetOrder(this.activeOrderId);
        this.lastInspectionCode = null;
        this.lastOrderStatus = "PENDING";
        if (res?.order) this.onOrderEvent(res.order);
        if (res?.snapshot) this.update(res.snapshot, true);
        this.toast("Đã reset tích xanh của phiếu hiện tại về 0%.", "success");
      } catch (e) {
        this.toast(e.message, "error");
      }
    });

    document.getElementById("btn-dismiss-reset-prompt")?.addEventListener("click", () => {
      const promptBox = document.getElementById("wg-reset-order-prompt");
      if (promptBox) promptBox.style.display = "none";
    });

    const triggerRescan = async () => {
      try {
        const res = await apiClient.inspectNow();
        if (res.snapshot) {
          this.update(res.snapshot);
        }
        await this.reloadOrders();
      } catch (e) {
        this.toast(`Lỗi nhận diện AI: ${e.message}`, "error");
      }
    };

    document.getElementById("btn-inspect-now")?.addEventListener("click", triggerRescan);
    document.getElementById("btn-rescan")?.addEventListener("click", triggerRescan);

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
          (it) => (it.status === "PENDING" || it.status === "PARTIAL") && it.class_name.toLowerCase() === targetClass
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
    const weightG = Number(snapshot.weight_gram || 0);
    if (snapshot.state === "IDLE" && (!snapshot.current_inspection || weightG < 8.0)) {
      this.lastInspectionCode = null;
    }

    updateWeightGauge(snapshot);
    updateLiveCameraCard(snapshot);
    updateNutritionTable(snapshot);
    this._renderOrderChecklist();

    if (!silent && snapshot.current_inspection && !(snapshot.state === "IDLE" && weightG < 8.0)) {
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
      this.toast("ĐÃ NHẬP ĐỦ 100% NGUYÊN LIỆU CHO BẾP", "success");
    } else {
      this.lastOrderStatus = order.status;
    }
  }
}
