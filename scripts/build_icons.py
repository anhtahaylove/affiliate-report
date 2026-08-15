"""Sinh toàn bộ icon Windows, PWA và Android từ hai file SVG nguồn.

`packaging/icon/icon.svg` và `icon-foreground.svg` là nguồn sự thật duy nhất. Mọi PNG và
.ico trong repo đều do script này ghi ra — sửa tay vào ảnh đã sinh sẽ bị lần chạy sau đè mất.

Trước đây icon Windows và icon Android là hai bộ rời nhau: Windows dùng packaging/app.ico
còn Android vẫn giữ nguyên icon mặc định của Android Studio, nên hai nền tảng trông khác hẳn.

    python -m scripts.build_icons            # ghi lại toàn bộ icon
    python -m scripts.build_icons --check    # chỉ báo lệch, exit 1 nếu có

Rasterize bằng Chromium của Playwright (repo không có cairosvg, còn Playwright thì đã sẵn
cho e2e), rồi đóng .ico bằng Pillow.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
ICON_DIR = REPO / "packaging" / "icon"
MASTER = ICON_DIR / "icon.svg"
FOREGROUND = ICON_DIR / "icon-foreground.svg"
# Node resolve import theo vị trí file chứ không theo cwd, nên bộ rasterize phải nằm trong
# web/ mới thấy được @playwright/test trong web/node_modules.
RENDERER = REPO / "web" / "scripts" / "render-icon.mjs"
WEB_DIR = REPO / "web"
ANDROID_RES = REPO / "android" / "native" / "app" / "src" / "main" / "res"

# Windows nhúng nhiều độ phân giải trong một .ico; 16 và 32 là cỡ thật trên taskbar.
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
# PWA + ảnh thương hiệu trong sidebar (app-shell dùng /icon-192.png).
WEB_ICONS = {192: WEB_DIR / "public" / "icon-192.png", 512: WEB_DIR / "public" / "icon-512.png"}
# Mật độ màn hình Android: mipmap ic_launcher là 48dp, foreground của adaptive icon là 108dp.
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def outputs() -> list[dict]:
    specs: list[dict] = []
    for size in ICO_SIZES:
        specs.append({"svg": str(MASTER), "size": size, "kind": "ico-part"})
    for size, path in WEB_ICONS.items():
        specs.append({"svg": str(MASTER), "size": size, "out": str(path)})
    for density, scale in DENSITIES.items():
        folder = ANDROID_RES / f"mipmap-{density}"
        specs.append({"svg": str(MASTER), "size": round(48 * scale), "out": str(folder / "ic_launcher.png")})
        specs.append({"svg": str(MASTER), "size": round(48 * scale), "out": str(folder / "ic_launcher_round.png"), "round": True})
        specs.append({"svg": str(FOREGROUND), "size": round(108 * scale), "out": str(folder / "ic_launcher_foreground.png")})
    return specs


def render(specs: list[dict], workdir: Path) -> None:
    payload = []
    for index, spec in enumerate(specs):
        out = spec.get("out") or str(workdir / f"ico-{spec['size']}.png")
        spec["resolved"] = out
        payload.append({"svg": spec["svg"], "size": spec["size"], "out": out, "round": bool(spec.get("round"))})
    result = subprocess.run(
        ["node", str(RENDERER)],
        cwd=WEB_DIR,  # Playwright nằm trong web/node_modules
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Rasterize thất bại:\n{result.stdout}\n{result.stderr}")


def build_ico(parts: list[Path], target: Path) -> None:
    largest = Image.open(parts[-1]).convert("RGBA")
    largest.save(target, format="ICO", sizes=[(size, size) for size in ICO_SIZES])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="chỉ báo lệch, không ghi")
    args = parser.parse_args()

    for source in (MASTER, FOREGROUND, RENDERER):
        if not source.is_file():
            raise SystemExit(f"Thiếu nguồn icon: {source}")

    with tempfile.TemporaryDirectory() as raw:
        workdir = Path(raw)
        specs = outputs()
        if args.check:
            for spec in specs:
                if spec.get("out") and not Path(spec["out"]).is_file():
                    print(f"Thiếu icon đã sinh: {spec['out']}", file=sys.stderr)
                    return 1
            if not (REPO / "packaging" / "app.ico").is_file():
                print("Thiếu packaging/app.ico", file=sys.stderr)
                return 1
            print("Đủ icon đã sinh.")
            return 0

        staged = {spec["size"]: workdir / f"ico-{spec['size']}.png" for spec in specs if spec.get("kind") == "ico-part"}
        render(specs, workdir)
        build_ico([staged[size] for size in ICO_SIZES], REPO / "packaging" / "app.ico")

    written = [spec["resolved"] for spec in specs if spec.get("out")]
    print(f"Đã sinh {len(written) + 1} tệp icon từ {MASTER.name}:")
    print(f"  packaging/app.ico ({', '.join(str(size) for size in ICO_SIZES)})")
    for path in written:
        print(f"  {Path(path).relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
