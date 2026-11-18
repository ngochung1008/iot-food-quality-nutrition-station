# HƯỚNG DẪN VẬN HÀNH TRẠM TẠI BẾP ĂN TẬP THỂ

## 1. Quy trình tiếp nhận thực phẩm đầu vào
1. Mở giao diện chính **Trạm Vận Hành Chính** (`http://<IP-PI>:8000`).
2. Kiểm tra cân ở trạng thái `0.0g`. Nếu đặt rổ/khay chứa, nhấn **Tare / Trừ bì (0g)** trước khi cho thực phẩm vào.
3. Đặt thực phẩm lên đĩa cân (≥ 15g). Hệ thống tự chuyển `CHỜ HÀNG` → `ỔN ĐỊNH` (1.5s) → `NHẬN DIỆN AI`.
4. Kiểm tra kết quả trên màn hình:
   - **ĐẠT CHUẨN TƯƠI SẠCH (Xanh lá):** Xem hàm lượng Kcal, Protein, Lipid, Carb, Vi chất tính theo khối lượng cân được và nhấn **Chốt đơn & Lưu phiếu**.
   - **CẦN KIỂM TRA (Vàng):** Đầu bếp kiểm tra lại cảm quan hoặc chọn lại đúng tên thực phẩm trong danh sách 64 loại trước khi chốt phiếu.
   - **KHÔNG ĐẠT - PHÁT HIỆN HƯ HỎNG (Đỏ):** Hệ thống phát âm thanh cảnh báo, hiển thị cảnh báo trên LCD và từ chối nhập kho.
5. Nhấc khay ra khỏi bàn cân (`< 10g`), trạm tự động reset về trạng thái sẵn sàng cho lô tiếp theo.

## 2. Hiệu chuẩn cân định kỳ
- Vào tab **Phần Cứng & Hiệu Chuẩn**:
  1. Dọn trống đĩa cân → Nhấn **1. Thực hiện Tare (Lấy điểm 0)**.
  2. Đặt quả cân chuẩn (ví dụ `500g` hoặc `1000g`) lên tâm đĩa cân → Nhập khối lượng → Nhấn **2. Đo vật mẫu & Lưu hệ số**.
  3. Hệ số `scale_ratio` mới được ghi vào `hardware/calibration.json` và có hiệu lực ngay lập tức.
