"use client";

import { useEffect, useRef, useState } from "react";
import { errorMessage } from "@/lib/format";

/**
 * Cache theo khoá bộ lọc dùng chung cho mọi trang. Quay lại một phạm vi đã xem thì số liệu cũ
 * hiện ra ngay rồi được làm mới ngầm, thay vì mỗi lần đổi trang lại tải trắng từ đầu.
 */
const cache = new Map<string, unknown>();
// App desktop mở cả ngày, mỗi tổ hợp bộ lọc giữ một payload analytics khá nặng; giữ 30 mục gần
// nhất là đủ cho việc đi tới đi lui giữa các trang mà không để cache phình vô hạn.
const CACHE_LIMIT = 30;

function remember(key: string, value: unknown) {
  cache.delete(key);
  cache.set(key, value);
  while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
}

export function invalidateApiCache() {
  cache.clear();
}

export function useApi<T>(key: string, load: () => Promise<T>, fallback: string) {
  const [result, setResult] = useState<{ key: string; data: T | null; error: string } | null>(null);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const data = await loadRef.current();
        remember(key, data);
        if (active) setResult({ key, data, error: "" });
      } catch (reason) {
        if (active) setResult({ key, data: null, error: errorMessage(reason, fallback) });
      }
    })();
    return () => {
      active = false;
    };
  }, [key, fallback]);

  const fresh = result?.key === key ? result : null;
  const data = (fresh?.data ?? (cache.get(key) as T | undefined)) ?? null;
  return { data, error: fresh?.error ?? "", loading: !fresh && data === null };
}
