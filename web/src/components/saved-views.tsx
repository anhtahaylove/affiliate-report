"use client";

import { Bookmark, ChevronDown, Save, Trash2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { createSavedView, deleteSavedView, loadSavedViews, type SavedReportView, type SavedViewRoute, updateSavedView } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";

const ARRAY_FILTERS = new Set(["account", "status"]);
const NUMBER_FILTERS = new Set(["size", "top"]);
const COMMON_FILTERS = ["account", "status", "start", "end", "month"];

export function SavedViews({ route }: { route: SavedViewRoute }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [views, setViews] = useState<SavedReportView[]>([]);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [makeDefault, setMakeDefault] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const current = views.find((view) => String(view.id) === selected);
  const currentFilters = captureFilters(searchParams, route);

  useEffect(() => {
    let active = true;
    loadSavedViews(route).then((response) => {
      if (!active) return;
      setViews(response.items);
      const preferred = response.items.find((item) => item.is_default);
      if (preferred) setSelected(String(preferred.id));
    }).catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : "Không thể tải chế độ xem.");
    });
    return () => { active = false; };
  }, [route]);

  function apply(view: SavedReportView | undefined) {
    if (!view) return;
    const params = new URLSearchParams();
    for (const [key, raw] of Object.entries(view.filters)) {
      if (key === "schema") continue;
      const values = Array.isArray(raw) ? raw : [raw];
      for (const value of values) params.append(key, String(value));
    }
    router.push(`${pathname}${params.size ? `?${params.toString()}` : ""}`);
  }

  async function saveNew() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const created = await createSavedView({ route, name: name.trim(), filters: currentFilters, is_default: makeDefault });
      setViews((items) => [created, ...items.map((item) => makeDefault ? { ...item, is_default: false } : item)]);
      setSelected(String(created.id));
      setName("");
      setMakeDefault(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể lưu chế độ xem.");
    } finally {
      setBusy(false);
    }
  }

  async function overwrite() {
    if (!current || busy) return;
    setBusy(true);
    setError("");
    try {
      const updated = await updateSavedView(current.id, { filters: currentFilters });
      setViews((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể cập nhật chế độ xem.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!current) return;
    setBusy(true);
    setError("");
    try {
      await deleteSavedView(current.id);
      setViews((items) => items.filter((item) => item.id !== current.id));
      setSelected("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể xóa chế độ xem.");
    } finally {
      setBusy(false);
      setConfirmingRemove(false);
    }
  }

  return (
    <section className="saved-views-bar panel" aria-label="Chế độ xem đã lưu" aria-busy={busy}>
      <button
        className="saved-views-mobile-toggle"
        type="button"
        aria-expanded={mobileOpen}
        aria-controls={`saved-views-content-${route}`}
        onClick={() => setMobileOpen((value) => !value)}
      >
        <span><Bookmark size={17} aria-hidden="true" /><strong>Chế độ xem</strong><small>{current?.name ?? "Phạm vi hiện tại"}</small></span>
        <ChevronDown size={18} aria-hidden="true" />
      </button>
      <div className={`saved-views-content${mobileOpen ? " is-open" : ""}`} id={`saved-views-content-${route}`}>
        <div className="saved-view-picker"><Bookmark size={17} aria-hidden="true" /><label htmlFor={`saved-view-${route}`}>Chế độ xem</label><select id={`saved-view-${route}`} value={selected} onChange={(event) => setSelected(event.target.value)}><option value="">Chọn chế độ xem…</option>{views.map((view) => <option key={view.id} value={view.id}>{view.is_default ? "★ " : ""}{view.name}</option>)}</select><button type="button" onClick={() => apply(current)} disabled={!current || busy}>Áp dụng</button></div>
        <div className="saved-view-create"><input aria-label="Tên chế độ xem mới" value={name} onChange={(event) => setName(event.target.value)} maxLength={64} placeholder="Lưu phạm vi hiện tại…" /><label><input type="checkbox" checked={makeDefault} onChange={(event) => setMakeDefault(event.target.checked)} />Mặc định</label><button className="primary" type="button" onClick={() => void saveNew()} disabled={!name.trim() || busy}><Save size={16} aria-hidden="true" />Lưu mới</button>{current ? <><button type="button" onClick={() => void overwrite()} disabled={busy}>Ghi đè</button><button className="danger-action" type="button" onClick={() => setConfirmingRemove(true)} disabled={busy} aria-label="Xóa chế độ xem"><Trash2 size={16} aria-hidden="true" /></button></> : null}</div>
      </div>
      {error ? <p className="filter-error" role="alert">{error}</p> : null}
      <ConfirmDialog
        open={confirmingRemove}
        title={`Xóa chế độ xem "${current?.name ?? ""}"?`}
        confirmLabel="Xóa chế độ xem"
        busy={busy}
        onCancel={() => setConfirmingRemove(false)}
        onConfirm={() => void remove()}
      >
        <p>Bộ lọc đã lưu này sẽ bị xóa. Dữ liệu báo cáo không bị ảnh hưởng.</p>
      </ConfirmDialog>
    </section>
  );
}

function captureFilters(params: URLSearchParams, route: SavedViewRoute): Record<string, unknown> {
  const output: Record<string, unknown> = { schema: 1 };
  const allowed = new Set([...COMMON_FILTERS, ...(route === "orders" ? ["search", "sort", "direction", "size"] : route === "analytics" ? ["group_by", "top"] : [])]);
  const keys = new Set(Array.from(params.keys()).filter((key) => allowed.has(key)));
  for (const key of keys) {
    if (ARRAY_FILTERS.has(key)) output[key] = params.getAll(key);
    else {
      const value = params.get(key);
      if (value == null || value === "") continue;
      output[key] = NUMBER_FILTERS.has(key) ? Number(value) : value;
    }
  }
  return output;
}
