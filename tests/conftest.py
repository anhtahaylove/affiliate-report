"""Chặn bộ test chạm vào database thật.

db.py đặt DEFAULT_DATABASE_URL = "sqlite:///data/tiktok_affiliate_report.db", đường dẫn
tương đối so với thư mục làm việc. Chạy pytest từ gốc repo thì get_engine() không có
DATABASE_URL sẽ mở đúng database thật, và init_db() chạy migration lên nó. Đã xảy ra thật:
một migration DROP COLUMN chạy vào dữ liệu 5.508 dòng của người dùng.

Đổi hướng mặc định sang thư mục tạm. Test nào cần PostgreSQL vẫn tự truyền URL riêng nên
không bị ảnh hưởng, và DATABASE_URL do CI đặt trỏ chỗ khác cũng được giữ nguyên.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

REAL_DATABASE_PATH = "data/tiktok_affiliate_report.db"


def _huong_ra_ngoai_db_that() -> None:
    hien_tai = os.environ.get("DATABASE_URL", "")
    # Chưa đặt thì db.py rơi về database thật; đặt rồi mà vẫn trỏ vào nó thì cũng chặn.
    if hien_tai and REAL_DATABASE_PATH not in hien_tai:
        return
    thu_muc = Path(tempfile.mkdtemp(prefix="tiktok-test-"))
    os.environ["DATABASE_URL"] = f"sqlite:///{(thu_muc / 'test.db').as_posix()}"


_huong_ra_ngoai_db_that()
