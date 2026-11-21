/**
 * Thẻ bảng chi tiết giá trị dinh dưỡng theo khối lượng thực tế (Calories, Protein, Lipid, Carb, Vi chất).
 */
export function renderNutritionTable(container) {
  container.innerHTML = `
    <div class="card">
      <div class="card-head">
        <h3 class="card-title">Định Lượng Dinh Dưỡng Theo Khối Lượng Cân</h3>
        <span id="nt-edible-badge" class="badge badge-info">Phần ăn được: 100%</span>
      </div>

      <div id="nt-quality-banner" class="status-banner success">
        <div style="font-size:17px; font-weight:700;" id="nt-quality-title">Sẵn sàng tiếp nhận thực phẩm</div>
        <div style="font-size:15px; margin-top:4px;" id="nt-quality-desc">
          Hệ thống tự động quy đổi Calories, Protein, Lipid, Carbohydrate và vi chất theo khối lượng cân được.
        </div>
      </div>

      <div class="macro-grid">
        <div class="macro-card">
          <div class="macro-label">Năng lượng</div>
          <div class="macro-val tabular-nums" id="nt-kcal">0.0 kcal</div>
          <div class="macro-sub" id="nt-kcal-pct">0% (2000 kcal)</div>
        </div>
        <div class="macro-card">
          <div class="macro-label">Protein (Đạm)</div>
          <div class="macro-val tabular-nums" id="nt-protein">0.0 g</div>
          <div class="macro-sub" id="nt-protein-pct">0% (60g)</div>
        </div>
        <div class="macro-card">
          <div class="macro-label">Lipid (Béo)</div>
          <div class="macro-val tabular-nums" id="nt-fat">0.0 g</div>
          <div class="macro-sub" id="nt-fat-pct">0% (65g)</div>
        </div>
        <div class="macro-card">
          <div class="macro-label">Carbohydrate</div>
          <div class="macro-val tabular-nums" id="nt-carb">0.0 g</div>
          <div class="macro-sub" id="nt-carb-pct">0% (300g)</div>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Vi chất &amp; Chất xơ</th>
              <th>Chuẩn / 100g</th>
              <th>Thực tế (<span id="nt-edible-g">0g</span> ăn được)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Chất xơ (Fiber)</td>
              <td class="tabular-nums" id="nt-100-fiber">—</td>
              <td class="tabular-nums" style="font-weight:700;" id="nt-act-fiber">0 g</td>
            </tr>
            <tr>
              <td>Canxi / Sắt / Vitamin C</td>
              <td class="tabular-nums" id="nt-100-micro">—</td>
              <td class="tabular-nums" style="font-weight:700;" id="nt-act-micro">0 mg / 0 mg / 0 mg</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `;
}

export function updateNutritionTable(snapshot) {
  const insp = snapshot?.current_inspection;
  const banner = document.getElementById("nt-quality-banner");
  const qTitle = document.getElementById("nt-quality-title");
  const qDesc = document.getElementById("nt-quality-desc");
  const edibleBadge = document.getElementById("nt-edible-badge");

  if (!banner || !qTitle || !qDesc) return;

  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  if (!insp) {
    banner.className = "status-banner success";
    qTitle.textContent = "Sẵn sàng tiếp nhận thực phẩm";
    qDesc.textContent = "Đặt thực phẩm từ 15g trở lên để kiểm định chất lượng và tính dinh dưỡng.";
    if (edibleBadge) edibleBadge.textContent = "Phần ăn được: 100%";
    setText("nt-kcal", "0.0 kcal");
    setText("nt-kcal-pct", "0% (2000 kcal)");
    setText("nt-protein", "0.0 g");
    setText("nt-protein-pct", "0% (60g)");
    setText("nt-fat", "0.0 g");
    setText("nt-fat-pct", "0% (65g)");
    setText("nt-carb", "0.0 g");
    setText("nt-carb-pct", "0% (300g)");
    setText("nt-edible-g", "0g");
    setText("nt-100-fiber", "—");
    setText("nt-act-fiber", "0 g");
    setText("nt-100-micro", "—");
    setText("nt-act-micro", "0 mg / 0 mg / 0 mg");
    return;
  }

  const qual = insp.quality || {};
  banner.className = `status-banner ${qual.alert_level || "success"}`;
  qTitle.textContent = qual.badge_text || qual.status || "Đạt chuẩn";
  qDesc.textContent = qual.recommendation || "";

  const nut = insp.nutrition || {};
  const act = nut.actual || {};
  const p100 = nut.per_100g || {};
  const pct = nut.daily_percent || {};

  if (edibleBadge) {
    edibleBadge.textContent = `Phần ăn được: ${nut.edible_portion_percent || 100}% (${nut.edible_gram || 0}g)`;
  }

  setText("nt-kcal", `${Number(act.energy_kcal || 0).toFixed(1)} kcal`);
  setText("nt-kcal-pct", `${pct.kcal_pct || 0}% (2000 kcal)`);
  setText("nt-protein", `${Number(act.protein_g || 0).toFixed(1)} g`);
  setText("nt-protein-pct", `${pct.protein_pct || 0}% (60g)`);
  setText("nt-fat", `${Number(act.fat_g || 0).toFixed(1)} g`);
  setText("nt-fat-pct", `${pct.fat_pct || 0}% (65g)`);
  setText("nt-carb", `${Number(act.carbohydrate_g || 0).toFixed(1)} g`);
  setText("nt-carb-pct", `${pct.carb_pct || 0}% (300g)`);

  setText("nt-edible-g", `${nut.edible_gram || 0}g`);
  setText("nt-100-fiber", p100.fiber_g !== undefined ? `${p100.fiber_g} g` : "—");
  setText("nt-act-fiber", `${act.fiber_g || 0} g`);
  setText(
    "nt-100-micro",
    p100.calcium_mg !== undefined ? `${p100.calcium_mg}mg / ${p100.iron_mg}mg / ${p100.vitamin_c_mg}mg` : "—"
  );
  setText(
    "nt-act-micro",
    `${act.calcium_mg || 0} mg / ${act.iron_mg || 0} mg / ${act.vitamin_c_mg || 0} mg`
  );
}
