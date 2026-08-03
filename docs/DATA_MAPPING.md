# Mapping dữ liệu — TikTok export → TikTok Affiliate Report

## 1. Grain và khoá

| Mục | Quy tắc đã chốt |
|---|---|
| Grain input | Một dòng đơn hàng/SKU |
| Business key | `affiliate_account + order_id + sku_id` |
| File dedupe | SHA-256 của bytes file |
| Row dedupe | SHA-256 của 47 giá trị đã normalize |
| ID type | `TEXT`, không parse thành số |
| Money type | VND integer/`NUMERIC(18,0)` |
| Date input | `dd/MM/yyyy HH:mm:ss`; `/` hoặc rỗng → `NULL` |
| Report date | Ngày của `Ngày đặt hàng` |
| Delete rule | Vắng mặt ở file sau không làm mất dòng hiện hành |

> File export không có trường tài khoản affiliate chủ file. `Tên cửa hàng` là seller shop. Người upload bắt buộc chọn `CHIISTORE`, `EMLINHNOIY`, `THAOBRA` hoặc account được cấu hình.

### Profile bốn file TikTok mẫu

| File suffix | Dòng | Khoảng ngày đặt hàng | Canonical status |
|---|---:|---|---|
| `7668993110945826580_1` | 1.637 | 2026-05-05 → 2026-08-02 | 1.293 settled; 239 ineligible; 105 pending |
| `7669031960321165076_1` | 2 | 2026-05-06 → 2026-05-09 | 2 settled |
| `7669183192695768852_1` | 760 | 2026-05-05 → 2026-08-02 | 620 settled; 120 ineligible; 20 pending |
| `7669183192696293140_1` | 3.111 | 2026-05-05 → 2026-08-02 | 2.424 settled; 553 ineligible; 134 pending |

Cả bốn file có đúng cùng 47 headers, tổng 5.510 dòng và không có cặp `ID đơn hàng + ID SKU` trùng trong hoặc giữa các file. Dữ liệu không có trường nào xác định affiliate account; seller shop không được dùng để suy ra account.

## 2. Cấu trúc output legacy đã phân tích

Mỗi sheet tháng trong `REPORT AFF.xlsx` có cùng bố cục:

| Vùng | Nội dung |
|---|---|
| `B:I` | CHIISTORE |
| `K:R` | EMLINHNOIY |
| `T:AA` | THAOBRA |
| `AC:AD` | Tổng doanh thu thực tế và tổng hoa hồng thực tế |
| Hàng 3 | Tổng tháng |
| Hàng 5–35 | Số liệu từng ngày |
| `AC1:AD1` | KPI hoa hồng thực tế tổng/ngày |

Trong mỗi block account:

1. Số lượng bán.
2. Tổng doanh thu.
3. Tổng hoa hồng ban đầu.
4. Doanh thu huỷ.
5. Hoa hồng huỷ.
6. Doanh thu thực tế = tổng doanh thu − doanh thu huỷ.
7. Hoa hồng thực tế = tổng hoa hồng ban đầu − hoa hồng huỷ.

KPI legacy:

| Tháng | KPI hoa hồng thực tế/ngày |
|---|---:|
| 2026-03 | 350.000 VND |
| 2026-04 | 400.000 VND |
| 2026-05 | 450.000 VND |
| 2026-06 | 500.000 VND |
| 2026-07 | 500.000 VND |
| 2026-08 | 500.000 VND |

Trong Operations Cockpit, các giá trị trên được giữ ở target `ALL`. User có thể đặt thêm KPI/ngày riêng cho từng account; target tháng và tỷ lệ đạt được Python core tính từ đúng target của account/phạm vi đang xem.

### Kết quả đối soát mapping

| File suffix | Block legacy khớp mạnh nhất | Đối soát số lượng | MAE Tổng DT/ngày | MAE Tổng HH ban đầu/ngày | Độ tin cậy |
|---|---|---:|---:|---:|---|
| `7669183192696293140_1` | `CHIISTORE` | 89/89 ngày active khớp | ~25.090 VND | ~26 VND | Cao |
| `7668993110945826580_1` | `EMLINHNOIY` | 89/89 ngày active khớp | ~22.889 VND | ~25 VND | Cao |
| `7669183192695768852_1` | `THAOBRA` | 88/90 ngày workbook khớp | ~16.255 VND | ~370 VND | Cao |
| `7669031960321165076_1` | Chưa xác định | Chỉ có 2 dòng | — | — | Không đủ dữ liệu |

Ngày `2026-08-02` còn trống trong workbook nhưng đã có dữ liệu trong các export mới. Các sai lệch tiền nhỏ phù hợp với việc workbook legacy có làm tròn hoặc điều chỉnh thủ công.

Kết quả trên chỉ là bằng chứng đối soát bộ mẫu, **không phải quy tắc nhận diện account khi chạy app**. Không hard-code filename → account và không dùng seller shop để suy ra account. Selector upload không có giá trị mặc định; operator phải chọn account rõ ràng.

Các ô huỷ trong workbook thường thấp hơn trạng thái hiện tại của export, nên nguồn mới dùng current status `ineligible`; không sao chép số huỷ hard-code từ workbook. Mapping cột và công thức bên dưới là nguồn sự thật cho MVP; workbook legacy chỉ dùng để kiểm chứng hình dạng output.

## 3. Mapping 47 cột input

`Typed` nghĩa là có cột riêng để filter/tính KPI trong MVP. `Raw JSON` nghĩa là vẫn được giữ đầy đủ để audit và có thể nâng thành typed field sau này.

| # | Header TikTok | Normalized field | Kiểu | MVP use |
|---:|---|---|---|---|
| 1 | ID đơn hàng | `order_id` | text | Typed, business key/search |
| 2 | ID SKU | `sku_id` | text | Typed, business key/search |
| 3 | Tên sản phẩm | `product_name` | text | Typed, explorer |
| 4 | ID sản phẩm | `product_id` | text | Raw JSON |
| 5 | Giá | `unit_price_vnd` | numeric(18,0) | Raw JSON |
| 6 | Số món bán ra | `units_sold` | integer | Typed, KPI |
| 7 | Số món đã hoàn tiền | `units_refunded` | integer | Typed, KPI |
| 8 | Tên cửa hàng | `shop_name` | text | Typed, explorer/filter |
| 9 | Mã cửa hàng | `shop_id` | text | Raw JSON |
| 10 | Đối tác liên kết | `affiliate_partner` | text | Raw JSON |
| 11 | Agency | `agency` | text | Raw JSON |
| 12 | Đơn vị tiền tệ | `currency_code` | text | Raw JSON; MVP kỳ vọng VND |
| 13 | Loại đơn hàng | `order_type` | text | Raw JSON |
| 14 | Trạng thái quyết toán đơn hàng | `status_raw` / `status` | text | Typed, cancellation/filter |
| 15 | Gián tiếp | `is_indirect` | text/boolean | Raw JSON |
| 16 | Loại hoa hồng | `commission_type` | text | Raw JSON |
| 17 | Loại nội dung | `content_type` | text | Raw JSON |
| 18 | Id nội dung | `content_id` | text | Raw JSON |
| 19 | Tiêu chuẩn | `standard_rate` | numeric/text | Raw JSON |
| 20 | Quảng cáo cửa hàng | `shop_ads_rate` | numeric/text | Raw JSON |
| 21 | TikTok thưởng | `tiktok_bonus_rate` | numeric/text | Raw JSON |
| 22 | Đối tác thưởng | `partner_bonus_rate` | numeric/text | Raw JSON |
| 23 | Phần chia doanh thu | `revenue_share_rate` | numeric/text | Raw JSON |
| 24 | GMV | `gmv` | numeric(18,0) | Typed, tổng doanh thu |
| 25 | Cơ sở hoa hồng ước tính | `estimated_commission_base` | numeric(18,0) | Raw JSON |
| 26 | Hoa hồng tiêu chuẩn ước tính | `estimated_standard_commission` | numeric(18,0) | Thành phần hoa hồng ban đầu |
| 27 | Hoa hồng Quảng cáo cửa hàng ước tính | `estimated_shop_ads_commission` | numeric(18,0) | Thành phần hoa hồng ban đầu |
| 28 | Thưởng ước tính | `estimated_bonus` | numeric(18,0) | Thành phần hoa hồng ban đầu |
| 29 | Thưởng ước tính của đối tác liên kết | `estimated_partner_bonus` | numeric(18,0) | Thành phần hoa hồng ban đầu |
| 30 | IVA ước tính | `estimated_iva` | numeric(18,0) | Raw JSON |
| 31 | ISR ước tính | `estimated_isr` | numeric(18,0) | Raw JSON |
| 32 | Est. CedularTax | `estimated_cedular_tax` | numeric(18,0) | Raw JSON |
| 33 | PIT ước tính | `estimated_pit` | numeric(18,0) | Raw JSON |
| 34 | Ước tính phần chia doanh thu | `estimated_revenue_share` | numeric(18,0) | Thành phần hoa hồng ban đầu |
| 35 | Cơ sở hoa hồng thực tế | `actual_commission_base` | numeric(18,0) | Raw JSON |
| 36 | Hoa hồng tiêu chuẩn | `actual_standard_commission` | numeric(18,0) | Raw JSON |
| 37 | Hoa hồng Quảng cáo cửa hàng | `actual_shop_ads_commission` | numeric(18,0) | Raw JSON |
| 38 | Thưởng | `actual_bonus` | numeric(18,0) | Raw JSON |
| 39 | Thưởng của đối tác liên kết | `actual_partner_bonus` | numeric(18,0) | Raw JSON |
| 40 | Thuế - ISR | `tax_isr` | numeric(18,0) | Raw JSON |
| 41 | Thuế - IVA | `tax_iva` | numeric(18,0) | Raw JSON |
| 42 | cedular_tax | `cedular_tax` | numeric(18,0) | Raw JSON |
| 43 | Thuế - PIT | `tax_pit` | numeric(18,0) | Raw JSON |
| 44 | Đã chia sẻ với đối tác | `shared_with_partner` | numeric(18,0) | Raw JSON |
| 45 | Tổng số tiền nhận được cuối cùng | `final_received` | numeric(18,0) | Typed, KPI TikTok riêng |
| 46 | Ngày đặt hàng | `order_date` | timestamp | Typed, report date |
| 47 | Ngày quyết toán hoa hồng | `settlement_date` | timestamp nullable | Typed, settlement analysis |

### `estimated_commission` typed field

MVP lưu thêm trường tổng đã tính sẵn cho mỗi version:

```text
estimated_commission = col_26 + col_27 + col_28 + col_29 + col_34
```

Giá trị trống được xem là `0` trong phép cộng, nhưng raw value vẫn được giữ.

## 4. Status normalization

| Raw status | Canonical status |
|---|---|
| `Đã quyết toán` | `settled` |
| `Không đủ điều kiện` | `ineligible` |
| `Chờ xử lý` | `pending` |
| `AwaitingPayment` | `pending` |
| Giá trị khác | `unknown` |

Không dịch đè raw value. Hệ thống luôn giữ `status_raw` trong `raw_json`.

## 5. Mapping output báo cáo ngày

| Output | Công thức trên current versions |
|---|---|
| Số lượng bán | `SUM(units_sold)` |
| Số lượng hoàn | `SUM(units_refunded)` |
| Tổng DT | `SUM(gmv)` |
| Tổng HH ban đầu | `SUM(estimated_commission)` |
| DT huỷ | `SUM(gmv WHERE status='ineligible')` |
| HH huỷ | `SUM(estimated_commission WHERE status='ineligible')` |
| DT thực tế | `Tổng DT - DT huỷ` |
| HH thực tế | `Tổng HH ban đầu - HH huỷ` |
| TikTok thực nhận | `SUM(final_received)`; hiển thị riêng |
| Tổng DT thực tế | Tổng `DT thực tế` của các account |
| Tổng HH thực tế | Tổng `HH thực tế` của các account |
| Tỷ lệ đạt KPI | `Tổng HH thực tế / KPI ngày` |

### Output wide cho Google Sheets v1

Tab **Google Sheets output** tạo một dòng cho mỗi `Ngày`, sắp xếp tăng dần để import/paste vào Sheet. Mỗi account có đúng bảy cột theo block legacy:

```text
<ACCOUNT> - Số lượng bán
<ACCOUNT> - Tổng DT
<ACCOUNT> - Tổng HH ban đầu
<ACCOUNT> - DT huỷ
<ACCOUNT> - HH huỷ
<ACCOUNT> - DT thực tế
<ACCOUNT> - HH thực tế
```

Cuối dòng là `Tổng DT thực tế`, `Tổng HH thực tế`, `KPI/ngày`, `% đạt KPI`. Account không có dữ liệu trong ngày được điền `0`; KPI không có cấu hình được giữ trống. CSV dùng UTF-8 BOM để mở/import thuận tiện trong Excel và Google Sheets.

## 6. Quy tắc import

1. Xác nhận đủ và đúng 47 headers.
2. Chuẩn hoá chuỗi Unicode, trim khoảng trắng; ID vẫn là text.
3. Tiền VND: bỏ dấu phân cách nghìn và ký tự không phải số hợp lệ; không dùng float.
4. Ngày: parse theo day-first; `/` và chuỗi rỗng thành `NULL`.
5. Tính `file_sha`, `business_key`, `normalized_hash`.
6. Ghi raw row trước khi tạo/đổi current version.
7. Toàn bộ batch chạy trong transaction.

## 7. Các điểm chưa ép vào MVP

- Số liệu legacy có điều chỉnh thủ công và làm tròn, nên không lấy các ô đó làm nguồn dữ liệu mới.
- Các cột thuế/hoa hồng thực tế TikTok được giữ trong raw JSON nhưng chưa tách thành dashboard riêng.
- `REPORT AFF.xlsx` là nguồn output legacy đã chốt cho MVP. Link Google Sheets gốc chỉ cần nếu sau này phải kiểm tra tính năng riêng của Sheets hoặc đồng bộ trực tiếp.
- V1 chỉ tải CSV Google Sheets-ready; chưa gọi Google Sheets API hoặc lưu credential Google.
