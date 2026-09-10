# Architecture

Tài liệu này là quy chuẩn bắt buộc khi team hoặc AI thêm tính năng mới. Mục tiêu là giữ code dễ tìm, không đăng ký trùng command, không tạo nhiều nguồn database và không tự viết thêm một hệ thống quyền riêng.

## Luồng chuẩn

```text
Discord command/interaction
        ↓
cogs/<catalog>/<feature>_cog.py
        ↓
services/<feature>_service.py
        ↓
utils.CogDatabase
        ↓
database/<name>.db
```

Nếu tính năng có giao diện:

```text
cog nghiệp vụ
  ├── gọi ui/<feature>/components.py
  ├── gọi ui/<feature>/ui.py
  └── giao diện lấy icon từ ui/<feature>/emoji.py
```

## Trách nhiệm từng layer

### Cog

Cog chỉ chứa:

- Prefix command và slash command.
- Kiểm tra quyền qua helper dùng chung.
- Điều phối luồng nghiệp vụ.
- Gọi service để đọc/ghi dữ liệu.
- Gọi UI để gửi embed, button, select hoặc modal.

Cog không được:

- Kết nối SQLite trực tiếp.
- Tự tạo một database quyền riêng.
- Chứa hàng loạt class `View`, `Select`, `Modal` hoặc mẫu embed.
- Tách các command cùng một nghiệp vụ thành nhiều file riêng.
- Để service hoặc UI import trực tiếp class cog, gây vòng phụ thuộc.

### Service

Service chịu trách nhiệm:

- Tạo và migrate bảng.
- Đọc/ghi database.
- Business logic dùng chung.
- Validate dữ liệu ở mức nghiệp vụ.
- Cung cấp API ổn định cho cog.

Mỗi service tạo database bằng:

```python
from utils import CogDatabase


class ExampleService:
    def __init__(self):
        self.db = CogDatabase("example")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "items",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL
            """,
        )
```

`CogDatabase("example")` tự dùng đường dẫn `database/example.db`. Không nối chuỗi đường dẫn database thủ công và không đặt DB trong `cogs/`.

### UI

Tính năng có giao diện tạo folder:

```text
ui/<feature>/
├── __init__.py
├── emoji.py
├── components.py
└── ui.py
```

Quy ước:

- `emoji.py`: fallback emoji, Discord emoji ID và hàm resolve emoji.
- `components.py`: `View`, `Button`, `Select`, `Modal`, `TextInput`.
- `ui.py`: embed, splash, nội dung trình bày và helper gửi interaction.
- Không đặt business logic hoặc truy vấn database trong UI.
- UI nhận đối tượng cog qua constructor và chỉ gọi public callback mà cog cung cấp.
- Service không được truyền thẳng vào UI nếu UI có thể gọi callback của cog.
- Cog không tự dựng embed nếu tính năng đã có folder UI.

Ví dụ emoji:

```python
FALLBACK_EMOJIS = {"ticket": "🎫"}
DISCORD_EMOJI_IDS = {"ticket": ""}


def ticket_emoji(key: str) -> str:
    ...
```

Khi thêm emoji Discord, chỉ cập nhật `DISCORD_EMOJI_IDS` hoặc biến môi trường tương ứng. Không hardcode ID emoji ở button/embed.

## Quy tắc catalog và cog

Loader tự tìm đệ quy mọi file kết thúc bằng `_cog.py`.

```text
cogs/
├── help_cog.py
├── user/
├── booking/
├── bot/
├── level/
├── role/
└── administrator/
```

Quy tắc nhóm file:

- Một catalog là một folder.
- Một nhóm nghiệp vụ liên quan là một cog.
- Không tách mỗi command thành một cog.
- Không gom toàn bộ catalog vào một cog khổng lồ.
- Các quyền quản trị như admin, mod, operator và staff nằm trong `administrator`.

Ví dụ đúng:

- `administrator/ban_cog.py`: `ban`, `unban`, `kick`.
- `booking/luong_cog.py`: `luong`, `tinhluong`, `traluong`.
- `role/role_cog.py`: `role`, `addrole`, `removerole`, `setrole`, `perms`, `myroles`, `rolescommands`.
- `administrator/ticket_cog.py`: toàn bộ command và nghiệp vụ Ticket.

Ví dụ sai:

```text
cogs/ticket/add_user_cog.py
cogs/ticket/remove_user_cog.py
cogs/ticket/claim_cog.py
cogs/ticket/close_cog.py
```

Các command trên cùng thuộc Ticket nên phải nằm trong một `ticket_cog.py`. Button/embed của chúng đặt trong `ui/ticket/`.

## Quyền admin và role DB

Nguồn quyền dùng chung:

- Hard admin: `DISCORD_OWNER_IDS` trong `.env`.
- Admin mềm: `database/bot_admins.db`.
- Quyền command theo Discord role: `database/command_role.db`.
- Role hệ thống như `booking`: `database/guild_settings.db`.

Cog quản trị phải kế thừa:

```python
from cogs.admin_command_utils import AdminCommandBase


class ExampleCog(AdminCommandBase):
    ...
```

Prefix command:

```python
@commands.command(name="example")
async def example(self, ctx):
    if not await self.require_role_or_admin_ctx(ctx, "example"):
        return
```

Interaction, button hoặc slash command:

```python
if not await self.require_role_or_admin_interaction(interaction, "example"):
    return
```

Kiểm tra không cần gửi lỗi ngay:

```python
allowed = self.can_use_role_or_admin(ctx, "example")
```

Không được:

- Chỉ dùng `member.guild_permissions.administrator`.
- Tự tạo `example_staff_roles`.
- Tạo một `AdminService`/`RolePermissionService` mới trong từng callback.
- Kiểm tra role bằng tên cố định.
- Ghi role permission vào database nghiệp vụ.

Role được cấp quyền bằng:

```text
baddrole @role example
bremoverole @role example
```

Một nhóm command dùng chung quyền phải thống nhất một key. Ví dụ toàn bộ Ticket dùng key `ticket`, kể cả manager, panel, claim, add/remove user và transfer.

## Database và liên kết dữ liệu

Trước khi tạo DB mới phải kiểm tra dữ liệu đã có nguồn chung chưa:

- User, cash, lương cơ bản: `users.db` qua `UserService`.
- Tỷ giá và đồng bộ casino: `users.db` qua `CurrencySyncService`.
- Booking, mốc giờ, trả lương: `booking.db` qua `BookingService`.
- Quyền command: `command_role.db` qua `RolePermissionService`.
- Admin mềm: `bot_admins.db` qua `AdminService`.
- Prefix: `bot_settings.db` qua `SettingsService`.
- Role hệ thống: `guild_settings.db` qua `GuildSettingsService`.
- Ticket: `ticket_system.db` qua `TicketService`.
- Bank/nạp tiền/donate: `bank_payments.db` qua `BankPaymentService`.
- Trạng thái AFK theo server/user: `afk.db` qua `AfkService`.
- Log cash/chat/voice/server/member: `log_system.db` qua `LogService`.

Không nhân đôi dữ liệu. Ví dụ Ticket không tạo bảng staff role riêng vì quyền staff đã có trong `command_role.db`.

### Đồng bộ cash với casino

Bot tổng và casino phải trỏ `CASH_DB_PATH` tới cùng file `users.db`.

```text
cogs/administrator/currency_rate_cog.py
        ↓
services/currency_sync_service.py
        ↓
users.db
├── users
├── currency_exchange_rate
└── currency_wallet_sync
        ↑
casino đọc tỷ giá và tự đồng bộ ví OWO
```

Quy tắc:

- `currency_exchange_rate` chỉ có một dòng tỷ giá hiện tại.
- `currency_wallet_sync` lưu mốc số dư đã đồng bộ cho từng user.
- Khi admin đổi tỷ giá bằng `rate`, OWO giữ nguyên; cash và mốc đồng bộ được tính lại theo tỷ giá mới.
- Cash âm từ casino được giữ trong `users.cash` như khoản nợ; bot tổng chỉ cho cộng/nạp để bù nợ, không cho thao tác chi tiêu tạo thêm nợ.
- Hai bot dùng SQLite WAL và không tạo database cash riêng.

### Bank, nạp tiền và donate

Luồng bank dùng chung:

```text
cogs/user/naptien_cog.py hoặc cogs/user/donate_cog.py
        ↓
services/bank_service.py
        ↓
database/bank_payments.db
        ↓
services/user_service.py cộng cash vào users.db
        ↓
cogs/cash_log_utils.py gửi log cash qua LogService
```

Quy tắc:

- `naptien` và `donate` là hai cog riêng trong catalog `user` vì người dùng gọi trực tiếp.
- Cấu hình ACB nằm trong `BankPaymentService`, không đọc `.env` rải rác trong cog.
- `.env` chỉ là giá trị mặc định; admin có thể đổi bằng command Discord.
- QR/card/embed nằm trong `ui/user/payment_ui.py`.
- Button xác nhận chuyển tiền dùng callback trong `cogs/user/payment_common.py`; reload số dư ngân hàng là luồng admin-only trong cog nạp/donate.
- `naptien_cog.py` duy trì vòng quét giao dịch đang chờ mỗi 5 giây. Button chỉ yêu cầu kiểm tra ngay, không tự cộng tiền khi ngân hàng chưa ghi nhận giao dịch.
- `naptien` bank thành công cộng `cash` và `total_money` trong `UserService` để toàn server dùng chung ví.
- `donate` bank không cộng cash; chỉ cộng `total_donate` và BXH donate của server.
- `donate cash` trừ cash hiện có của user, sau đó cộng `total_donate` và BXH donate của server.
- Bảng xếp hạng donate theo tháng nằm trong `bank_payments.db`; reset chỉ xóa dữ liệu bảng tháng, không trừ cash và không xóa tổng donate của user.
- Kênh cảm ơn và kênh bảng xếp hạng donate là hai cấu hình độc lập. Nạp tiền không dùng bảng xếp hạng hoặc thông báo cảm ơn.
- Ảnh nền được đặt riêng tại `ui/user/assets/naptien/` và `ui/user/assets/donate/`; dùng tên `card.png` hoặc `background.png` (khuyến nghị 980x620), không nhúng file ảnh vào cog.
- Admin cũng có thể thay nền runtime bằng `naptien config decor` / `donate config decor` với URL hoặc ảnh đính kèm.
- Log nạp, donate, chuyển, cộng/trừ cash gửi về channel `log cash` qua `LogService`.
- Nếu chưa set `log cash`, helper log tiền tự tìm kênh `log_cash`, `log-cash` hoặc `cash-log`.
- Không tạo DB cash riêng cho bank và không cộng tiền bằng SQL trực tiếp trong cog.

### Khóa command theo channel

- Cấu hình nằm trong `command_toggle.db` qua `ChannelCommandToggleService`.
- Command quản trị nằm chung trong `cogs/administrator/command_cog.py`.
- Có thể khóa command gốc hoặc command con, ví dụ `giveaway` hoặc `level setup`.
- Hard admin luôn được bỏ qua khóa channel để có thể sửa cấu hình.
- Khóa command không được chặn listener nền như log, thông báo join/leave, level tracking hoặc auto response.

Các biến cấu hình hỗ trợ:

```text
ACB_USERNAME
ACB_PASSWORD
ACB_ACCOUNT_NUMBER
ACB_ACCOUNT_NAME
ACB_CLIENT_ID
ACB_BANK_CODE
NAPTIEN_DECOR_URL
DONATE_DECOR_URL
DONATE_THANK_TEMPLATE
```

Khi dữ liệu phải liên kết:

- Lưu Discord ID dưới dạng `INTEGER`.
- Mọi query theo server phải có `guild_id`.
- Mọi table cần tính theo user phải dùng `user_id`.
- Tên hiển thị chỉ là dữ liệu phụ, không dùng thay ID.
- Migration cột mới đặt trong service, dùng kiểm tra `PRAGMA table_info`.

## Mẫu feature chuẩn

```text
cogs/administrator/example_cog.py
services/example_service.py
ui/example/__init__.py
ui/example/emoji.py
ui/example/components.py
ui/example/ui.py
test/test_example.py
```

Không bắt buộc tạo đủ mọi file:

- Không có DB: không cần service.
- Không có button/embed/menu riêng: không cần folder UI.
- Chỉ tạo file thực sự có trách nhiệm rõ ràng.
- Không tạo `helpers.py`, `permissions.py`, `resolvers.py` riêng nếu helper nhỏ chỉ dùng cho một cog.
- Mỗi feature có UI riêng tương ứng với cog; không gom UI của nhiều command vào một module dùng chung.
- Command có nhiều nội dung/icon tùy chỉnh phải có menu config và lưu cấu hình theo guild.
- Cog không được khai báo `View`, `Button`, `Select`, `Modal` hoặc hardcode khối nội dung giao diện dài.

## Ticket là mẫu tham chiếu

Ticket hiện dùng cấu trúc:

```text
cogs/administrator/ticket_cog.py
services/ticket_service.py
ui/ticket/
├── emoji.py
├── components.py
└── ui.py
```

- `ticket_cog.py`: command, callback nghiệp vụ, kiểm tra quyền và gọi service.
- `ticket_service.py`: config, ticket, event, trạng thái và transcript metadata.
- `components.py`: panel, control, manager, select và modal.
- `ui.py`: toàn bộ embed/splash Ticket.
- `emoji.py`: fallback và Discord emoji ID.
- Tất cả thao tác quản trị dùng quyền `ticket` trong `command_role.db`.

## Checklist trước khi code

1. Tính năng thuộc catalog nào?
2. Có cog liên quan để bổ sung chưa?
3. Dữ liệu đã tồn tại trong service/DB nào?
4. Command có cần admin hoặc role DB không?
5. Nếu có quyền, key quyền dùng chung là gì?
6. Có button/select/modal/embed không? Nếu có, tạo hoặc dùng `ui/<feature>/`.
7. Nội dung hoặc icon có nhiều mục cần sửa không? Nếu có, tạo menu config riêng trong UI.
8. Có đang tạo file nhỏ chỉ để chứa một helper không cần thiết không?
9. Help và command reference đã cập nhật chưa?

## Checklist trước khi commit

```bash
python3 -m py_compile cogs/<catalog>/<feature>_cog.py
python3 -m unittest discover -s test -p 'test_<feature>*.py'
```

Kiểm tra thêm:

- Loader chỉ thấy một cog cho feature.
- Không có command/slash trùng.
- Không còn import đường dẫn cũ.
- DB tự tạo trong `database/`.
- Role DB thật sự điều khiển được command và button.
- UI không truy vấn DB trực tiếp.

## Chỉ dẫn ngắn cho AI

Khi giao việc cho AI, yêu cầu AI đọc file này trước và tuân thủ:

> Giữ command liên quan trong một cog theo catalog. Cog chỉ xử lý command/quyền/nghiệp vụ. Database đặt trong service và dùng `CogDatabase`. Lệnh quản trị kế thừa `AdminCommandBase`, dùng hard admin hoặc role permission trong `command_role.db`. Giao diện tách thành `ui/<feature>/components.py`, `ui.py`, `emoji.py`. Không tạo database quyền riêng và không tách mỗi command thành một file.
