# Docs Overview

Bộ docs này là phần tài liệu chính của dự án sau refactor catalog cogs.

## Nên đọc theo thứ tự

1. [ARCHITECTURE.md](ARCHITECTURE.md)
2. [COMMANDS_REFERENCE.md](COMMANDS_REFERENCE.md)
3. [PROJECT_STATUS.md](PROJECT_STATUS.md)

Team member hoặc AI phải đọc `ARCHITECTURE.md` trước khi tạo cog, service, database hoặc UI mới.

## Mục tiêu

- Giữ tài liệu gọn trong 3-4 file chính.
- README ngoài repo dành cho cộng đồng.
- Docs trong folder này dành cho setup, phát triển và kiểm tra command.
- Khi thêm lệnh mới, cập nhật `COMMANDS_REFERENCE.md`.
- Khi đổi cấu trúc hoặc database, cập nhật `ARCHITECTURE.md`.
- Không tạo thêm docs rời nếu nội dung có thể cập nhật vào 3 file trên.
- UI mới theo `ui/<feature>/components.py`, `ui.py`, `emoji.py`.
- Quyền quản trị dùng helper chung và `command_role.db`, không tạo bảng staff-role riêng.

## Version ghi chú

- `v0.1`: khởi tạo dự án và docs ban đầu.
- `v0.2`: refactor cogs theo catalog.
- `v0.3`: thêm booking, role permission, admin DB và economy.
- `v0.4`: thêm responsive profile, auto response, cash/give và cập nhật help.
- `v0.7`: chuẩn hóa cog/service/UI, Ticket dùng quyền role DB chung.
- `v1.7`: thêm nạp tiền/donate ACB, kiểm tra giao dịch, admin xem số dư ACB, QR UI và log cash.
- `v2.5`: hoàn thiện auto check 5 giây, DM thành công và bảng xếp hạng donate tháng.
- `v2.6`: tùy chỉnh nội dung/emoji và giao diện bắt đầu, kết thúc giveaway.
- `v2.7`: thêm bật/tắt command theo từng channel.
- `v2.8`: cập nhật help, README và tài liệu kiến trúc cho các tính năng mới.
- `v2.9`: chuẩn hóa thời gian ở footer nhỏ của embed theo giờ Việt Nam.
- `v3.0`: thêm AFK, random, pick và setname cho user.
- `v3.1`: thêm lock/unlock channel theo quyền role database.
- `v3.2`: cập nhật help và tài liệu cho nhóm lệnh mới.
