# Commands Reference

> Phạm vi dữ liệu: prefix, points, lương và booking độc lập theo từng server. Cash là ví global dùng chung giữa các server.

Prefix lấy từ database `bot_settings.db`, mặc định theo `BOT_PREFIX` trong `.env`.
Prefix không phân biệt chữ hoa/chữ thường.
Trong docs dùng `{prefix}` để đại diện cho prefix hiện tại.

## General

- `{prefix}help`
  - Mở help menu theo category.
- `{prefix}help <command>`
  - Xem chi tiết một lệnh.

## User

- `{prefix}afk [lý do]`
  - Đặt trạng thái AFK. Nếu bỏ trống lý do, bot dùng `AFK`.
  - Khi có người tag, bot báo lý do và thời gian đã AFK; trạng thái tự gỡ khi user nhắn lại.
- `{prefix}random <số lớn nhất>`
  - Chọn số ngẫu nhiên từ 1 đến số đã nhập.
  - Alias: `{prefix}rand`, `{prefix}rd`.
- `{prefix}random set <user_id> <số>`
  - Chỉ hard admin dùng trong DM để chỉ định minh bạch kết quả random kế tiếp của user.
  - Kết quả được ghi rõ là đã chỉ định và thiết lập tự xóa sau một lần dùng.
- `{prefix}pick <mục 1, mục 2, mục 3>`
  - Chọn ngẫu nhiên một mục, hỗ trợ danh sách phân cách bằng dấu phẩy hoặc khoảng trắng.
  - Alias: `{prefix}choose`, `{prefix}chon`, `{prefix}chọn`.
- `{prefix}uptime`
  - Xem thời gian bot/VPS đã chạy, RAM VPS, memory tiến trình bot và dung lượng ổ đĩa.
  - Alias: `{prefix}upt`, `{prefix}system`, `{prefix}sys`, `{prefix}stats`, `{prefix}st`.
- `{prefix}setname <tên mới>`
  - Mọi user được tự đổi nickname của chính mình.
- `{prefix}setname @user <tên mới>`
  - Đổi nickname người khác.
  - Quyền: hard admin hoặc role có quyền `setname` trong database.
  - Alias: `{prefix}setnick`, `{prefix}nickname`.
- `{prefix}note`
  - Xem danh sách note của bạn bằng text thường.
- `{prefix}note <nội dung> [số tiền]`
  - Thêm note vào danh sách của bạn, vẫn hỗ trợ tiền như `100k`, `1m`.
- `{prefix}note d 1,2`
  - Xoá note của bạn theo số thứ tự.
- `{prefix}note 2 +100k` hoặc `{prefix}note 2 -100k`
  - Cộng/trừ tiền vào note số 2 như chế độ cũ.
- `{prefix}note public|private`
  - Bật/tắt cho người khác thêm note vào danh sách của bạn.
  - Có thể viết tắt `pb` hoặc `prv`.
- `{prefix}note public|private @user`
  - Admin hoặc role có quyền `note public` hoặc `note private` bật/tắt quyền nhận note của người khác.
  - Cấp quyền riêng bằng `addrole @role note public` hoặc `addrole @role note private`.
- `{prefix}note status [@user]`
  - Kiểm tra note đang public hay private.
- `{prefix}note @user`
  - Xem note của user đó nếu họ public hoặc bạn có quyền `note`; private sẽ báo không có quyền truy cập.
- `{prefix}note @user <nội dung>`
  - Thêm note vào danh sách người khác nếu họ public, hoặc bạn là admin/role có quyền `note`.
- Reply một tin nhắn rồi dùng `{prefix}note` hoặc `{prefix}note @user`
  - Lưu nội dung, file, sticker hoặc embed của tin nhắn thành note TXT.
  - Note có link **Tin nhắn** để nhảy thẳng tới tin nhắn gốc.
- `{prefix}note @user txt`
  - Hiện nút mở popup nhập tiêu đề và nội dung dài.
- `{prefix}note tiêu đề [file nội dung dài]`
  - Lưu note dạng TXT để dùng cho giao diện/template.
  - Lần tạo đầu không có `- Fix`; sau khi sửa ít nhất một lần mới hiện `- Fix`.
- `{prefix}note view|v [@user] <số>`
  - Xem thành phẩm của note TXT với Markdown và emoji server đã được render.
  - Ban đầu nội dung dài được rút gọn; bấm `Phóng to` để xem đầy đủ và `Thu gọn` để quay lại bản ngắn.
  - Note dạng TXT có nhãn `TXT` ở đầu dòng danh sách và đầu tiêu đề để phân biệt.
- `{prefix}note edit|e [@user] <số> <nội dung>`
  - Sửa note. Người ngoài chỉ sửa được note họ đã thêm, trừ khi có quyền `note`.
- `{prefix}note edit|e @user <số> txt`
  - Hiện nguyên mã nguồn đầy đủ, gồm cả ID emoji, rồi mở popup sửa note TXT.
- `{prefix}notes [@user]`
  - Xem danh sách note bằng embed; xem người khác cần public hoặc quyền `note`.

- `{prefix}profile [@user]`
  - Xem profile của bạn.
  - Xem người khác cần admin bot hoặc role có quyền `profile`.
- `{prefix}cash [@user]`
  - Xem số dư cash.
  - Xem người khác cần cash-admin, role có quyền `cash` hoặc quyền `profile`.
- `{prefix}cash all`
  - Xem tất cả cash trong database.
  - Quyền: hard admin, cash-admin hoặc role có quyền `cash`.
- `{prefix}cash a @user <money>`
  - Cộng cash cho user.
- `{prefix}cash add @user <money>`
  - Cách viết đầy đủ của cộng cash.
- `{prefix}cash r @user <money>`
  - Trừ cash của user.
  - Có thể dùng `{prefix}cash remove @user <money>`, `{prefix}cash rm @user <money>`, `{prefix}cash d @user <money>` hoặc `{prefix}cash delete @user <money>`.
- `{prefix}cash e @user <money>`
  - Set cash của user về số mới.
  - Có thể dùng `{prefix}cash edit @user <money>`.
- Trong DM, quản trị cash dùng thêm server ID: `{prefix}cash a <user_id> <money> <server_id>`.
- `{prefix}points [@user|all]`
  - Xem points của bạn, user khác hoặc tất cả.
  - Xem user khác/all cần admin bot hoặc role có quyền `points`.
- `{prefix}points a|r|e @user <amount>`
  - Quản trị points theo action add/remove/edit.
  - `r` có thể viết `rm`, `remove`, `d` hoặc `delete`.
- `{prefix}time [@user|all]`
  - Xem tổng giờ của bạn, user khác hoặc tất cả.
  - Xem user khác/all cần admin bot hoặc role có quyền `time`.
- `{prefix}time a|r|e @user <hours>`
  - Quản trị tổng giờ theo action add/remove/edit.
  - `r` có thể viết `rm`, `remove`, `d` hoặc `delete`.
- `{prefix}give @user <money>`
  - Chuyển cash cho member trong server.
  - Có thể đảo tham số: `{prefix}give <money> @user`.
  - Ví dụ: `{prefix}give @Yang 10k`.
- `{prefix}naptien <money>`
  - Tạo QR nạp cash theo số tiền.
  - Ví dụ: `{prefix}naptien 100k`.
- `{prefix}naptien check [id|code]`
  - Kiểm tra lại giao dịch đang chờ.
  - Có thể dùng nút **Tôi đã chuyển tiền** dưới QR.
  - Bot cũng tự kiểm tra các giao dịch đang chờ mỗi 5 giây.
  - User tự check QR của mình; check QR người khác cần quyền `cash`.
- `{prefix}naptien reload|sodu|balance`
  - Quyền `cash`: hiển thị số dư tài khoản ngân hàng ACB.
- `{prefix}naptien config username|password|account|name|bank|decor|auto <value>`
  - Cài thông tin ACB/VietQR trực tiếp trong Discord.
  - Quyền: hard admin, cash-admin hoặc role có quyền `cash`.
  - Gửi kèm ảnh và dùng `{prefix}naptien config decor` để thay nền card; dùng `decor off` để về mặc định.
- `/naptien amount:<money>`
  - Slash command tạo QR nạp cash.
- `{prefix}donate|dnt`
  - Không nhập tham số: mở menu Bank/QR hoặc Cash và biểu mẫu nhập số tiền + lời nhắn.
- `{prefix}dnt bank|qr <money> [nội dung]`
  - Tạo QR donate cho server. Khi giao dịch khớp chỉ ghi nhận tổng donate/BXH, không cộng cash.
  - Ví dụ: `{prefix}dnt qr 50k Chúc server phát triển`.
- `{prefix}dnt cash <money> [nội dung]`
  - Trừ cash của người dùng, ghi nhận tổng donate/BXH và gửi thông báo vào channel đã setup.
  - Ví dụ: `{prefix}dnt cash 50k Cảm ơn mọi người`.
- `{prefix}dnt <money> [cash] [nội dung]`
  - Không ghi hình thức: mặc định tạo QR bank. Có thể dùng `{prefix}dnt 50k cash lời nhắn` để donate cash.
- `{prefix}donate check [id|code]`
  - Kiểm tra lại giao dịch donate đang chờ.
  - User tự check QR của mình; check QR người khác cần quyền `cash`.
- `{prefix}donate reload|sodu|balance`
  - Quyền `cash`: hiển thị số dư tài khoản ngân hàng ACB.
- `{prefix}donate config channel #channel`
  - Set channel gửi lời cảm ơn donate.
  - Dùng `off` để tắt channel cảm ơn.
- `{prefix}donate config leaderboard #channel`
  - Set kênh bảng xếp hạng donate tháng, tối đa 50 người và 10 người mỗi trang.
- `{prefix}donate config thanks <template>`
  - Set nội dung cảm ơn donate.
  - Placeholder: `{user}`, `{username}`, `{amount}`, `{code}`, `{message}`, `{method}`, `{server}`.
- `{prefix}donate config decor <url|off>`
  - Set ảnh decorate card QR donate.
  - Có thể gửi kèm ảnh rồi dùng `{prefix}donate config decor`; dùng `off` để về mặc định.
- `{prefix}donate top`
  - Xem bảng xếp hạng donate tháng hiện tại.
- `{prefix}donate reset`
  - Quyền `cash`: gửi bảng hiện tại vào DM admin rồi reset bảng tháng về trống.
  - Không trừ cash và không xóa tổng donate tích lũy của user.
- `/donate [amount] [method] [message]`
  - Chọn Bank/QR hoặc Cash; bỏ trống amount để mở biểu mẫu.
- `{prefix}topusers [limit]`
  - Xem top user theo points.

## Bot

- `{prefix}join`
  - Bot vào voice channel hiện tại của bạn.
  - Alias: `{prefix}j`.
  - Người gọi `join` sẽ là người giữ quyền `play l/leave`.
- `{prefix}say <nội dung>`
  - Bot vào voice và đọc nội dung bằng giọng Google.
  - Alias: `{prefix}s <nội dung>`.
  - Nếu bot chưa ở voice, người gọi `say` sẽ là người giữ quyền `play l/leave`.
  - Sau khi không dùng trong 5 phút, bot tự rời voice.
- `{prefix}leave`
  - Bot rời voice ngay nếu bạn là người đã mời bot vào.
  - Alias: `{prefix}l`, `{prefix}disconnect`, `{prefix}dc`.
- `{prefix}play <url|từ khóa|playlist>`
  - Phát nhạc từ YouTube, YouTube Music, SoundCloud, MixCloud hoặc playlist qua `yt-dlp`.
  - Alias: `{prefix}p <url|từ khóa|playlist>` hoặc `{prefix}a <url|từ khóa|playlist>`.
  - Khi đang phát, bài mới thêm vào queue sẽ có thông báo tên bài, vị trí và số lượng.
  - Spotify URL sẽ được thử qua extractor; nếu link không chạy, gửi tên bài hoặc link YouTube/YT Music tương ứng.
  - Nếu bot chưa ở voice, người gọi `play` sẽ là người giữ quyền `play l/leave`.
  - Player hoạt động trong cả text channel và phần chat của voice channel.
  - Player cũ tự xóa và card mới được gửi xuống cuối chat khi thao tác hoặc chuyển bài.
  - Nhạc bắt đầu ngay khi nguồn phát sẵn sàng; card được render ở background và có thể xuất hiện sau.
  - Card là ảnh đính kèm trực tiếp, không dùng embed.
  - Thanh thời gian chạy trong GIF và được đồng bộ lại từ playback clock mỗi 30 giây.
  - Không còn dòng `Bắt đầu ... / kết thúc ...` bên ngoài ảnh.
  - Nút player vẫn hoạt động sau khi reload cog.
  - Thời gian bắt đầu/kết thúc dùng timestamp động của Discord.
- `{prefix}play q`
  - Xem queue.
  - Có thể dùng `{prefix}play queue`.
- `{prefix}play sh`
  - Shuffle queue.
  - Có thể dùng `{prefix}play shuffle` hoặc `{prefix}play sf`.
- `{prefix}play a`
  - Bật/tắt autoplay.
  - Có thể dùng `{prefix}play autoplay on/off`.
  - Autoplay lấy radio đề xuất theo chủ đề của YouTube, không tự ưu tiên cùng tác giả.
- `{prefix}play s`
  - Bỏ qua bài hiện tại.
  - Có thể dùng `{prefix}play skip`.
- `{prefix}play pause`
  - Tạm dừng bài đang phát.
  - Có thể dùng `{prefix}play p`.
- `{prefix}play resume`
  - Tiếp tục phát.
  - Có thể dùng `{prefix}play r`.
- `{prefix}play stop`
  - Dừng phát và xóa queue, bot vẫn ngồi voice và tự out sau 5 phút nếu không dùng.
  - Có thể dùng `{prefix}play st`.
- `{prefix}play l`
  - Bot rời voice ngay.
  - Có thể dùng `{prefix}play leave`.
  - Chỉ người đã mời bot vào voice bằng `join`, `say` hoặc `play` mới được dùng.
- `{prefix}play n`
  - Xem bài đang phát.
  - Có thể dùng `{prefix}play now`.
- `{prefix}play lo`
  - Bật/tắt loop bài hiện tại.
  - Có thể dùng `{prefix}play loop`.
- `{prefix}play v <0-200>`
  - Set volume.
  - Có thể dùng `{prefix}play vol <0-200>`.
  - Volume được lưu riêng cho đúng người vừa chỉnh; người khác chỉnh không ghi đè dữ liệu của bạn.
  - Mức mới có hiệu lực ngay cho phiên đang phát và toàn bộ queue hiện tại.
  - Khi bắt đầu phiên phát mới, bot tự nạp volume đã lưu của người mở phiên đó.
  - Autoplay và loop không được lưu.
- `{prefix}play rm <số>`
  - Xóa một bài khỏi queue theo số thứ tự.
- `{prefix}play c`
  - Xóa toàn bộ queue.
  - Có thể dùng `{prefix}play clear`.
- `{prefix}play settings`
  - Mở menu tùy chỉnh giao diện, nội dung card/message, nhãn nút, icon và reaction theo server.
  - Thông báo thêm queue hỗ trợ `{title}`, `{position}`, `{count}`, `{requester}`.
  - Mỗi lựa chọn có ví dụ; nhập `reset` để trả riêng mục đó về mặc định.
  - Chỉ bot admin hoặc role có quyền `play settings`.
  - Cấu hình player được lưu theo server; autoplay và loop vẫn chỉ áp dụng cho phiên hiện tại.

## Booking

- `{prefix}luong`
  - Xem bảng tính lương của bạn ngay tại kênh hiện tại.
- `{prefix}luong @user`
  - Xem bảng tính lương của user khác tại kênh hiện tại.
  - Quyền: admin bot hoặc role có quyền `luong`/`tinhluong`.
- `{prefix}luong all`
  - Xem tất cả bảng lương.
  - Quyền: admin bot hoặc role có quyền `luong`/`tinhluong`.
- `{prefix}luong a @user <money>`
  - Cộng lương cho booking.
- `{prefix}luong add @user <money>`
  - Cách viết đầy đủ của cộng lương.
- `{prefix}luong r @user <money>`
  - Trừ lương của booking.
  - Có thể dùng `{prefix}luong remove @user <money>`, `{prefix}luong rm @user <money>`, `{prefix}luong d @user <money>` hoặc `{prefix}luong delete @user <money>`.
- `{prefix}luong e @user <money>`
  - Set lương của booking về số mới.
  - Có thể dùng `{prefix}luong edit @user <money>`.
  - User phải có role hệ thống `booking`.
- `{prefix}star`
  - Xem giờ đã book và số tiền đã tiêu của bạn.
- `{prefix}star @user`
  - Admin/role DB xem booking của user khác.
- `{prefix}star all`
  - Xem tất cả star trong database.
  - Quyền: admin bot hoặc role có quyền `star`.
- `{prefix}star a @user <amount>`
  - Cộng star cho user.
- `{prefix}star add @user <amount>`
  - Cách viết đầy đủ của cộng star.
- `{prefix}star r @user <amount>`
  - Trừ star của user.
  - Có thể dùng `{prefix}star remove @user <amount>`, `{prefix}star rm @user <amount>`, `{prefix}star d @user <amount>` hoặc `{prefix}star delete @user <amount>`.
- `{prefix}star e @user <amount>`
  - Set star của user về số mới.
  - Có thể dùng `{prefix}star edit @user <amount>`.
- `{prefix}star time <hours> [@user]`
  - Ghi nhận giờ book.
  - Admin/role DB có thể ghi cho người khác.
- `{prefix}star money <money> [@user]`
  - Ghi nhận tiền nạp.
  - Admin/role DB có thể ghi cho người khác.
- `{prefix}star top`
  - Xem top giờ book và top nạp.
- `{prefix}tinhluong`
  - Gửi bảng tính lương của bạn qua DM.
  - Chỉ hiện những mốc giờ đã có dữ liệu.
- `{prefix}tinhluong @user`
  - Admin/role DB gửi bảng tính lương của user qua DM.
- `{prefix}tinhluong all`
  - Admin/role DB gửi/tính bảng lương toàn bộ booking.
- `{prefix}topbook [limit]`
  - Top giờ được book nhiều nhất.
  - Quyền: admin hoặc role DB.
- `{prefix}topnap [limit]`
  - Top người nạp tiền nhiều nhất.
  - Quyền: admin hoặc role DB.
- `{prefix}topgift`
  - Xem tổng quà đang có.

## Role Management

- `{prefix}addrole @role1, @role2 command1, command2`
  - Cấp quyền dùng command cho 1 hoặc nhiều role.
  - Có thể dùng cú pháp cũ `{prefix}addrole @role <command>` nếu chỉ có 1 role và 1 lệnh.
  - Command nào tồn tại trong bot/cog thì được lưu quyền, command không tồn tại sẽ được báo riêng.
  - Alias: `{prefix}themrole`.
- `{prefix}removerole @role1, @role2 command1, command2`
  - Xóa quyền dùng command khỏi 1 hoặc nhiều role.
  - Có thể dùng cú pháp cũ `{prefix}removerole @role <command>` nếu chỉ có 1 role và 1 lệnh.
  - Command nào tồn tại trong bot/cog thì được xử lý, command không tồn tại sẽ được báo riêng.
  - Alias: `{prefix}rmrole`, `{prefix}xoarole`.
- `{prefix}setrole @role`
  - Mở menu chọn role hệ thống cho role đó.
  - Các lựa chọn: `admin`, `booking`, `user`, `staff`.
- `{prefix}setrole @role booking`
  - Set nhanh role hệ thống nếu không muốn dùng menu.
- `{prefix}perms command1, command2`
  - Xem role nào đang có quyền dùng 1 hoặc nhiều command.
  - Command không tồn tại sẽ hiện trong mục riêng.
- `{prefix}myroles [@user]`
  - Xem role của bạn hoặc user khác.
- `{prefix}rolescommands @role`
  - Xem role đang dùng được những command nào.

## Administrator

- `{prefix}lock [#channel]`
  - Không nhập channel: khóa chat tại channel đang dùng lệnh.
  - Có `#channel`: khóa channel được chỉ định.
  - Quyền: bot admin hoặc role có quyền `lock` trong database.
- `{prefix}unlock [#channel]`
  - Không nhập channel: mở khóa channel đang dùng lệnh.
  - Có `#channel`: mở khóa channel được chỉ định.
  - Quyền: bot admin hoặc role có quyền `unlock` trong database.

### Bot admin

- `{prefix}addadmin @user`
  - Thêm admin bot trong server hiện tại.
  - Trong DM dùng `{prefix}addadmin <user_id> <server_id>`.
  - Alias: `{prefix}themadmin`.
- `{prefix}rmadmin @user`
  - Xóa admin bot khỏi server hiện tại.
  - Trong DM dùng `{prefix}rmadmin <user_id> <server_id>`.
  - Alias: `{prefix}xoaadmin`.
- `{prefix}addcashadmin @user`
  - Thêm quyền quản trị cash/naptien/donate trong server hiện tại.
  - Trong DM dùng `{prefix}addcashadmin <user_id> <server_id>`.
  - Alias: `{prefix}themcashadmin`, `{prefix}cashadmin`.
- `{prefix}rmcashadmin @user`
  - Xóa quyền quản trị cash/naptien/donate trong server hiện tại.
  - Trong DM dùng `{prefix}rmcashadmin <user_id> <server_id>`.
  - Alias: `{prefix}xoacashadmin`.

### Bật/tắt command theo channel

- `{prefix}disable <command>`
  - Khóa command trong channel hiện tại, ví dụ `{prefix}disable ga` hoặc `{prefix}disable level setup`.
- `{prefix}enable <command>`
  - Bật lại command trong channel hiện tại.
- `{prefix}command disable|enable <command>`
  - Cú pháp tổng, alias `{prefix}cmd`.
- `/command action:<enable|disable> command:<tên_lệnh>`
  - Slash command quản lý khóa lệnh theo channel.
  - Hard admin bỏ qua khóa; listener nền như log và level tracking vẫn hoạt động.

### Giveaway

- `{prefix}ga <time> <winners> <reward> [quantity]`
  - Tạo một hoặc nhiều giveaway.
- `{prefix}ga config`
  - Mở menu sửa emoji tham gia, tiêu đề, nội dung kết quả, nhãn và icon theo server.
  - Mỗi lựa chọn có ví dụ và danh sách biến hỗ trợ; nhập `reset` để trả riêng mục đó về mặc định.
- `{prefix}ga config emoji <emoji>`
  - Đổi nhanh emoji tham gia; cú pháp config trực tiếp cũ vẫn được hỗ trợ.
- `/giveaway action:config`
  - Mở cùng menu cấu hình bằng slash command.

### Steal emoji

- `{prefix}steal <custom emoji> [name]`
  - Sao chép custom emoji tĩnh hoặc động; bỏ trống `name` để giữ tên gốc.
- `{prefix}steal <URL ảnh> <name>`
  - Tạo emoji từ URL PNG, JPG, GIF hoặc WEBP.
- Đính kèm ảnh rồi dùng `{prefix}steal <name>`.
- `/steal emoji:<custom emoji|URL> [name]`
  - Bản slash, kết quả chỉ người dùng lệnh nhìn thấy.
- Quyền: bot admin hoặc role có permission key `steal`.

```text
{prefix}addrole @role steal
```

### Economy

- `{prefix}rate`
  - Xem tỷ giá đang dùng giữa cash VND của bot tổng và OWO của casino.
  - Chỉ bot admin được dùng.
- `{prefix}rate cash <hệ số> owo <hệ số>`
  - Đặt tỷ giá mới, ví dụ `{prefix}rate cash 1 owo 1` tương ứng `1.000 VND = 1.000.000 OWO`.
  - Hỗ trợ số thập phân bằng dấu chấm hoặc dấu phẩy, ví dụ `{prefix}rate cash 1 owo 0,5`.
  - Khi đổi tỷ giá, OWO giữ nguyên; bot chỉ quy đổi lại cash và cập nhật mốc đồng bộ.
- `{prefix}cash a|r|e @user <money>`
  - Quản trị cash theo action add/remove/edit.
  - Cash âm do casino đồng bộ được giữ làm khoản nợ; nạp/cộng cash có thể bù dần về 0.
- `{prefix}luong a|r|e @user <money>`
  - Quản trị lương booking theo action add/remove/edit.
- `{prefix}star a|r|e @user <amount>`
  - Quản trị star theo action add/remove/edit.
- `{prefix}points a|r|e @user <amount>`
  - Quản trị points theo action add/remove/edit.
- `{prefix}time a|r|e @user <hours>`
  - Quản trị tổng giờ theo action add/remove/edit.
  - Với các lệnh action, `r` có thể viết `rm`, `remove`, `d` hoặc `delete`.
- `{prefix}tongluong`
  - Xem tổng lương.
- `{prefix}topstar [limit]`
  - Top star.
- `{prefix}addtime @user <hours>`
  - Cộng giờ kiểu cũ.
- `{prefix}addtime a|r|e @user <hours>`
  - Cộng/trừ/set giờ bằng action.
- `{prefix}subtime @user <hours>`
  - Trừ giờ.
- `{prefix}addpoints @user <amount>`
  - Cộng points kiểu cũ.
- `{prefix}addpoints a|r|e @user <amount>`
  - Cộng/trừ/set points bằng action.

### Booking config

- `{prefix}bookconfig`
  - Xem giá booking và phần trăm trả tiền.
  - Alias: `{prefix}bookingconfig`, `{prefix}giabook`.
- `{prefix}setgiobook <money>`
  - Đặt giá tiền cho 1 giờ booking.
  - Alias: `{prefix}setgia`, `{prefix}giabooking`.
- `{prefix}setphantram <percent>`
  - Đặt phần trăm trả tiền cho booking.
  - Alias: `{prefix}setpayout`, `{prefix}settraluong`.
- `{prefix}setan <percent>`
  - Đặt phần trăm bot/server ăn.
  - Alias: `{prefix}setfee`, `{prefix}sethoahong`.

### Responsive profile và auto response

- `{prefix}form [key]`
  - Gửi form booking để user tự điền.
  - Có thể dùng dạng dính liền như `{prefix}formau`.
- `{prefix}ar a <res> | <content>`
  - Thêm auto response.
- `{prefix}ar a <profile_key><number>`
  - Tạo profile, số `0` dùng được.
  - Ví dụ: `{prefix}ar a ad0`.
- `{prefix}ar des <res> | <content>`
  - Sửa nội dung auto response.
- `{prefix}ar description <profile_key><number>`
  - Lấy nội dung profile từ tin nhắn reply.
- `{prefix}ar target <res|profile> @user`
  - Gắn target cho auto res hoặc profile.
- `{prefix}ar iurl <res|profile> <url|ảnh>`
  - Set ảnh lớn.
- `{prefix}ar turl <res|profile> <url|ảnh>`
  - Set ảnh nhỏ/thumbnail, bot tự crop vuông.
- `{prefix}ar r <res|profile>`
  - Xóa auto res hoặc profile.
  - Có thể dùng `{prefix}ar remove <res|profile>` hoặc `{prefix}ar rm <res|profile>`.
- `{prefix}res <key>`
  - Gọi auto response theo key.
- `{prefix}up <profile_key><number> #channel`
  - Up profile lên channel chỉ định.

Placeholder auto response:

- `{user}`: người gọi lệnh.
- `{key}`: key trigger.
- `{target}`: user đã gắn target nếu có.

### Moderation và server

- `{prefix}ban @user|username|id [time] [reason]`
  - Ban user vĩnh viễn hoặc tạm thời.
  - Time hỗ trợ `s`, `m`, `h`, `d`; ví dụ `{prefix}ban @user 1d spam`.
- `{prefix}unban <user_id> [reason]`
  - Gỡ ban.
- `{prefix}kick @user|username|id [reason]`
  - Kick member khỏi server.
- `{prefix}role a @user @role`
  - Cấp Discord role cho user.
- `{prefix}role r @user @role`
  - Gỡ Discord role khỏi user.
  - Có thể dùng: `{prefix}role remove @user @role` hoặc `{prefix}role rm @user @role`.
  - Bot cần quyền `Manage Roles` và role cần cấp/gỡ phải thấp hơn role cao nhất của bot.
- `{prefix}mute @user|username|id [duration] [reason]`
  - Mute member.
- `{prefix}unmute @user|username|id [reason]`
  - Gỡ mute.
- `{prefix}color @role <hex|name>`
  - Đổi màu role.
- `{prefix}emoji ...`
  - Quản lý emoji.
- `/antiraid`
  - Bật/tắt chống raid trong server.

### Log system

- `{prefix}log chat #channel`
  - Gửi log xóa/sửa tin nhắn của toàn server về channel đã chọn.
- `{prefix}log voice #channel`
  - Gửi log vào/rời/chuyển voice của toàn server.
- `{prefix}log server #channel`
  - Gửi log thay đổi server, role, avatar/user update và cấu hình server.
- `{prefix}log join #channel`
  - Gửi log member join/leave server.
- `{prefix}log cash #channel`
  - Gửi log nạp tiền, donate, give, cộng/trừ/set cash.
- `{prefix}log <loại> off`
  - Tắt một loại log.
- `{prefix}log voice announce <message|off>`
  - Tuỳ chỉnh thông báo khi user vào/rời voice channel.

### Ticket

- `{prefix}ticket`
  - Xem hướng dẫn nhanh hệ thống Ticket.
- `{prefix}ticket manager` hoặc `{prefix}ticket config`
  - Mở bảng cấu hình Ticket.
  - Menu **Tag theo mục** cấu hình role/user được ping riêng cho từng loại Ticket.
  - Có thể chọn role, chọn user hoặc nhập trực tiếp role ID/user ID.
  - Role/user của mục được cấp quyền xem kênh và được tag khi Ticket tương ứng được tạo.
  - Menu **Nội dung** sửa tiêu đề, mô tả, lời nhắc, tên loại Ticket và nhãn nút.
  - Menu **Icon** sửa icon panel, loại Ticket và các nút điều khiển.
  - Mỗi ô nhập có ví dụ; nhập `reset` để trả riêng mục đó về mặc định.
  - Quyền: bot admin hoặc role có quyền `ticket` trong `command_role.db`.
- `{prefix}ticket panel`
  - Gửi mới hoặc refresh panel mở Ticket.
  - Quyền: bot admin hoặc role có quyền `ticket`.
- `{prefix}ticket add @user`
  - Thêm user vào Ticket hiện tại.
- `{prefix}ticket remove @user`
  - Xóa user khỏi Ticket hiện tại.
  - Alias subcommand: `rm`.
- `{prefix}ticket rename <tên>`
  - Đổi tên kênh Ticket.
- `{prefix}ticket transfer @user`
  - Chuyển người nhận Ticket.
- `{prefix}ticket unclaim`
  - Gỡ người đang nhận Ticket.
- `{prefix}ticket info`
  - Xem thông tin Ticket hiện tại.
- `{prefix}ticket close [lý do]`
  - Đóng Ticket, tạo transcript và archive/xóa theo cấu hình.
- `/ticket manager`
  - Mở giao diện quản lý Ticket.
- `/ticket info`
  - Xem Ticket hiện tại.
- `/ticket close [reason]`
  - Đóng Ticket hiện tại.

Các thao tác manager, panel, claim, thêm/xóa user, rename, transfer và unclaim dùng chung key quyền `ticket`. Cấp quyền bằng:

```text
{prefix}addrole @role ticket
```

### Operator

- `{prefix}gitpull`
  - Đồng bộ code VPS với `origin/main`, kể cả khi GitHub đã force-push viết lại lịch sử.
  - Nếu lịch sử phân kỳ, bot tự tạo branch `backup/gitpull-...` giữ commit cũ rồi cập nhật VPS.
  - Tự bỏ qua database, log và cache runtime; nếu có file code chưa commit, bot dừng lại để không ghi đè.
  - Alias: `{prefix}pull`, `{prefix}update`.
- `{prefix}gitstatus`
  - Xem trạng thái git.
  - Alias: `{prefix}status`.
- `{prefix}reload [catalog|module]`
  - Hỗ trợ tên ngắn, ví dụ `{prefix}reload ticket` sẽ reload `administrator.ticket_cog`.
  - Reload một cog, một catalog hoặc toàn bộ.
- `{prefix}load <catalog|module>`
  - Load một cog hoặc catalog.
- `{prefix}unload <catalog|module>`
  - Unload một cog hoặc catalog.
- `{prefix}cogs`
  - Liệt kê các cogs đang load.
- `{prefix}prefix <value>`
  - Đổi prefix bot.

## Định dạng tiền

Các lệnh tiền dùng VNĐ:

- `100000` -> `100,000 VNĐ`
- `100k` -> `100,000 VNĐ`
- `1m` -> `1,000,000 VNĐ`
- `1b` -> `1,000,000,000 VNĐ`
- `0,5m` -> `500,000 VNĐ`
- `100.000` hoặc `100,000` đều hợp lệ.

## Ghi nhớ nhanh

- Lệnh quản trị quan trọng nằm trong catalog Administrator.
- Lệnh dùng được bởi mọi người nằm trong User hoặc Booking tùy tính năng.
- Role permission dùng `addrole`/`removerole`.
- Role hệ thống dùng `setrole @role`, sau đó chọn `admin/booking/user/staff`.
- Database tự tạo khi bot chạy, không cần commit file `.db`.
