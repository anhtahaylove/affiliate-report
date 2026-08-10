"use client";

import { useSyncExternalStore } from "react";

type Theme = "system" | "light" | "dark";

const STORAGE_KEY = "tiktok-affiliate-theme";
const NEXT: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const LABELS: Record<Theme, string> = { system: "Theo hệ thống", light: "Sáng", dark: "Tối" };

// Nguồn sự thật là thuộc tính data-theme trên <html>, do script trong <head> đặt trước khi vẽ.
let listeners: Array<() => void> = [];

function subscribe(callback: () => void) {
  listeners.push(callback);
  return () => {
    listeners = listeners.filter((item) => item !== callback);
  };
}

function readTheme(): Theme {
  const value = document.documentElement.getAttribute("data-theme");
  return value === "dark" || value === "light" ? value : "system";
}

function setTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
    window.localStorage.removeItem(STORAGE_KEY);
  } else {
    root.setAttribute("data-theme", theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }
  listeners.forEach((listener) => listener());
}

export function ThemeToggle() {
  const theme = useSyncExternalStore<Theme>(subscribe, readTheme, () => "system");
  return (
    <button className="theme-toggle" type="button" onClick={() => setTheme(NEXT[theme])} aria-label={`Giao diện: ${LABELS[theme]}. Bấm để đổi.`}>
      {LABELS[theme]}
    </button>
  );
}
