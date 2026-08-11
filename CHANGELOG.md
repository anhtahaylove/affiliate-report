# Changelog

## v1.3.3 - 2026-08-11

**Khi app đã đóng, màn hình không còn hiện "Failed to fetch".** Nếu bạn chọn Thoát ứng dụng từ biểu tượng khay hệ thống mà vẫn còn tab trình duyệt đang mở, tab đó mất kết nối và trước đây hiện đúng dòng chữ tiếng Anh của trình duyệt, không nói được phải làm gì. Giờ nó nói thẳng: hãy mở lại TikTok Affiliate Report từ Desktop hoặc Start Menu rồi tải lại trang.

**Chờ app mở lại sau khi cập nhật lâu hơn trước khi báo lỗi.** Đo trên máy thật: mở app ngay sau khi cài mất 2-4 giây, nhưng mở nguội (máy nghỉ lâu, phần mềm diệt virus quét lại gần 1.800 file) có lần mất tới 35 giây. Ngưỡng cũ 45 giây quá sát con số đó nên máy chậm hơn một chút là bị báo nhầm "chưa tự mở lại được" dù app vẫn đang khởi động bình thường. Nâng lên 90 giây; chờ lâu không còn gây hại gì kể từ khi bỏ việc mở app lần thứ hai ở v1.3.2.

## v1.3.2 - 2026-08-11

**Sửa lỗi cập nhật báo "Failed to load Python DLL".** Sau khi cài xong bản mới, app không tự mở lại được và hiện hộp lỗi đỏ về `python312.dll`. Nguyên nhân: mỗi lần chạy, app phải tự bung toàn bộ 59 MB thư viện Python ra thư mục tạm của Windows. Ngay sau khi cài, file vừa ghi xuống đĩa còn đang bị phần mềm diệt virus quét, nên bước bung này hỏng giữa chừng. Tệ hơn, khi chờ quá lâu app lại được mở thêm lần thứ hai, hai lần bung chạy song song tranh nhau ổ đĩa và làm hỏng chắc chắn hơn.

Từ bản này, thư viện Python nằm sẵn cạnh file chạy và được cài một lần lúc cài đặt, app không bung gì nữa khi mở. Đo trên máy: **mở app mất 2,4 giây** thay vì 12–60 giây ở lần đầu sau cập nhật, và không còn để lại rác trong thư mục tạm. App cũng chỉ còn một tiến trình thay vì hai — trước đây tắt app đôi khi chỉ tắt được một nửa, khiến lần cài đè sau đó báo lỗi "Installer exited with code 5".

Nếu app vẫn không tự mở lại được, phần cập nhật giờ nói thẳng "đã cài xong nhưng chưa tự mở lại được, hãy mở từ Desktop" thay vì báo thành công rồi im lặng.

**Xoá dữ liệu xong thì file cũng nhỏ lại.** Trước đây bấm Xoá dữ liệu hay Khôi phục xong, file database vẫn giữ nguyên kích thước cũ vì chỗ trống không được thu hồi — có máy còn 25 MB trong khi bên trong không còn dòng nào. Giờ hệ thống tự thu gọn ngay sau đó và báo đã giải phóng bao nhiêu.

## v1.3.1 - 2026-08-11

Không có thay đổi tính năng so với v1.3.0 — toàn bộ nội dung bên dưới vẫn là của bản này. Bản v1.3.0 không phát hành được: bước kiểm tra bảo mật phụ thuộc khi dựng bản cài báo một lỗ hổng trong `nanoid`, một thư viện đi kèm công cụ dựng giao diện. Đã ghim lên bản đã vá rồi dựng lại; lỗ hổng đó nằm ở khâu dựng ứng dụng, không nằm trong bản chạy trên máy bạn.

## v1.3.0 - 2026-08-11

**Nhập dữ liệu không còn mất trắng vì một dòng hỏng.** Trước đây chỉ cần một dòng có ngày sai định dạng hoặc thiếu ID SKU là cả file bị từ chối, dù 5.000 dòng còn lại hoàn toàn bình thường. Giờ app chỉ loại đúng dòng đọc không được, báo rõ dòng số mấy và sai ở đâu, phần còn lại vẫn vào bình thường. Cùng lý do đó, file chỉ cần có đủ 47 cột TikTok là nhập được — thứ tự cột không còn quan trọng và cột lạ TikTok thêm về sau chỉ bị bỏ qua chứ không làm hỏng cả lần nhập.

**Hoàn tác được một lần nhập.** Nhập nhầm file vào sai tài khoản là chuyện sẽ xảy ra, mà trước đây cách duy nhất để sửa là xoá sạch dữ liệu báo cáo hoặc xoá cả tài khoản. Giờ trong **Nhập dữ liệu** mỗi lần nhập có nút **Hoàn tác lần nhập này**: app cho xem trước sẽ gỡ bao nhiêu dòng, bao nhiêu dòng quay về phiên bản trước, bắt gõ cụm xác nhận rồi mới làm, và tự sao lưu trước khi động vào dữ liệu. Nếu lần nhập đó không phải lần mới nhất, app nói rõ điều này thay vì lặng lẽ làm sai số liệu hiện tại.

**Xem được lịch sử của từng dòng đơn.** App vẫn luôn lưu mọi phiên bản của mỗi dòng đơn qua các lần nhập, nhưng chưa có chỗ nào xem. Giờ mở **Chi tiết** một đơn trong bảng Đơn hàng sẽ thấy dòng đó đã đổi gì, ở lần nhập nào và lúc nào.

**App không còn đứng hình trong lúc nhập file lớn.** Trước đây suốt thời gian nhập, mọi thứ khác đều phải chờ — tab khác không tải được, biểu tượng tray không phản hồi. Giờ việc nhập chạy nền, phần còn lại của app vẫn dùng được. Nhập nhanh hơn khoảng 7 lần (5.000 dòng: 4,1 giây xuống 0,5 giây) và mở dashboard nhanh hơn khoảng 3 lần (1,4 giây xuống 0,5 giây), do app không còn kéo toàn bộ dữ liệu thô lên mỗi lần xem báo cáo.

**Chế độ tối.** Có nút chuyển ở góc trên bên phải với ba lựa chọn: theo hệ thống, sáng, tối. Lựa chọn được nhớ cho lần mở sau.

**Giao diện gọn lại và làm được nhiều việc hơn:**

- Dashboard giữ 4 chỉ số chính ở trên, các chỉ số phụ dồn xuống một dải nhỏ bên dưới thay vì bảy thẻ ngang hàng nhau.
- Máy mới cài, chưa nhập gì thì Dashboard chỉ ba bước cần làm thay vì hiện một dàn thẻ 0 đồng.
- Bảng Đơn hàng sắp xếp được bằng cách bấm tên cột và chọn được 50/100/200 dòng mỗi trang; lựa chọn nằm trong địa chỉ trang nên copy link gửi đi vẫn giữ nguyên.
- Bộ lọc thêm nút bấm nhanh: 7 ngày qua, 30 ngày qua, tháng này, tháng trước.
- Nhập nhiều file cùng lúc giờ hiện kết quả riêng từng file kèm trạng thái, thay vì nối tất cả thành một dòng chữ dài.
- Các thao tác nguy hiểm (xoá dữ liệu, khôi phục, xoá tài khoản, hoàn tác, thoát app, cài cập nhật) dùng chung một hộp xác nhận trong app, gộp phần xem trước ảnh hưởng và ô gõ cụm xác nhận vào một chỗ.
- Biểu đồ xu hướng không còn méo khi đổi kích thước cửa sổ, có thêm trục giá trị và lưới mờ để ước lượng.
- Tìm kiếm đơn hàng giờ tìm đúng cả khi gõ không dấu hoa-thường tiếng Việt (gõ "áo thun" ra "Áo Thun").

**Bên trong:** cột `target_commission` trong database được đổi tên thành `daily_target_commission` cho đúng nghĩa (nó luôn là KPI mỗi ngày, không phải tổng tháng) — database cũ tự động chuyển khi mở app, không cần làm gì. Test giao diện giờ chạy trong CI (trước đây có viết nhưng chưa bao giờ được chạy), và có thêm một kịch bản chạy thật qua trình duyệt cho luồng tạo tài khoản → nhập file → đọc số liệu → hoàn tác.

## v1.2.13 - 2026-08-05

- Tăng thời gian chờ app tự mở lại sau khi cài cập nhật (v1.2.12) từ 12 giây lên 60 giây trước khi thử mở lại lần nữa. Lý do: bản .exe vừa cài là file hoàn toàn mới trên đĩa — lần chạy đầu tiên phải giải nén lại runtime bên trong (chưa có cache), có thể chậm hơn hẳn các lần chạy sau tuỳ tải hệ thống lúc đó. Mở lại quá sớm khi lần đầu chỉ đang chậm (chứ không phải bị treo) sẽ tạo thêm 1 lần giải nén thứ hai chạy song song, tranh chấp đĩa và làm chậm thêm — nên ưu tiên chờ đủ lâu cho lần đầu trước khi thử lại.

## v1.2.12 - 2026-08-05

- Sửa lỗi app đôi khi không tự mở lại sau khi cài xong bản cập nhật (đứng ở "Đang chờ kết nối lại…" dù bản cài đã thành công). Nguyên nhân nghi vấn nhiều khả năng nhất: phần mềm diệt virus quét file .exe mới cài trước khi cho chạy, khiến bước tự mở lại app bị treo vài giây tới cả chục giây. Updater giờ chờ xác nhận app thật sự phản hồi (gọi `/health`) sau khi mở lại, và tự thử mở lại thêm 1 lần nếu chưa thấy phản hồi trong 12 giây, thay vì coi "đã gọi lệnh mở" là xong việc.
- Bản cập nhật (file cài đè, thay thế .exe) vẫn thành công như trước — đây chỉ là bước "mở lại app cho người dùng thấy" sau khi cài xong, không ảnh hưởng tới việc cài đặt có thành công hay không.

## v1.2.11 - 2026-08-05

- Thêm thẻ KPI mới trên Dashboard: **"Tiến độ gộp (kể cả Không đủ điều kiện)"** — hoa hồng ước tính của mọi đơn kể cả bị loại, hiện cạnh thẻ "Tiến độ mục tiêu" chính thức (không đổi, vẫn chỉ tính tiền thật sẽ nhận). Thẻ mới kèm dòng "mất X đ (Y%) do không đủ điều kiện" để thấy ngay đang hao hụt bao nhiêu doanh số.
- Đây là lớp xem bổ sung cho việc theo dõi sức bán, tách biệt hoàn toàn khỏi số liệu chính thức dùng để đánh giá đã đạt mục tiêu tháng hay chưa — tránh báo "đạt 100%" trong khi một phần tiền đó chắc chắn không về.

## v1.2.10 - 2026-08-05

- Trang Tài khoản chỉ còn một định danh — Mã tài khoản (đã bỏ "Tên hiển thị" riêng, dùng chung một giá trị duy nhất).
- Sửa lỗi hiển thị 0đ ở các đơn "Không đủ điều kiện": cột "Hoa hồng ước tính" trong bảng Đơn hàng và bảng "Theo trạng thái" trong Phân tích giờ hiện đúng số ước tính từ file gốc thay vì luôn là 0 (0đ vẫn đúng cho "Hoa hồng thực tế" tổng — đơn ineligible không tính vào tổng thực nhận, nhưng số ước tính của từng đơn không được phép biến mất khỏi màn hình).
- Thêm cột "Số món bán ra" vào bảng Đơn hàng và bảng So sánh hiệu suất (Dashboard), khớp với chỉ số REPORT_AFF.xlsx người dùng đang theo dõi thủ công.
- Bộ lọc Tài khoản/Trạng thái giờ giới hạn chiều cao ~3 hàng và cuộn nội bộ khi có nhiều lựa chọn, không còn đẩy cả trang xuống dài dằng dặc.

## v1.2.9 - 2026-08-05

- Không có thay đổi tính năng. Bản này chỉ để xác nhận thật bản vá "Installer exited with code 5" ở v1.2.8: cài v1.2.8 trực tiếp (không qua auto-update, do máy đang mắc kẹt ở bản lỗi cũ), rồi từ đó bấm cập nhật thật lên v1.2.9 qua đúng luồng trong app để chứng minh `Wait-FileUnlocked` hoạt động khi bên thực hiện cập nhật đã có bản vá.

## v1.2.8 - 2026-08-05

- Sửa lỗi cập nhật thất bại với "Installer exited with code 5" (Setup tự huỷ vì cho rằng ứng dụng còn đang chạy). Nguyên nhân: bước tự đóng app trước khi cài chỉ theo dõi đúng 1 tiến trình con, trong khi tiến trình cha của gói .exe onefile có thể còn giữ file .exe thêm vài trăm mili-giây để dọn dẹp thư mục tạm — installer chạy `/CLOSEAPPLICATIONS` đúng lúc đó, thấy file "đang bận" và Huỷ luôn vì chạy ở chế độ im lặng (không có hộp thoại để bấm Thử lại). Giờ updater chờ chắc chắn file .exe được nhả hoàn toàn (thử mở độc quyền, tối đa 15 giây) trước khi gọi installer, thay vì chỉ chờ đúng 1 tiến trình.

## v1.2.7 - 2026-08-05

- Chuẩn hoá màu tiến độ mục tiêu (Dashboard, So sánh hiệu suất, Mục tiêu) theo kiểu đèn giao thông: xanh khi đạt (≥100%), vàng khi còn 50–99%, đỏ khi dưới 50% — dùng lại đúng bộ màu trạng thái sẵn có của app, không thêm màu mới.
- Sửa hình dạng cột trong biểu đồ xu hướng Phân tích: bo góc trên, đáy phẳng neo vào trục — thay vì bo tròn đều 4 góc trông lơ lửng, đồng bộ với biểu đồ cột ở Dashboard.

## v1.2.6 - 2026-08-04

- Sửa lỗi tự đóng ứng dụng để cài bản cập nhật có thể treo ở popup Windows "Failed to remove temporary directory" (cảnh báo gốc từ PyInstaller khi không xoá được thư mục tạm `_MEI...` do vẫn còn thư viện đang được nạp). App giờ thoát tiến trình ngay sau khi đã dọn dẹp xong (tắt tray, lưu trạng thái, nhả khoá single-instance) thay vì để trình bao bọc PyInstaller tự dọn dẹp và có thể treo — updater không còn bị timeout chờ app đóng.

## v1.2.5 - 2026-08-04

- Trang Tài khoản chỉ còn CRUD tài khoản (thêm/sửa/lưu trữ/xóa); bảng so sánh hiệu suất đã dời hẳn về Dashboard, không còn trùng lặp và không còn bộ lọc gây hiểu nhầm phạm vi ảnh hưởng.
- Rút gọn tóm tắt Analytics từ 6 xuống 3 chỉ số không lặp với Dashboard (so kỳ trước, tỷ lệ hoa hồng hiệu dụng, độ mới dữ liệu), nhường trọng tâm cho xu hướng và xếp hạng.
- Thêm dòng chú thích phạm vi ảnh hưởng ngay dưới bộ lọc ở từng trang (Tổng quan, Phân tích, Đơn hàng, Mục tiêu).
- Gộp 3 mục Dữ liệu/Cập nhật/Người dùng thành một mục **Cài đặt** trên sidebar, chuyển sang dạng tab trong trang; URL từng trang không đổi.
- Dashboard dùng biểu đồ cột thật cho nhịp 14 ngày gần nhất thay vì chỉ bảng số; dọn code chết (`ProgressList`) không còn được dùng ở đâu.

## v1.2.4 - 2026-08-04

- Sửa lỗi auto-update trên Windows: helper không còn bị chặn bởi `DETACHED_PROCESS`, chuyển sang API .NET để chờ tiến trình, tính SHA-256 và chạy installer thay vì phụ thuộc `Get-FileHash`.
- App chỉ đóng sau khi helper xác nhận khởi động thành công (handshake); tải installer bằng background worker để không treo API.
- Giao diện Cập nhật hiển thị tiến độ thật theo phase `downloading → verifying → waiting_for_exit → installing → restarting → installed/failed`, kèm số MB và phần trăm.
- Khi cài đặt thất bại, tự khởi động lại phiên bản hiện tại và hiển thị nguyên nhân để thử lại.

## v1.2.3 - 2026-08-04

- Thu gọn bộ lọc trên mobile, hiển thị tóm tắt phạm vi và giữ đầy đủ thao tác khi mở rộng.
- Cải thiện Dashboard với thanh phạm vi báo cáo và nút xuất báo cáo ngày riêng, rõ ràng hơn.
- Liên kết cảnh báo dữ liệu tới đúng đơn hàng/import liên quan và hiển thị chi tiết tối đa 10 dòng nhập bị từ chối.
- Chuẩn hoá smoke installer theo tham số phiên bản để kiểm tra cài mới và nâng cấp cho mọi release tiếp theo.

## v1.2.2 - 2026-08-04

- Việt hoá trạng thái dashboard/analytics/order: Đã quyết toán, Không đủ điều kiện, Đang chờ quyết toán và Chưa xác định.
- Mặc định bộ lọc Account/Trạng thái chọn tất cả; giữ URL gọn khi đang ở scope ALL.
- Nút **Đặt lại bộ lọc** áp dụng canonical query ngay lập tức, không cần refresh.
- Xác minh smoke test nâng cấp Windows giữ nguyên dữ liệu cũ và đủ 9 route desktop/mobile.

## v1.2.1 - 2026-08-04

- Nâng GitHub Actions lên các major chạy Node.js 24 để loại cảnh báo Node.js 20 trong CI/release.
- Thêm smoke test installer trên Windows runner sạch cho cài mới v1.2.0 và nâng cấp v1.1.1 lên v1.2.0 có giữ dữ liệu.
- Khôi phục route **Settings → Data** từng bị rule `.gitignore` loại nhầm khỏi installer v1.2.0.
- Bổ sung hướng dẫn mở, chạy và xử lý lỗi app local cho người dùng cuối.
- Thêm system tray với hành động mở dashboard và thoát ứng dụng; web app cũng có nút **Thoát ứng dụng** chỉ hiện trong bản Windows local.
- Chặn chạy trùng bằng Windows named mutex; mở shortcut lần nữa sẽ mở lại dashboard của instance đang chạy.
- Nâng PostCSS lên 8.5.25 để vá cảnh báo bảo mật GHSA-fxqj-rqcc-2cmp.

## v1.2.0 - 2026-08-03

- Auto-update chuyển sang public signed feed `stable.json` + `stable.json.sig`, không cần token ở máy người dùng.
- App ghim Ed25519 `key_id`, chặn manifest sai chữ ký, downgrade, non-HTTPS, sai tên installer, sai kích thước hoặc sai SHA-256.
- Release workflow tạo private release bốn asset rồi mirror installer, checksum và signed stable feed sang `anhtahaylove/tiktok-affiliate-report-updates`.

## v1.1.1 - 2026-08-03

- Owner-only Reset Data yêu cầu xác nhận rõ ràng và tự động tạo/kiểm tra backup SQLite trước khi xoá lịch sử.
- Owner có thể xem trước backup, khôi phục riêng dữ liệu báo cáo và hệ thống tự tạo safety backup trước khi restore; user/session hiện tại được giữ nguyên.
- Dashboard tự kiểm tra GitHub Release mới nhất; bản Windows đã cài có thể tải, xác minh GitHub asset digest + `SHA256SUMS.txt`, đóng app, chạy installer qua helper và khởi động lại.
- Tag release tự build/test installer Windows, phát hành đúng hai asset và tải lại để kiểm tra SHA-256 trước khi publish.
- Local installer tiếp tục là chế độ mặc định; shared OIDC/PostgreSQL/domain/HTTPS hoàn toàn tùy chọn.

## v1.1.0 - 2026-08-03

- Operations Cockpit Next.js thay hoàn toàn Streamlit trong local runtime và Windows packaging.
- Editable KPI/ngày theo từng account; owner có thêm target tổng `ALL`.
- Dashboard responsive gồm filter, KPI tháng, daily/account performance, upload và import history.
- Windows EXE phục vụ static Next.js qua FastAPI trên cổng loopback tự chọn; máy người dùng không cần Python/Node/Docker.
- Gate B: OIDC Authorization Code + PKCE, server-side session/CSRF và role/account authorization.
- PostgreSQL shared database support, SQLite → PostgreSQL migration tool và Postgres 16 CI.
- PWA login/logout flow; viewer read-only, operator bị giới hạn account, `ALL` chỉ owner chỉnh sửa.
- Windows packaging mặc định unsigned; SHA-256 là integrity gate miễn phí.
- Chỉ phát hành full installer; portable EXE không còn là release artifact.
- Reinstall/upgrade giữ nguyên database và lịch sử người dùng theo installer contract.

## v1.0.0 - 2026-08-03

- Local Streamlit dashboard và Windows EXE/installer không cần Python.
- Import TikTok `.xlsx`, chống import trùng và version hóa order line overlap.
- Dashboard overview, daily, monthly KPI, orders và import history theo `REPORT AFF.xlsx`.
- Installer cài theo user, tạo Desktop shortcut và giữ nguyên database khi nâng cấp.
- Privacy gate chặn database người dùng bị nhúng vào EXE phát hành.
- Phase 2 foundation: FastAPI `/api/v1` và Next.js PWA responsive.

### Windows status

Artifact có thể unsigned/self-signed và Windows SmartScreen có thể cảnh báo. Private release kèm `SHA256SUMS.txt` để kiểm tra integrity.
