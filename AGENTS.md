# AGENTS.md

Ứng dụng desktop Windows local-first: FastAPI + Next.js static export đóng gói bằng
PyInstaller, phát hành qua installer Inno Setup và tự cập nhật bằng feed ký Ed25519.
Có thêm bản Android (Capacitor + Chaquopy) dùng chung phiên bản.

## Quy tắc không được phá

- **Không bump phiên bản, không tạo tag, không push, không publish feed** nếu người dùng
  chưa yêu cầu rõ ràng. Tag đẩy lên là phát hành thật tới mọi máy người dùng, không thu hồi được.
- **Không tuyên bố "xong" dựa trên mock hay Playwright.** Bằng chứng phải đến từ runtime đã
  đóng gói: cài installer, chạy app, gọi API loopback thật. UI mock qua được không có nghĩa
  bản đóng gói chạy được.
- Kiểm `git log` / `git status` **trước và sau** mỗi lần sửa. Repo này có thể có phiên agent
  khác chạy song song với quyền tự commit/push; báo ngay nếu thấy commit mình không tạo.
- `main` không có branch protection. Release workflow đẩy thẳng `stable.json` lên `main`,
  nên nếu bật protection phải chừa bypass cho `github-actions[bot]`.

## Phiên bản: một nguồn sự thật

`affiliate_report/version.py` là nguồn duy nhất. Mọi nơi khác đều dẫn xuất.

```bash
# sửa APP_VERSION trong affiliate_report/version.py, rồi:
python -m scripts.sync_version           # ghi lại 16 file dẫn xuất
python -m scripts.sync_version --check   # chỉ báo lệch, exit 1
```

- Android `versionCode` suy ra bằng `major*1_000_000 + minor*1_000 + patch` (2.1.2 → 2001002).
- Gate Android dựng thêm bản synthetic **N+1** để thử nâng cấp cùng khóa ký; script tự tính.
- `tests/test_packaging_contract.py` gọi `--check`, nên lệch làm đỏ test cục bộ trong 0,2 giây.

**Cạm bẫy đã trả giá:** các workflow kiểm phiên bản bằng regex **escape dấu chấm**
(`APP_VERSION = "2\.1\.2"`, `versionName='2\.1\.2'`). Thay chuỗi literal `"2.1.2"` không chạm
tới chúng. Ở v2.1.2 điều này làm gate Android hỏng ở phút thứ 20 của CI. `sync_version` xử lý
cả hai dạng — đừng sửa tay.

`sync_version` đọc thẳng file chứ không `import`, vì `__pycache__` cũ từng trả về phiên bản
sai và làm cả repo đồng bộ nhầm mà không báo gì.

## Phát hành

Thứ **duy nhất** khởi động phát hành là push tag `v*.*.*`. Trước đó, trên **đúng SHA của tag**
phải có cả hai workflow thành công với `event=push` trên `main`:

- `windows-installer-smoke.yml`
- `android-candidate.yml`

`release.yml` sau đó tự làm hết: build installer → tải APK đã ký đúng SHA → ký `stable.json`
bằng secret `UPDATE_SIGNING_KEY_B64` (đối chiếu public key với `TRUSTED_UPDATE_KEYS` ghim
trong `updater.py`) → tạo draft → publish prerelease → đẩy feed lên `main` → **chạy 5 client
Windows độc lập bấm "Cập nhật ngay" thật** → chỉ khi 5/5 đạt mới gỡ prerelease và đánh dấu
latest. Mọi bước fail-closed và tự rollback feed về bản đã ký trước đó.

**Bẫy path filter:** `windows-installer-smoke.yml` chỉ chạy khi commit chạm đúng các path
trong filter của nó. Sửa mình `android-candidate.yml` sẽ **không** kích hoạt lại nó, và
release sẽ bị chặn vì thiếu gate trên SHA mới. Khi vá gate Android, hãy chạm thêm một path
nằm trong filter (ví dụ `tests/test_packaging_contract.py`).

## Đóng gói Windows

- `packaging/build_installer.ps1` gọi `BUILD_EXE.bat` (PyInstaller onedir) rồi Inno Setup.
- Chạy được ở **cả** pwsh 7 lẫn Windows PowerShell 5.1.
- **Mọi `.ps1` chứa tiếng Việt phải giữ UTF-8 BOM.** Không BOM thì 5.1 đọc theo ANSI, chuỗi vỡ
  và script chết với `string is missing the terminator` — rất khó lần ra. `BUILD_EXE.bat` gọi
  `assert_no_embedded_database.ps1` bằng `powershell.exe` (5.1) ngay cả trong CI, nên đây là
  bẫy thật. Có test chặn trong `test_packaging_contract.py`.
- Dùng đường dẫn **ngắn** khi build ngoài repo (ví dụ `C:\wt`): Inno Setup gãy khi vượt
  MAX_PATH, và pnpm từ chối `node_modules` dạng junction.
- `packaging/TikTokAffiliateUpdater-v1.0.0.ps1` được ghim SHA-256 trong feed đã ký. **Đụng vào
  là hỏng bản phát hành đang chạy.**

## Giao diện

`web/src/app/globals.css` là một file phẳng hơn 2.300 dòng, hơn 700 class, **không có scope**
và không dùng CSS module. Va tên class giữa hai component không liên quan là rủi ro thường
trực: ở v2.1.2, `.download-progress` của trang cập nhật trúng luật `.target-track` của
dashboard và bị cắt còn 8px — lỗi lọt tới bản phát hành.

`web/e2e/clipping.ts` dò phần tử bị chính `overflow: hidden` cắt mất nội dung. Đang dùng ở:

- `layout-audit.spec.ts` — quét mọi route × 4 viewport (trạng thái mặc định)
- `update-ui.spec.ts` — quét từng trạng thái updater (nơi lỗi v2.1.2 thật sự sống)

Vòng quét route **không** chạm tới trạng thái có điều kiện. Thêm UI chỉ hiện ở một trạng thái
thì phải tự quét trạng thái đó.

## Validate dữ liệu: vài quy tắc có nhiều bản sao cố ý

Đừng gộp thành "một nguồn chung" tưởng sạch hơn — mỗi bản một vai trò khác nhau, gộp sai từng
gây lỗ hổng thật:

**Cạm bẫy đã trả giá:** mã account tồn tại ở BA bản `ACCOUNT_CODE_RE` cùng tên khác module —
`accounts.ACCOUNT_CODE_RE` và `db.ACCOUNT_CODE_RE` (giá trị **đã** `.upper()`, chỉ
`A-Z0-9_.-`) khác `api.AccountCreate.code` (`Field(pattern=...)`, input **thô** từ form, chấp
nhận cả chữ thường vd. `sarah.reign`). `api._sanitize_view_filters`'s `valid_account()` dựa vào
`ACCOUNT_CODE_RE` chỉ nhận chữ hoa để tự chặn `"all"` viết thường lọt qua so sánh case-sensitive
`!= "ALL"`. Từng thử gộp hai pattern (thêm `a-z` vào `ACCOUNT_CODE_RE`) — làm `"all"` lọt qua,
bắt được nhờ `test_saved_views_are_csrf_protected_scoped_and_sanitized` khi chạy full suite chứ
không phải lúc code review.

Tên tệp export TikTok (`affiliate_orders*.xlsx`) cũng có ba bản tay, không chia sẻ được code vì
khác ngôn ngữ: `parser.FILENAME_PATTERN` (Python, thẩm quyền cuối — server luôn kiểm lại),
`imports.tsx`'s `EXPORT_FILENAME_RE` (JS, pre-check phía trình duyệt), `MainActivity.java`'s
`isValidSyncFilename` (Java, lọc trước khi upload từ thư mục đồng bộ Android). Lệch giữa ba bản
chỉ gây bỏ sót/thử thừa, không phải lỗ hổng — nhưng vẫn nên sửa cả ba khi đổi quy tắc.

## Android: Storage Access Framework (thư mục đồng bộ)

**Cạm bẫy đã trả giá:** từ Android 11, hệ điều hành **khoá cứng** nút "Sử dụng thư mục này" khi
người dùng chọn thẳng thư mục `Download` gốc qua `ACTION_OPEN_DOCUMENT_TREE` — cùng loại giới hạn
với root bộ nhớ ngoài và `Android/data`/`Android/obb`. Đây là hạn chế của OS, **không sửa được từ
phía app**, và `EXTRA_INITIAL_URI` trỏ thẳng vào đó không né được (chỉ đỡ vài bước điều hướng, tới
đúng chỗ vẫn bị khoá). Người dùng bắt buộc phải đi tiếp vào một thư mục **con** bên trong Download
(có sẵn hoặc tạo mới ngay trong trình chọn) mới chọn được. `MainActivity.launchSyncFolderPicker()`
+ `android-sync-folder.tsx` đã dặn trước điều này trong UI — đừng gợi ý "chọn Download" trống
không nữa, luôn kèm "thư mục con bên trong Download".

Nguồn: [Android Developers — Storage updates in Android 11](https://developer.android.com/about/versions/11/privacy/storage),
[CommonsWare — SAF Restrictions](https://commonsware.com/R/pages/chap-scoped-006).

## Gate cục bộ trước khi đề nghị push

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m scripts.sync_version --check
pnpm --dir web lint
pnpm --dir web exec tsc --noEmit
pnpm --dir web test:unit
pnpm --dir web build          # e2e phục vụ từ web/out, phải build lại trước khi chạy e2e
pnpm --dir web test:e2e
pnpm --dir web audit --prod
```

`test:e2e` bỏ qua tag `@shots`. Sửa CSS mà quên `pnpm --dir web build` thì e2e vẫn chạy trên
bản build cũ và cho kết quả sai lệch.
