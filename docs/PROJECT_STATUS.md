# Project Status

## Phiên bản hiện tại

`v3.2`

Trạng thái: đang phát triển, đã chuẩn hóa catalog cog, service/database, role permission và UI theo feature.

## Đã có

- Recursive cog loader cho `cogs/` và subfolder catalog.
- Help menu theo category.
- User commands: `profile`, `cash`, `naptien`, `donate`, `points`, `time`, `give`, `topusers`, `afk`, `random`, `pick`, `uptime`, `setname`, `note`.
- Booking commands: `luong`, `star`, `tinhluong`, `topbook`, `topnap`, `topgift`.
- Role commands: `addrole`, `removerole`, `setrole`, `perms`, `myroles`, `rolescommands`.
- Administrator commands theo nhóm:
  - Admin DB theo server: `addadmin`, `rmadmin`; quyền cash riêng: `addcashadmin`, `rmcashadmin`.
  - Economy: `cash a|r|e`, `luong a|r|e`, `star a|r|e`, `points a|r|e`, `time a|r|e`, `tongluong`, `topstar`, `addtime a|r|e`, `subtime`, `addpoints a|r|e`.
  - Booking config: `bookconfig`, `setgiobook`, `setphantram`, `setan`.
  - Responsive: `ar`, `form`, `res`, `up`.
  - Moderation: `ban`, `unban`, `kick`, `role`, `mute`, `unmute`, `lock`, `unlock`.
  - Operator: `gitpull`, `gitstatus`, `reload`, `load`, `unload`, `cogs`, `prefix`.
  - Command channel: `command`, `enable`, `disable`.
  - Slash: `/antiraid`, `/giveaway`, `/group`, `/level`, `/naptien`, `/donate`, `/ticket`.
- Event contest: quản lý sự kiện thi ảnh/video/meme, tự động kiểm duyệt bài thi, bảng xếp hạng real-time chống rate-limit.
- Bank/VietQR: tạo QR nạp tiền/donate, kiểm tra giao dịch mỗi 5 giây, admin reload số dư ACB, cộng cash và gửi log cash.
- Donate có kênh cảm ơn, bảng xếp hạng tháng 1-50, phân trang 10 người và reset không ảnh hưởng cash/tổng donate.
- Note có public/private, note cho người khác theo quyền, TXT popup và nội dung dài có thể thu gọn/phóng to.
- Command có thể bị khóa theo từng channel; hỗ trợ khóa command gốc hoặc command con.
- Music player lưu volume độc lập theo từng user; mức vừa chỉnh áp dụng cho queue hiện tại, phiên mới nạp volume của người mở phiên.
- Khi thêm bài hoặc playlist vào phiên đang phát, bot gửi thông báo queue rồi đưa card player xuống cuối chat.
- Card player có thanh tiến trình GIF, đồng bộ playback clock mỗi 30 giây và persistent controls.
- Playback không chờ render card; card được dựng bằng background task sau khi nhạc bắt đầu.
- Giveaway có menu `ga config` để sửa nội dung, icon và emoji tham gia theo server.
- Ticket manager có menu riêng cho nội dung và icon theo server.
- Ticket hỗ trợ cấu hình role/user được tag riêng theo từng mục; mapping lưu DB theo server và đồng thời cấp quyền xem ticket.
- Music player có menu settings cho giao diện, nội dung, icon và reaction; autoplay/loop không được lưu.
- Log system có `chat`, `voice`, `server`, `join` và `cash`.
- Database tự tạo cho users, booking, role permission, admin, settings, guild settings, responsive, bank payments, AFK và log system.
- Multi-server: `points`, lương, toàn bộ booking và prefix được tách riêng theo server; `cash` vẫn global dùng chung mọi server.
- Dữ liệu global cũ chỉ tự migrate khi bot xác định đúng một server đã cấu hình, tránh nhân dữ liệu nhầm sang nhiều server.
- Định dạng tiền VNĐ thống nhất.
- Ticket dùng một cog tại `cogs/administrator/ticket_cog.py`.
- Ticket dùng `TicketService` và `ticket_system.db`.
- Ticket dùng chung quyền `ticket` trong `command_role.db`, không còn staff-role DB riêng.
- UI feature được tách thành `components.py`, `ui.py`, `emoji.py`.

## Setup nhanh

```bash
pip install -r requirements.txt
python main.py
```

## Test trước khi push

```bash
.venv/bin/python -m compileall cogs services utils.py main.py
```

Nên test thêm:

- Bot khởi động không lỗi cog.
- `{prefix}help` mở menu.
- `{prefix}cash`, `{prefix}points`, `{prefix}time` hiện dữ liệu của bạn.
- `{prefix}luong` hiện bảng lương ở kênh hiện tại.
- `{prefix}give @user 10k` chuyển được nếu đủ cash.
- `{prefix}naptien 10k` tạo QR, bấm **Tôi đã chuyển tiền** hoặc `{prefix}naptien check`.
- `{prefix}naptien reload` cần quyền cash để xem số dư tài khoản ngân hàng ACB; user thường vẫn tự nạp và auto cộng cash.
- `{prefix}dnt bank 10k [lời nhắn]` tạo QR donate nhưng không cộng cash; `{prefix}dnt cash 10k [lời nhắn]` trừ cash và ghi nhận donate.
- `{prefix}dnt` mở menu + biểu mẫu chọn Bank/QR hoặc Cash.
- `{prefix}donate config leaderboard #top-donate` set bảng xếp hạng và `{prefix}donate reset` reset bảng tháng bằng quyền cash.
- `{prefix}disable ga` khóa giveaway tại channel hiện tại; `{prefix}enable ga` bật lại.
- `{prefix}log cash #log-cash` nhận log tiền, nạp, donate và give. Nếu chưa set, bot tự tìm kênh `log_cash`, `log-cash` hoặc `cash-log`.
- `{prefix}setrole @Booking booking` nhận role booking.
- `{prefix}tinhluong` gửi DM.
- `{prefix}ar a`, `{prefix}form`, `{prefix}res`, `{prefix}up` hoạt động đúng.

## Workflow cho feature mới

1. Chọn catalog phù hợp trong `cogs/`.
2. Gộp các lệnh liên quan vào cùng một cog.
3. Kế thừa `AdminCommandBase` nếu cần hard admin/admin DB/role DB.
4. Tạo hoặc cập nhật service nếu có logic/database; dùng `CogDatabase`.
5. Tách UI theo từng feature; lệnh có nhiều nội dung/icon phải có menu config riêng.
6. Cập nhật `COMMANDS_REFERENCE.md` nếu thêm/sửa lệnh.
7. Chạy compile/load test.
8. Commit bằng tiếng Việt theo nhóm thay đổi.

## Git workflow

- Không commit `.env`, database `.db`, logs, `__pycache__`.
- Commit theo nhóm:
  - `v1.x: cập nhật ...`
  - `v1.x: thêm ...`
  - `v1.x: sửa ...`
- Push sau khi compile/load cogs không lỗi.

## Việc sắp tới

- Hoàn thiện casino/marry/gift nếu tiếp tục phát triển.
- Bổ sung test tự động cho service layer.
- Rà soát permission chi tiết cho từng command admin khi thêm tính năng mới.
- Tiếp tục chuyển UI đang hardcode trong cog cũ sang cấu trúc UI theo feature.
