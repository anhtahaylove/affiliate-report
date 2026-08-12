# Hướng thiết kế đã chốt

## Ba phương án đã đưa (2026-08-13)

| Bản | Ý tưởng | Ảnh |
|---|---|---|
| A — Bảng điều khiển một màn | Giữ đủ thông tin, khối không có gì để nói co lại đúng một dòng | `A-ban-dieu-khien-mot-man.png` |
| B — Việc cần làm trước | Một câu phán tình trạng, chỉ việc còn dở được tô sáng, khối im lặng đẩy sang kệ phải | `B-viec-can-lam-truoc.png` |
| C — Một số chủ đạo | Một con số 62px, kệ ngang người dùng tự chọn thẻ nào hiện | `C-mot-so-chu-dao.png` |

Cả ba dùng số liệu thật (40.000 ₫ / 200.000 ₫ / 2 đơn / SHOTSHOP / 01–31/03/2026), cùng token màu thật của sản phẩm, ba bộ khung bố cục khác nhau về cấu trúc.

## Lựa chọn của người dùng — nguyên văn

> "phương án thiết kế có thể giống với bản hiện tại, nhưng nâng cấp, cải tiến, cải thiện, chỉnh sửa đẹp hơn"

Tức **không** chọn A, B hay C như một bản thay thế. Giữ nguyên cấu trúc và ngôn ngữ thị giác hiện tại của v2.0.11, làm tinh hơn.

## Cách diễn giải để thi công

Vấn đề số một người dùng tự chọn ở vòng hỏi: **"nhiều khối không dùng tới"**. Nên đợt này lấy **đúng một ý tưởng cốt lõi của phương án A** — khối không có gì để nói thì co lại một dòng — vì đó là cách giải quyết than phiền đó mà **không** dời chỗ bất kỳ khối nào. Các phần khác là tinh chỉnh tại chỗ:

1. Khối rỗng (cảnh báo, sức khỏe dữ liệu, đối soát khi sạch) co còn một dòng có số tóm tắt; có sự cố thì nở lại thành thẻ đầy đủ.
2. Bỏ số bị lặp — hoa hồng 40.000 ₫ hiện ba lần ở ba khối khác nhau.
3. Checklist khởi động tự gấp khi đã xong.
4. Gom bớt ba hàng điều khiển ở đầu trang (chế độ xem, phạm vi, tùy chỉnh widget).
5. Tinh chỉnh khoảng cách và thứ bậc chữ, không đổi bảng màu.

## Ràng buộc giữ nguyên

- Chữ chính ≥14px, tương phản ≥4.5:1 (đợt trước đo thấp nhất 4,87:1)
- Vùng chạm mobile ≥44px
- `axe` không phát sinh vi phạm mới trên 10 route × 4 khổ màn hình
- Toàn bộ e2e hiện có phải xanh, kể cả `layout-audit` và `update-ui`

## Ngoài phạm vi đợt này

Import từ điện thoại: bị chặn bởi ranh giới loopback (`desktop_launcher.py:20`, `api.py:458-461`), không giải được bằng giao diện. Ba đường đã nêu với người dùng, chờ quyết định riêng.
