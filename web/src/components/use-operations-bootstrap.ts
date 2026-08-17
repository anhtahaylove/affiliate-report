"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  type CurrentUser,
  loadCurrentUser,
  loadMeta,
  loadUiPreferences,
  saveUiPreferences,
  type MetaResponse,
  type UiPreferences,
} from "@/lib/api";
import { errorMessage } from "@/lib/format";
import { applyThemePreference } from "@/components/theme-toggle";

export type UiPreferenceChanges = Partial<Pick<UiPreferences, "theme" | "sidebar_collapsed" | "dashboard_layout">>;

export function useOperationsBootstrap() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [metaData, setMetaData] = useState<MetaResponse | null>(null);
  const [preferences, setPreferences] = useState<UiPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const [authError, setAuthError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    async function load() {
      try {
        const [currentUser, meta, uiPreferences] = await Promise.all([loadCurrentUser(), loadMeta(), loadUiPreferences()]);
        setUser(currentUser);
        setMetaData(meta);
        setPreferences(uiPreferences);
        applyThemePreference(uiPreferences.theme);
        setConnectionError("");
        setAuthError("");
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 401) setAuthError(reason.message || "Phiên đăng nhập đã hết hạn.");
        else setConnectionError(errorMessage(reason, "Không thể tải cấu hình ứng dụng."));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [reloadToken]);

  const retry = useCallback(() => setReloadToken((token) => token + 1), []);
  const refreshAccountMetadata = useCallback(async () => {
    const refreshed = await loadMeta();
    setMetaData(refreshed);
  }, []);
  const updatePreferences = useCallback(async (changes: UiPreferenceChanges) => {
    const updated = await saveUiPreferences(changes);
    setPreferences(updated);
    applyThemePreference(updated.theme);
  }, []);

  return {
    authError,
    connectionError,
    loading,
    metaData,
    preferences,
    refreshAccountMetadata,
    retry,
    updatePreferences,
    user,
  };
}
