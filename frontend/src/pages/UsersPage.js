/**
 * Trang Quản Lý Tài Khoản & Phân Quyền RBAC (Chỉ Quản trị viên / Admin).
 */
import { apiClient, getAuthSession } from "../services/apiClient.js";

export class UsersPage {
  constructor(toast) {
    this.toast = toast;
    this.users = [];
  }

  async mount(rootEl) {
    rootEl.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:18px;">
        <div class="card">
          <div class="card-head">
            <h3 class="card-title">Thêm Tài Khoản Nhân Viên Mới</h3>
            <span class="badge badge-success">RBAC Security</span>
          </div>

          <form id="create-user-form" style="display:grid; grid-template-columns:1fr 1fr 1.2fr 1fr auto; gap:10px; align-items:end;">
            <div>
              <label style="display:block; font-size:12px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Tên đăng nhập</label>
              <input id="u-username" class="input" style="width:100%;" placeholder="vd: beppho1" required />
            </div>
            <div>
              <label style="display:block; font-size:12px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Mật khẩu</label>
              <input id="u-password" type="password" class="input" style="width:100%;" placeholder="Tối thiểu 4 ký tự" required />
            </div>
            <div>
              <label style="display:block; font-size:12px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Họ và tên</label>
              <input id="u-fullname" class="input" style="width:100%;" placeholder="Họ tên nhân viên" required />
            </div>
            <div>
              <label style="display:block; font-size:12px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Vai trò</label>
              <select id="u-role" class="select" style="width:100%;">
                <option value="RECEIVER">Nhân viên tiếp nhận (RECEIVER)</option>
                <option value="CHEF">Đầu bếp trưởng (CHEF)</option>
                <option value="ADMIN">Quản trị viên (ADMIN)</option>
              </select>
            </div>
            <button class="btn btn-primary" type="submit">Tạo tài khoản</button>
          </form>
        </div>

        <div class="card">
          <div class="card-head">
            <h3 class="card-title">Danh Sách Nhân Sự Hệ Thống</h3>
            <button id="btn-reload-users" class="btn btn-sm btn-outline" type="button">Làm mới</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Tên đăng nhập</th>
                  <th>Họ và tên</th>
                  <th>Vai trò</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody id="users-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    await this.loadUsers();
    this._bindEvents();
  }

  async loadUsers() {
    const tbody = document.getElementById("users-tbody");
    if (!tbody) return;
    const { user: current } = getAuthSession();
    try {
      this.users = await apiClient.getUsers();
      tbody.innerHTML = this.users
        .map((u) => {
          const isSelf = current && String(current.id) === String(u.id);
          const roleBadge =
            u.role === "ADMIN" ? "badge-success" : u.role === "CHEF" ? "badge-info" : "badge-warning";
          return `
            <tr>
              <td class="tabular-nums">${u.id}</td>
              <td><strong>${u.username}</strong></td>
              <td>${u.full_name}</td>
              <td><span class="badge ${roleBadge}">${u.role}</span></td>
              <td><span class="badge ${u.is_active ? "badge-success" : "badge-danger"}">${u.is_active ? "Đang hoạt động" : "Tạm khóa"}</span></td>
              <td style="display:flex; gap:6px;">
                <button class="btn btn-sm btn-outline btn-toggle-active" data-id="${u.id}" data-active="${u.is_active}" ${isSelf ? "disabled" : ""} type="button">
                  ${u.is_active ? "Khóa" : "Mở khóa"}
                </button>
                <button class="btn btn-sm btn-outline btn-del-user" data-id="${u.id}" ${isSelf ? "disabled" : ""} type="button">
                  Xóa
                </button>
              </td>
            </tr>
          `;
        })
        .join("");

      tbody.querySelectorAll(".btn-toggle-active").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = Number(btn.dataset.id);
          const curActive = btn.dataset.active === "true";
          await apiClient.updateUser(id, { is_active: !curActive });
          this.toast("Đã cập nhật trạng thái tài khoản", "info");
          await this.loadUsers();
        });
      });

      tbody.querySelectorAll(".btn-del-user").forEach((btn) => {
        btn.addEventListener("click", async () => {
          if (!confirm("Xóa tài khoản này?")) return;
          await apiClient.deleteUser(Number(btn.dataset.id));
          this.toast("Đã xóa tài khoản", "info");
          await this.loadUsers();
        });
      });
    } catch (e) {
      this.toast(e.message, "error");
    }
  }

  _bindEvents() {
    document.getElementById("btn-reload-users")?.addEventListener("click", () => this.loadUsers());
    document.getElementById("create-user-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await apiClient.createUser({
          username: document.getElementById("u-username").value.trim(),
          password: document.getElementById("u-password").value,
          full_name: document.getElementById("u-fullname").value.trim(),
          role: document.getElementById("u-role").value,
        });
        this.toast("Đã tạo tài khoản thành công", "success");
        e.target.reset();
        await this.loadUsers();
      } catch (err) {
        this.toast(err.message, "error");
      }
    });
  }

  update() {}
}
