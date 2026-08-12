# Changelog

## v2.0.12 - 2026-08-13

**Tổng quan gọn lại một phần ba.** Những khối gần như luôn im lặng giờ co lại còn một dòng có số tóm tắt, bấm vào là mở ra đầy đủ như cũ:

- **Trung tâm hành động** khi không có cảnh báo nào
- **Dòng tiền đối soát** khi không còn dòng chờ
- **Độ tin cậy dữ liệu** khi cả bốn chỉ số cảnh báo bằng 0
- **Đóng góp theo tài khoản** khi bạn chỉ có một tài khoản — biểu đồ một thanh chỉ nói được "100%"

**Nhắc thiết lập không còn chiếm cả khung.** Khi ứng dụng đã chạy được và chỉ sót một bước chưa làm, trước đây vẫn hiện đủ ba bước giữa trang, trong đó hai bước chỉ để khoe dấu "Hoàn tất". Giờ còn một dòng nhắc đúng việc chưa xong. Lần đầu dùng thật thì vẫn hiện đủ ba bước như cũ.

**Biểu đồ xu hướng dùng hết chiều ngang** thay vì bỏ trống hơn một phần ba khung bên phải.

Đo trên cùng dữ liệu: trang Tổng quan cao **3.308 điểm ảnh xuống còn 2.166**, giảm 35%. Không thông tin nào bị xoá, không khối nào đổi chỗ, màu sắc giữ nguyên.

**Bên trong:** nguồn cập nhật hoàn tất chuyển về kho mã nguồn chính — từ bản này, thông tin bản mới được ghi thẳng ở đó.

## v2.0.11 - 2026-08-13

**Nguồn cập nhật chuyển về kho mã nguồn chính.** Trước đây ứng dụng đọc thông tin bản mới từ một kho lưu trữ riêng; nay kho mã nguồn đã công khai nên gộp về một chỗ, bớt một nơi phải trông coi.

Bản này là bước chuyển tiếp: nó vẫn được phát hành qua nguồn cũ để máy đang chạy 2.0.10 nhận được, nhưng bản thân nó đọc nguồn mới. Bạn không phải làm gì — bấm cập nhật như mọi lần.

Chữ ký Ed25519 và khoá xác thực **không đổi**, nên cách kiểm tra an toàn của bản cập nhật vẫn y như cũ.

## v2.0.10 - 2026-08-12

Bản v2.0.8 và v2.0.9 đều không phát hành được nên chưa từng tới máy nào. Toàn bộ nội dung của chúng nằm trong bản này.

Thay đổi duy nhất so với v2.0.9 nằm ở bộ kiểm thử nội bộ, không đụng tới ứng dụng: bài kiểm tra sau phát hành từng báo hỏng khi tiến trình cài đặt chưa kịp tự thoát, dù bản cập nhật đã cài xong và dữ liệu còn nguyên. Giờ nó chờ tối đa 30 giây thay vì kết luận ngay.

## v2.0.9 - 2026-08-12

Bản v2.0.8 không phát hành được nên chưa từng tới máy nào — toàn bộ nội dung của nó nằm trong bản này, cộng thêm hai bản sửa bên dưới.

**Sửa lỗi cập nhật thỉnh thoảng hỏng ngay từ đầu.** Cứ 5 lần cài thì khoảng 2 lần dừng lại với thông báo "Không thể hoàn tất cài đặt bản cập nhật", ngay trước khi bắt đầu tải gói. Nguyên nhân: ứng dụng ghi tệp trạng thái cập nhật bằng cách thay nguyên tệp, mà trên Windows thao tác này bị từ chối nếu đúng lúc đó có ai đang mở tệp để đọc — và chính màn hình tiến độ đang đọc tệp đó mỗi 0,75 giây. Giờ ứng dụng thử lại trong 2 giây thay vì bỏ cuộc ngay; nếu thật sự không ghi được thì vẫn báo lỗi như cũ.

Lỗi này có từ các bản trước, không phải mới xuất hiện.

**Kiểm thử sau phát hành chạy đúng cặp phiên bản.** Quy trình phát hành ghim cứng số phiên bản cũ nên bài kiểm tra tự động sau khi phát hành đi qua nhánh cài đặt cũ thay vì nhánh mới. Không có gì phát hiện ra điều đó. Giờ nó lấy số phiên bản từ đúng một nguồn và có kiểm tra chặn việc ghim cứng trở lại.

## v2.0.8 - 2026-08-12

> Canary: đây là bản đầu tiên được cài bằng **bootstrap độc lập đã ký** của v2.0.7. Bước v2.0.7 → v2.0.8 chứng minh end-to-end rằng logic cài đặt không còn sinh ra từ mã nguồn đang chạy.

**Mở ứng dụng là biết ngay có bản mới.** Trước đây chỉ trang **Cài đặt → Cập nhật** mới biết, nên bạn phải tự nhớ đi tìm. Giờ mọi trang đều hiện một dòng nhắc khi có bản mới, kèm hai lựa chọn: **Cập nhật ngay** hoặc **Để sau**.

**Cập nhật ngay** đưa thẳng tới hộp xác nhận, không phải tự tìm lại nút Cài. **Để sau** thì im hẳn cho tới khi có bản mới hơn nữa — không nhắc lại cùng một bản.

Ứng dụng chỉ hỏi nguồn cập nhật **một lần cho mỗi lần mở**; chuyển trang qua lại không gọi lại. Không có mạng thì dòng nhắc lặng lẽ không hiện, không chen ngang việc bạn đang làm.

**Cài xong thì giao diện tự tải lại.** Trước đây sau khi cài xong, tab trình duyệt vẫn đang chạy giao diện của bản cũ — mọi thay đổi của bản mới nằm im cho tới khi bạn tự bấm tải lại trang, mà không có gì nói cho bạn biết. Không API nào thay được phần giao diện đã tải; chỉ nạp lại trang mới làm được, và lúc đó ứng dụng vừa khởi động lại bên dưới nên cũng không còn gì để mất.

**Kết nối lại sau khi cài nhanh hơn khoảng 2–4,5 giây.** Đo trên Windows: gọi tới cổng đã đóng mất **~2,03 giây** mới báo lỗi chứ không báo ngay, nên phần lớn thời gian mỗi vòng chờ là chờ mạng chứ không phải khoảng nghỉ. Từ bản này mỗi lần hỏi bị cắt sau 1,5 giây và khoảng nghỉ rút xuống 0,5–1 giây.

Thời gian chết tệ nhất giữa lúc ứng dụng sống lại và lúc màn hình nhận ra: **4,03 → 2,00 giây** khi mở ấm, **7,03 → 2,50 giây** khi mở nguội.

## v2.0.7 - 2026-08-12

**Tách updater bootstrap khỏi phiên bản source đang chạy.** Public signed feed bổ sung asset `TikTokAffiliateUpdater-v1.0.0.ps1`; ứng dụng xác minh Ed25519 manifest, filename, protocol, kích thước và SHA-256 trước khi tải và kiểm tra lại hash ngay trước khi chạy. Logic đợi app thoát, cài Inno, khởi động lại và health handshake từ đây được phân phối độc lập theo release thay vì sinh từ Python source cũ.

- Thêm handshake theo `attempt_id`, protocol, bootstrap version và target version; status cũ hoặc ACK của lần thử khác không thể làm app đóng nhầm.
- `instance.json` ghi `app_version`; bootstrap chỉ báo thành công khi đúng target version phản hồi `/health`.
- Giữ nguyên feed schema v1, Ed25519 key, AppId, installer filename, data path và restart contract để v2.0.6 vẫn nâng cấp được lên v2.0.7 bằng helper legacy.
- Candidate/release allowlist, `SHA256SUMS.txt` và anonymous release verification bao gồm cả bootstrap độc lập.
- Thêm tài liệu threat model, protocol và release gates tại `docs/V2.0.7-INDEPENDENT-UPDATER.md`.

## v2.0.6 - 2026-08-12

> Recovery boundary: the v2.0.5 app still owns the bootstrap for the one-time
> v2.0.5 → v2.0.6 hop. Exact-head Windows tests protect the new helper, while
> the public transition is verified after release. Manual install remains the
> fallback if an older helper is delayed by antivirus on an end-user machine.

### Fixed

- Nới thời gian chờ handshake của updater helper từ 5 lên 30 giây để PowerShell cold-start hoặc antivirus không tạo lỗi giả trước khi helper kịp báo sẵn sàng.
- Dừng helper an toàn nếu handshake thật sự thất bại, tránh để tiến trình nền cũ tiếp tục chờ và tranh chấp với lần thử sau.
- Smoke updater qua UI giờ phát hiện backend `failed` ngay, đồng thời lưu trạng thái và log helper/installer đã scrub để chẩn đoán lỗi Windows mà không lộ đường dẫn máy runner.

## v2.0.5 - 2026-08-12

**Account thân thiện nhưng định danh vẫn ổn định.** Tên hiển thị account giờ là nhãn chính và code bất biến là thông tin phụ trên Dashboard, Analytics, Orders, Imports, Targets và Users. Thêm, đổi tên, lưu trữ, kích hoạt lại hoặc xóa account cập nhật metadata đang hiển thị ngay trong App Shell; nếu đồng bộ lại lỗi, ứng dụng giữ dữ liệu đã xác minh gần nhất và cho phép thử lại thay vì reload mất trạng thái.

**Luồng bắt đầu rõ hơn cho người dùng mới.** Dashboard hướng dẫn theo đúng quyền, account, lịch sử import và target tháng hiện tại. Trang Import khóa thao tác khi chưa có account, giải thích bước cần làm và sau khi upload thành công đưa hành động trực tiếp sang Dashboard hoặc Mục tiêu.

**Release candidate được cài thử trước khi merge.** Pull request cùng repo thay đổi runtime hoặc installer sẽ build đúng PR merge SHA, chỉ lưu installer cùng SHA256SUMS và chạy fresh smoke lẫn nâng cấp `2.0.4 -> 2.0.5` bằng cùng oracle Windows hiện hữu. Fork không được cấp quyền chạy artifact/install và phải chuyển commit đã review sang branch cùng repo trước merge.

**Updater có smoke qua đúng giao diện thật.** Workflow thủ công sau release cài bản cũ, tạo marker, dùng Playwright bấm **Kiểm tra lại** và **Cài bản cập nhật**, chờ ứng dụng reconnect rồi xác minh phiên bản, trạng thái `installed` và dữ liệu marker còn nguyên. Workflow không dùng token ghi feed, không chạy installer mới trực tiếp và chỉ lưu screenshot/summary đã scrub.

## v2.0.4 - 2026-08-12

**Điều hướng static export và cache sau cập nhật ổn định hơn.** Backend phục vụ đúng các RSC payload do Next.js static export tạo ra thay vì để client nhận `404`; resolver chỉ ánh xạ file hợp lệ trong static root. Service worker dùng cache namespace theo phiên bản ứng dụng, bao phủ đủ route Settings và hiển thị trang kết nối lại riêng khi offline thay vì trả nhầm Dashboard.

**Accessibility được khóa bằng regression thực tế.** Focus ring và chữ phụ đạt ngưỡng tương phản ở chế độ sáng/tối; các summary dùng semantic HTML; command palette, bottom sheet và dialogs giữ luồng focus bàn phím đúng. Axe chạy trên 10 route ở 320, 390, 768 và 1440 px không còn violation; reduced-motion và capability states cũng được kiểm tra.

**Dashboard mobile gọn nhưng không mất dữ liệu.** Today Pulse, mục tiêu và cảnh báo hành động được ưu tiên; sáu khối phân tích thứ cấp thu gọn bằng disclosure có vùng chạm tối thiểu 44 px, hỗ trợ bàn phím và không tràn ngang ở 320 px. Desktop tiếp tục hiển thị đầy đủ và tùy chỉnh widget vẫn được giữ.

**Updater có trạng thái kết thúc rõ ràng.** Helper ghi `installed` sau health handshake thành công, tương thích trạng thái legacy và dùng thời gian reconnect 90 giây nhất quán. API/UI không hiển thị path, exit code hoặc log nội bộ; thay vào đó đưa thông báo tiếng Việt cùng hành động tiếp theo.

## v2.0.3 - 2026-08-12

**Loại bỏ điều hướng Cài đặt bị trùng.** Các trang Giao diện, Dữ liệu, Cập nhật và Người dùng giờ chỉ dùng một nguồn điều hướng: sidebar trên desktop và menu **Thêm** trên mobile. Trạng thái active giữ đúng ở mọi route, kể cả khi thu gọn hoặc mở rộng sidebar.

**Sidebar gọn và hướng tới người dùng cuối.** Bỏ hoàn toàn khối kỹ thuật “API hoạt động / Nội bộ ứng dụng”; tài khoản local được hiển thị là **Chế độ cục bộ** thay cho email giả `local-owner@localhost`. Đăng xuất và Thoát vẫn được ghim ở đáy và tự giãn đúng khi chỉ có một hành động.

**Thiết kế lại trang Cập nhật ứng dụng.** Trạng thái phiên bản, bản đang dùng, bản mới nhất và hành động chính được gom thành một hierarchy rõ ràng. Timeline đủ năm bước luôn nằm một hàng trên desktop và chuyển thành một cột trên mobile, không còn bước “Khởi động lại” bị rớt dòng. Tiến độ tải chỉ xuất hiện khi cần; ghi chú phát hành thu gọn; chữ ký và SHA-256 vẫn được xác minh như trước.

Đợt audit chạy trên toàn bộ 10 route ở 320, 390, 768 và 1440 px, cả sáng/tối. Regression kiểm tra overflow, duplicate ID, active navigation, touch target, accessibility và static production build.

## v2.0.2 - 2026-08-11

**Làm rõ quyền truy cập và ranh giới vận hành của bản dùng chung.** OIDC allowlist giờ áp dụng nhất quán cho user mới, user hiện hữu và session đang hoạt động; email bị loại khỏi cấu hình sẽ mất quyền ở request tiếp theo thay vì tiếp tục dùng session cũ. Trang **Người dùng** giải thích rõ `active` không thể vượt qua `AUTH_ALLOWED_EMAILS`.

API meta công bố capability theo runtime/database. Trên PostgreSQL hoặc OIDC dùng chung, trang **Dữ liệu** và **Cập nhật** chuyển sang trạng thái do hạ tầng quản lý, không gọi endpoint Reset/Restore hoặc trình cài Windows local-only. Bản local SQLite/Windows giữ nguyên đầy đủ backup, restore và auto-update hiện có.

**Hoàn thiện responsive sau audit toàn bộ ứng dụng.** Tất cả route được kiểm tra ở 320, 390, 768 và 1440 px. Import không còn tạo overflow ngang do file input ẩn; tab Phân tích mobile tự dàn thành lưới đọc được đầy đủ; các điều khiển quan trọng đạt vùng chạm tối thiểu 44 px và có khoảng cuộn an toàn phía trên bottom navigation.

**Giảm trùng lặp và làm rõ thông tin.** Navigation Settings theo chiều ngang chỉ xuất hiện trên mobile, nơi sidebar không có mặt. Orders đổi nhãn thành **Bộ lọc đang áp dụng**; ngày giờ luôn hiển thị năm bốn chữ số để tránh hiểu nhầm.

## v2.0.0 - 2026-08-11

**Momentum Canvas thay toàn bộ lớp trải nghiệm, giữ nguyên lõi dữ liệu đã đối soát.** App có hệ thống thiết kế mới cho vận hành và tăng trưởng: Today Pulse, tiến độ mục tiêu, cảnh báo hành động, biểu đồ xu hướng, đóng góp theo tài khoản, đối soát và sức khỏe dữ liệu. Navigation desktop hỗ trợ thu gọn và tìm nhanh `Ctrl/Cmd + K`; mobile có bottom navigation, action sheet và filter bottom sheet thay vì nhồi toàn bộ điều khiển lên đầu trang.

**Mobile không còn là bản desktop co nhỏ.** Dashboard, Đơn hàng, Nhập dữ liệu và các trang quản trị có bố cục riêng cho màn hình 320–390 px, card list, thao tác chạm đủ lớn, safe-area và trạng thái loading/empty/error rõ ràng. Biểu đồ Recharts có bảng dữ liệu thay thế cho trình đọc màn hình.

**Chế độ sáng/tối được đưa về đúng Cài đặt → Giao diện.** Tuỳ chọn `Theo hệ thống / Sáng / Tối`, trạng thái thu gọn sidebar, thứ tự/ẩn widget Dashboard và chế độ xem báo cáo được lưu riêng theo người dùng trong database. Reset Data không xoá các tuỳ chọn này; full backup/restore có thể khôi phục chúng.

**Operations và Finance workflows được tổ chức lại.** Analytics chia theo tài chính, account, sản phẩm/nội dung, đối soát và chất lượng dữ liệu. Orders có chế độ xem lưu sẵn, cột tuỳ chọn và mobile cards. Imports thành quy trình Account → Files → Queue → Upload. Targets, Accounts, Data, Updates và Users được làm rõ quyền, preview ảnh hưởng và thao tác xác nhận.

Python/FastAPI, SQLite/PostgreSQL, công thức KPI, deduplication theo snapshot/version, dữ liệu người dùng và signed public updater vẫn được giữ nguyên. Migration mới chỉ bổ sung bảng cá nhân hoá và tự chạy khi mở database cũ.

## v1.4.3 - 2026-08-11

**Sang tháng mới không phải gõ lại KPI cho từng tài khoản.** Trang **Mục tiêu** có thêm nút **Chép KPI tháng trước**: một lần bấm là chép KPI/ngày của tháng liền trước sang tháng đang xem.

Nút này **không ghi đè** tài khoản nào đã có KPI cho tháng đích. Nếu bạn đã chỉnh một vài tài khoản rồi mới bấm, những con số đó được giữ nguyên và hệ thống báo rõ đã chép bao nhiêu, giữ nguyên bao nhiêu. Bấm nhầm lần nữa cũng không hỏng gì. Việc chép chạy trong một lần ghi duy nhất nên không có chuyện chép được nửa chừng.

Chỉ tài khoản bạn có quyền mới được chép; người chỉ có quyền xem không bấm được.

**Tháng KPI bám theo phạm vi đang lọc.** Trước đây nếu bạn mở trang Mục tiêu bằng đường dẫn có sẵn khoảng ngày (ví dụ tháng 3) thì ô nhập vẫn sửa KPI của tháng hiện tại — sửa nhầm tháng mà không có gì báo. Giờ tháng KPI lấy theo ngày bắt đầu của phạm vi.

## v1.4.2 - 2026-08-11

**Sửa lỗi tiến độ mục tiêu sai khi khoảng ngày bắc qua hai tháng.**

KPI được đặt riêng cho từng tháng. Khi bạn chọn "30 ngày qua" gần đầu tháng, khoảng đó nằm vắt qua hai tháng — nhưng ô **Tiến độ mục tiêu** chỉ tính phần thuộc tháng hiện tại, trong khi ô **Hoa hồng thực tế** ngay cạnh nó tính đủ cả 30 ngày. Hai con số nằm cạnh nhau trên cùng một màn hình nhưng đo hai khoảng thời gian khác nhau, mà không có gì báo cho bạn biết.

Ví dụ đo được: khoảng 13/07–11/08 với KPI 1.000 ₫/ngày và hoa hồng 80.000 ₫. Hệ thống báo tiến độ **181,8%** (chỉ lấy 20.000 ₫ của 11 ngày tháng 8 chia cho mục tiêu 11 ngày). Con số đúng cho cả 30 ngày là **266,7%** — 80.000 ₫ chia cho mục tiêu 30.000 ₫.

Từ bản này, mục tiêu của cả phạm vi là tổng KPI/ngày nhân số ngày của từng tháng trong phạm vi đó, đúng theo cách hệ thống vẫn tính khi bạn chọn một phần của tháng. Nếu có tháng nào trong phạm vi chưa đặt KPI, hệ thống báo "chưa xác định" thay vì cộng các tháng còn lại rồi báo vượt mục tiêu một cách giả tạo.

Lỗi này chỉ ảnh hưởng phần hiển thị tiến độ; hoa hồng, GMV và số đơn luôn đúng.

**Trang Mục tiêu nói rõ đang tính trên khoảng nào**, thay vì chỉ ghi tên tháng trong khi tiến độ lại tính theo phạm vi lọc. Thông báo lỗi khi lưu cũng được đọc lên cho trình đọc màn hình đúng cách.

## v1.4.1 - 2026-08-11

Đợt chỉnh giao diện thứ hai, lần này dựa trên ảnh chụp thật của OmniRoute chứ không phải suy đoán từ mã nguồn.

**Menu trái chia thành ba nhóm** — Báo cáo, Dữ liệu, Hệ thống — và mỗi mục có thêm một dòng mô tả. Bảy mục xếp phẳng bắt bạn phải nhớ "Mục tiêu" khác "Tài khoản" chỗ nào; giờ đọc là biết.

**Số phiên bản hiện ngay dưới tên ứng dụng.** Trước đây nó nằm sâu trong Cài đặt và chỉ chủ sở hữu xem được, nên lúc báo lỗi thường không ai biết mình đang chạy bản nào.

**Nút Đăng xuất và Thoát ứng dụng chuyển xuống đáy menu trái.** Trước đây "Thoát ứng dụng" nằm ngay cạnh email của bạn ở đầu trang — đúng chỗ dễ bấm nhầm nhất cho thao tác nguy hiểm nhất.

**Chọn khoảng thời gian không cần mở bộ lọc nữa.** 7 ngày / 30 ngày / Tháng này / Tháng trước giờ là một cụm nút liền khối luôn hiện, khoảng đang xem được tô đặc. Trước đây bốn nút này nằm bên trong phần thu gọn và trông giống hệt nhau nên không biết đang ở khoảng nào.

**Tổng quan gọn hơn một màn hình:**
- Tiêu đề trang dời lên cùng hàng với email và nút đổi màu, thay vì chiếm riêng một hàng trong khi nửa hàng trên bỏ trống.
- Nút **Xuất báo cáo ngày** về nằm cạnh dòng phạm vi mà nó xuất, không còn đứng một mình một hàng.
- Bốn thẻ lớn và dải năm chỉ số phụ gộp thành **một lưới đều chín ô**: cùng cỡ chữ, cùng cách trình bày nên quét mắt một lượt là đọc hết.
- Nhãn mỗi ô chuyển thành chữ nhỏ in hoa để con số là thứ duy nhất bắt mắt.
- Bỏ ô trống lớn cạnh "Các lần nhập gần đây".

Đã đo tương phản cho toàn bộ màu mới ở cả hai chế độ: thấp nhất 4,87:1, trên ngưỡng WCAG AA cho chữ nhỏ.

## v1.4.0 - 2026-08-11

Đợt chỉnh giao diện theo hướng bảng điều khiển kỹ thuật: dày thông tin hơn, ít chữ thừa hơn, số dễ so hơn.

**Bộ lọc không còn chiếm nửa màn hình.** Trước đây phần chọn tháng, ngày, tài khoản và trạng thái luôn mở sẵn, ngốn gần 300 điểm ảnh chiều cao và đẩy số liệu xuống dưới. Giờ nó thu lại thành một dòng cho biết đang xem phạm vi nào, bấm **Chỉnh sửa** mới mở ra.

**Số liệu thẳng cột.** Toàn bộ con số trong bảng và thẻ dùng chữ số đều nhau, nên nhìn dọc là so được ngay thay vì phải đọc từng dòng. Mã đơn và mã SKU chuyển sang phông đơn cách vì chúng được đọc theo từng ký tự, không phải theo từ.

**Menu bên trái có biểu tượng** cho từng mục, nhận ra bằng hình nhanh hơn đọc chữ.

**Bớt lặp và bớt ồn:**
- Bỏ khối "Phạm vi báo cáo" hiện hai lần cạnh nhau trên Tổng quan.
- Dòng thông tin chất lượng dữ liệu chỉ tô màu cảnh báo khi thật sự có vấn đề; không có gì bất thường thì nó im lặng.
- Nút **Thoát ứng dụng** không còn là thứ nổi bật nhất màn hình dù là thao tác nguy hiểm nhất; nó chỉ chuyển đỏ khi bạn rê chuột vào.
- Ngày trong bảng Đơn hàng hiển thị theo định dạng Việt Nam thay vì dạng máy `2026-03-10T08:00:00`.

**Lúc chờ tải, màn hình giữ nguyên khung** thay vì hiện một dòng chữ rồi nhảy layout khi dữ liệu về.

## v1.3.4 - 2026-08-11

**Cập nhật xong không còn mở thêm tab trình duyệt trùng.** Trước đây mỗi lần mở app lại chọn một cổng ngẫu nhiên mới, nên tab bạn đang xem tiến độ cập nhật trỏ vào một địa chỉ đã chết và app buộc phải mở tab thứ hai — bạn còn lại hai tab, một cái hỏng. Giờ app dùng lại đúng cổng của lần chạy trước nếu còn trống, nên chính tab đang mở tự kết nối lại và hiện bản mới, không mở thêm gì. Nếu cổng cũ đã bị chương trình khác chiếm thì app vẫn mở tab mới như trước, vì lúc đó tab cũ chắc chắn không dùng được nữa.

**Bản sao lưu chỉ giữ 3 bản gần nhất.** Mỗi lần xoá dữ liệu, khôi phục, xoá tài khoản hay hoàn tác lần nhập, hệ thống đều chép nguyên database ra một bản sao lưu — không dọn thì thư mục phình mãi, với database 25 MB thì vài chục thao tác là hàng trăm MB nằm chết. Giờ hệ thống tự xoá các bản cũ hơn và luôn chừa lại bản bạn đang khôi phục.

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
