"""Đồng bộ mọi nơi ghim phiên bản từ một nguồn sự thật duy nhất.

`affiliate_report/version.py` là nguồn. Mọi chỗ khác — installer, APK, script CI,
workflow, README — đều dẫn xuất từ đó và do file này ghi lại.

Trước khi có script này, bump phiên bản là sửa tay 19 file. Bản v2.1.2 vẫn sót hai
regex escape dấu chấm (`APP_VERSION = "2\\.1\\.2"`) vì phép thay chuỗi literal
"2.1.1" không chạm tới chúng, và gate Android hỏng ở phút thứ 20 của CI.

    python -m scripts.sync_version            # ghi lại các chỗ dẫn xuất
    python -m scripts.sync_version --check    # chỉ báo lệch, exit 1 nếu có

`--check` được test hợp đồng đóng gói gọi, nên lệch sẽ hỏng ngay ở test cục bộ.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO / "affiliate_report" / "version.py"


def read_app_version() -> str:
    """Đọc thẳng file, không import.

    `import affiliate_report.version` có thể trả về bytecode cache cũ trong
    __pycache__ — đã gặp thật: version.py trên đĩa là 2.1.2 nhưng import ra 2.1.3, và
    sync sẽ lặng lẽ đồng bộ cả repo về sai phiên bản. Công cụ mà nhiệm vụ là "file trên
    đĩa là nguồn sự thật" thì không được đi qua lớp cache nào.
    """
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit(f"Không đọc được APP_VERSION trong {VERSION_FILE}")
    return match.group(1)


APP_VERSION = read_app_version()

# Android versionCode phải tăng đơn điệu và là số nguyên. Quy ước của repo:
# 2.1.2 -> 2001002. Suy ra được nên không ghim tay ở đâu cả.
VERSION_CODE_SCALE = (1_000_000, 1_000, 1)


def parse_version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise SystemExit(f"APP_VERSION không hợp lệ: {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def version_code(parts: tuple[int, int, int]) -> int:
    return sum(part * scale for part, scale in zip(parts, VERSION_CODE_SCALE))


def escaped(value: str) -> str:
    """Dạng dùng trong regex của workflow: 2.1.2 -> 2\\.1\\.2."""
    return value.replace(".", r"\.")


VERSION = APP_VERSION
PARTS = parse_version(VERSION)
CODE = str(version_code(PARTS))
# Bước synthetic upgrade của gate Android cài bản N rồi nâng lên N+1 bằng cùng khóa ký.
# Bản N+1 chỉ tồn tại trong CI, không bao giờ được phát hành.
NEXT = f"{PARTS[0]}.{PARTS[1]}.{PARTS[2] + 1}"
NEXT_CODE = str(version_code((PARTS[0], PARTS[1], PARTS[2] + 1)))

SEMVER = r"\d+\.\d+\.\d+"
ESC_SEMVER = r"\d+\\\.\d+\\\.\d+"
# File được ghi lại theo byte để giữ nguyên BOM, nên không có universal-newline của
# Python: pattern nhiều dòng phải tự chịu được cả LF lẫn CRLF.
EOL = r"\r?\n"

# (đường dẫn, [(pattern, replacement), ...]). Mỗi pattern phải neo đủ chặt để chỉ
# khớp đúng chỗ ghim phiên bản của ứng dụng — không bao giờ chạm vào phiên bản của
# dependency (pandas 2.1.3, is-docker ^2.1.1, @ionic/utils-process 2.1.12, ms 2.1.3).
RULES: list[tuple[str, list[tuple[str, str]]]] = [
    ("packaging/AffiliateReport.iss", [
        (rf'(#define MyAppVersion "){SEMVER}(")', rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("packaging/build_installer.ps1", [
        (rf"(\[string\]\$AppVersion = '){SEMVER}(')", rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("android/package.json", [
        (rf'("version": "){SEMVER}(")', rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("android/package-lock.json", [
        # Chỉ hai chỗ đi kèm tên gói; các "version" khác trong lock là dependency.
        (rf'("name": "affiliate-report-android",{EOL}(\s+)"version": "){SEMVER}(")',
         rf"\g<1>{VERSION}\g<3>"),
    ]),
    ("android/native/app/build.gradle", [
        (r"(versionCode )\d+", rf"\g<1>{CODE}"),
        (rf'(versionName "){SEMVER}(")', rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("android/native/app/src/main/java/vn/io/huuhungn/affiliatereport/AffiliateReportApplication.java", [
        (rf'(WEB_VERSION = "){SEMVER}(")', rf"\g<1>{VERSION}\g<2>"),
    ]),
    (".github/workflows/windows-installer-smoke.yml", [
        (rf'(current_version:{EOL}\s+description: [^\r\n]*{EOL}\s+required: true{EOL}\s+default: "){SEMVER}(")',
         rf"\g<1>{VERSION}\g<2>"),
    ]),
    (".github/workflows/windows-updater-ui-smoke.yml", [
        (rf'(current_version:{EOL}\s+description: [^\r\n]*{EOL}\s+required: true{EOL}\s+default: "){SEMVER}(")',
         rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("docs/android-runtime.md", [
        (rf"(AffiliateReport-v){SEMVER}(-arm64\.apk)", rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("README.md", [
        (rf"(AffiliateReportSetup-v){SEMVER}(\.exe)", rf"\g<1>{VERSION}\g<2>"),
        (rf"(AffiliateReport-v){SEMVER}(-arm64\.apk)", rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("scripts/ci/build_android_candidate.ps1", [
        (rf'(\$version = "){SEMVER}(")', rf"\g<1>{VERSION}\g<2>"),
        (r'(\$versionCode = ")\d+(")', rf"\g<1>{CODE}\g<2>"),
    ]),
    ("scripts/ci/android_emulator_smoke.sh", [
        (rf"(AffiliateReport-v){SEMVER}(-x86_64-debug\.apk)", rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("scripts/ci/android_runtime_smoke.py", [
        (rf'(!= "){SEMVER}(")', rf"\g<1>{VERSION}\g<2>"),
        (rf'(default="){SEMVER}(")', rf"\g<1>{VERSION}\g<2>"),
    ]),
    ("scripts/ci/android_signed_upgrade_smoke.sh", [
        (rf'(current="\$GITHUB_WORKSPACE/candidate/AffiliateReport-v){SEMVER}(-x86_64-release\.apk")',
         rf"\g<1>{VERSION}\g<2>"),
        (rf'(target="\$GITHUB_WORKSPACE/candidate/AffiliateReport-v){SEMVER}(-x86_64-release\.apk")',
         rf"\g<1>{NEXT}\g<2>"),
        (rf"(--phase seed --package \"\$package\" --expected-version ){SEMVER}", rf"\g<1>{VERSION}"),
        (rf"(--phase persist --package \"\$package\" --expected-version ){SEMVER}", rf"\g<1>{NEXT}"),
        (r"(versionCode=)\d+", rf"\g<1>{NEXT_CODE}"),
    ]),
    ("scripts/ci/verify_android_scaffold.py", [
        (r"('versionCode )\d+(')", rf"\g<1>{CODE}\g<2>"),
        (rf"('versionName \"){SEMVER}(\"')", rf"\g<1>{VERSION}\g<2>"),
    ]),
    (".github/workflows/android-candidate.yml", [
        (rf"(AffiliateReport-v){SEMVER}(-x86_64-debug\.apk)", rf"\g<1>{VERSION}\g<2>"),
        (rf"(AffiliateReport-v){SEMVER}(-arm64\.apk)", rf"\g<1>{VERSION}\g<2>"),
        # Hai dòng artifact upgrade: dòng trên là bản N, dòng dưới là bản N+1.
        (rf"(artifacts/android/AffiliateReport-v){SEMVER}(-x86_64-release\.apk{EOL}\s+artifacts/android/AffiliateReport-v){SEMVER}(-x86_64-release\.apk)",
         rf"\g<1>{VERSION}\g<2>{NEXT}\g<3>"),
        # Guard "đúng bản N" — regex escape dấu chấm, chính chỗ bump v2.1.2 bỏ sót.
        (rf"(-notmatch 'APP_VERSION = \"){ESC_SEMVER}(\"')", rf"\g<1>{escaped(VERSION)}\g<2>"),
        (r"(-notmatch 'versionCode )\d+(')", rf"\g<1>{CODE}\g<2>"),
        (rf"(-notmatch 'versionName \"){ESC_SEMVER}(\"')", rf"\g<1>{escaped(VERSION)}\g<2>"),
        (rf"(Synthetic Android upgrade source is not the exact ){SEMVER}( candidate)",
         rf"\g<1>{VERSION}\g<2>"),
        # Ba dòng .Replace(N -> N+1) dựng bản synthetic.
        (rf"(\.Replace\('APP_VERSION = \"){SEMVER}(\"', 'APP_VERSION = \"){SEMVER}(\"'\))",
         rf"\g<1>{VERSION}\g<2>{NEXT}\g<3>"),
        (r"(\.Replace\('versionCode )\d+(', 'versionCode )\d+(')", rf"\g<1>{CODE}\g<2>{NEXT_CODE}\g<3>"),
        (rf"(\.Replace\('versionName \"){SEMVER}(\"', 'versionName \"){SEMVER}(\"')",
         rf"\g<1>{VERSION}\g<2>{NEXT}\g<3>"),
        (rf"(\.Replace\('\$version = \"){SEMVER}(\"', '\$version = \"){SEMVER}(\"')",
         rf"\g<1>{VERSION}\g<2>{NEXT}\g<3>"),
        (r"(\.Replace\('\$versionCode = \")\d+(\"', '\$versionCode = \")\d+(\")",
         rf"\g<1>{CODE}\g<2>{NEXT_CODE}\g<3>"),
        # Kiểm metadata APK bằng aapt2 — cũng là regex escape dấu chấm.
        (rf"(versionCode=')\d+('\.\*versionName='){ESC_SEMVER}(')",
         rf"\g<1>{CODE}\g<2>{escaped(VERSION)}\g<3>"),
        (rf"(APK package/version metadata is not the v){SEMVER}( release contract)",
         rf"\g<1>{VERSION}\g<2>"),
        (rf"(Same-key synthetic ){SEMVER}( to ){SEMVER}( upgrade)",
         rf"\g<1>{VERSION}\g<2>{NEXT}\g<3>"),
    ]),
]


def apply(check_only: bool) -> int:
    drift: list[str] = []
    written: list[str] = []
    for relative, rules in RULES:
        path = REPO / relative
        raw = path.read_bytes()
        # Vài .ps1 phải giữ UTF-8 BOM, nếu không Windows PowerShell 5.1 đọc theo ANSI và
        # chuỗi tiếng Việt vỡ thành lỗi parse. Ghi lại mà đánh rơi BOM là tự đặt lại bẫy.
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        original = raw.decode("utf-8-sig" if has_bom else "utf-8")
        text = original
        for pattern, replacement in rules:
            text, count = re.subn(pattern, replacement, text)
            if count == 0:
                raise SystemExit(
                    f"{relative}: pattern không khớp chỗ nào, hợp đồng phiên bản đã đổi hình: {pattern}"
                )
        if text == original:
            continue
        if check_only:
            drift.append(relative)
        else:
            path.write_bytes((b"\xef\xbb\xbf" if has_bom else b"") + text.encode("utf-8"))
            written.append(relative)

    if check_only:
        if drift:
            print(f"Lệch so với APP_VERSION={VERSION}:", file=sys.stderr)
            for item in drift:
                print(f"  {item}", file=sys.stderr)
            print("Chạy: python -m scripts.sync_version", file=sys.stderr)
            return 1
        print(f"Khớp APP_VERSION={VERSION} (versionCode={CODE}, synthetic={NEXT}).")
        return 0

    if written:
        print(f"Đã đồng bộ về APP_VERSION={VERSION} (versionCode={CODE}, synthetic={NEXT}):")
        for item in written:
            print(f"  {item}")
    else:
        print(f"Không có gì phải sửa; đã khớp APP_VERSION={VERSION}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="chỉ báo lệch, không ghi")
    return apply(parser.parse_args().check)


if __name__ == "__main__":
    raise SystemExit(main())
