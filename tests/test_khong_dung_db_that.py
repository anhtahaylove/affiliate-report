"""Bằng chứng cho chốt chặn ở conftest.py.

Bỏ tests/conftest.py đi rồi chạy lại thì test này ĐỎ: get_engine() không có DATABASE_URL sẽ
rơi về DEFAULT_DATABASE_URL, tức data/tiktok_affiliate_report.db — đúng database người dùng
đang dùng thật, và init_db() sẽ chạy migration lên nó.
"""

from __future__ import annotations

# Cố ý KHÔNG nhập hằng số từ conftest: test phải đỏ vì chốt chặn mất tác dụng, chứ không phải
# vì thiếu import.
from tiktok_affiliate_report.db import get_engine

REAL_DATABASE_PATH = "data/tiktok_affiliate_report.db"


def test_engine_mac_dinh_khong_tro_vao_database_that() -> None:
    assert REAL_DATABASE_PATH not in str(get_engine().url)
