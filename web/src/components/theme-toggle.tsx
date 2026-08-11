"use client";

import * as RadioGroup from "@radix-ui/react-radio-group";
import { Monitor, Moon, Sun } from "lucide-react";
import { useState } from "react";
import type { UiPreferences } from "@/lib/api";

export type Theme = UiPreferences["theme"];

const STORAGE_KEY = "tiktok-affiliate-theme";
const LABELS: Record<Theme, { title: string; description: string }> = {
  system: { title: "Theo hệ thống", description: "Tự đổi theo cài đặt sáng/tối của thiết bị." },
  light: { title: "Sáng", description: "Nền sáng, phù hợp khi đối soát ban ngày." },
  dark: { title: "Tối", description: "Giảm chói cho ca trực tối hoặc màn hình OLED." },
};

export function applyThemePreference(theme: Theme) {
  if (typeof document === "undefined") return;
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Database remains the source of truth; local storage only prevents first-paint flash.
  }
}

function ThemeIcon({ theme }: { theme: Theme }) {
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  return <Icon size={18} aria-hidden="true" />;
}

export function ThemePreferences({ value, onChange }: { value: Theme; onChange: (theme: Theme) => Promise<void> }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function select(theme: Theme) {
    if (saving || theme === value) return;
    setSaving(true);
    setError("");
    try {
      await onChange(theme);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể lưu chế độ giao diện.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="section panel preference-panel" aria-labelledby="appearance-heading" aria-busy={saving}>
      <div className="section-heading">
        <div>
          <p className="section-label">Cá nhân hóa</p>
          <h2 id="appearance-heading">Chế độ màu</h2>
          <p>Tuỳ chọn được lưu theo người dùng và chỉ đặt tại Cài đặt để tránh đổi nhầm khi đang vận hành.</p>
        </div>
        <span className="preference-save-state" aria-live="polite">{saving ? "Đang lưu…" : "Tự động lưu"}</span>
      </div>
      <RadioGroup.Root className="theme-preference-grid" value={value} onValueChange={(theme) => void select(theme as Theme)} aria-label="Chọn chế độ giao diện">
        {(Object.keys(LABELS) as Theme[]).map((item) => (
          <RadioGroup.Item className="theme-preference-card" value={item} key={item} disabled={saving}>
            <span className="theme-preference-icon"><ThemeIcon theme={item} /></span>
            <span><strong>{LABELS[item].title}</strong><small>{LABELS[item].description}</small></span>
            <span className="theme-radio-dot" aria-hidden="true" />
          </RadioGroup.Item>
        ))}
      </RadioGroup.Root>
      {error ? <p className="filter-error" role="alert">{error}</p> : null}
    </section>
  );
}
