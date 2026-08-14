import assert from "node:assert/strict";
import test from "node:test";

import { deriveUpdatePresentation } from "./update-presentation.ts";

const baseStatus = {
  current_version: "2.1.1",
  latest_version: "2.1.1",
  available: false,
  installable: true,
  automatic_install_supported: true,
  release_name: "v2.1.1",
  release_url: "https://example.test/releases/v2.1.1",
  published_at: "2026-08-14T11:50:00Z",
  notes: null,
  source_repo: "example/updates",
};

const idleProgress = {
  schema: "tiktok-affiliate-report.update-status.v1",
  phase: "idle",
  current_version: "2.1.1",
  target_version: null,
  bytes_downloaded: 0,
  bytes_total: 0,
  percent: null,
  error: null,
  error_action: null,
  updated_at: null,
};

function derive(overrides = {}) {
  return deriveUpdatePresentation({
    status: baseStatus,
    progress: idleProgress,
    busy: false,
    installing: false,
    reconnecting: false,
    issueKind: null,
    hasIssue: false,
    now: new Date("2026-08-14T12:00:00Z"),
    ...overrides,
  });
}

test("stale completed progress never labels an older target as the latest version", () => {
  const view = derive({
    status: { ...baseStatus, latest_version: "2.0.29" },
    progress: {
      ...idleProgress,
      current_version: "2.0.29",
      phase: "installed",
      target_version: "2.0.29",
      bytes_downloaded: 46_020_826,
      bytes_total: 46_020_826,
      percent: 100,
      updated_at: "2026-08-13T15:48:12Z",
    },
  });

  assert.equal(view.state, "latest");
  assert.equal(view.currentVersion, "2.1.1");
  assert.equal(view.availableVersion, null);
  assert.equal(view.availabilityText, "Không có bản mới hơn");
  assert.equal(view.feedBehindCurrent, true);
  assert.equal(view.showWorkflow, false);
  assert.equal(view.showDownloadProgress, false);
});

test("equal versions render a quiet latest state without an idle timeline", () => {
  const view = derive();

  assert.equal(view.state, "latest");
  assert.equal(view.availabilityText, "Không có bản mới hơn");
  assert.equal(view.showWorkflow, false);
  assert.equal(view.showDownloadProgress, false);
});

test("a newer signed release is available but manual-only when automatic install is unsupported", () => {
  const automatic = derive({
    status: { ...baseStatus, latest_version: "2.1.2", available: true },
  });
  const manual = derive({
    status: {
      ...baseStatus,
      latest_version: "2.1.2",
      available: true,
      automatic_install_supported: false,
    },
  });

  assert.equal(automatic.state, "available");
  assert.equal(automatic.availableVersion, "2.1.2");
  assert.equal(manual.state, "manual");
  assert.equal(manual.availableVersion, "2.1.2");
});

test("checking and offline states remain distinct", () => {
  assert.equal(derive({ status: null, progress: null, busy: true }).state, "checking");
  assert.equal(derive({ status: null, progress: null, issueKind: "offline", hasIssue: true }).state, "offline");
});

for (const [phase, percent] of [["downloading", 0], ["downloading", 35], ["downloading", 100], ["verifying", 100], ["installing", 100], ["restarting", 100]]) {
  test(`${phase} ${percent}% keeps the workflow active and only download shows the progress bar`, () => {
    const view = derive({
      installing: true,
      progress: {
        ...idleProgress,
        phase,
        target_version: "2.1.2",
        bytes_downloaded: Math.round(1_000 * percent / 100),
        bytes_total: 1_000,
        percent,
        updated_at: "2026-08-14T11:59:30Z",
      },
    });

    assert.equal(view.state, "active");
    assert.equal(view.showWorkflow, true);
    assert.equal(view.showDownloadProgress, phase === "downloading");
  });
}

test("reconnecting and relevant failures provide dedicated recovery states", () => {
  const progress = {
    ...idleProgress,
    phase: "installing",
    target_version: "2.1.2",
    bytes_total: 1_000,
    percent: 100,
  };
  assert.equal(derive({ installing: true, reconnecting: true, progress }).state, "reconnecting");
  assert.equal(derive({
    progress: { ...progress, phase: "failed", error: "Cập nhật chưa hoàn tất." },
    hasIssue: true,
  }).state, "failed");
});

test("a fresh completion may show its workflow briefly but never a redundant 100% download bar", () => {
  const view = derive({
    progress: {
      ...idleProgress,
      phase: "installed",
      target_version: "2.1.1",
      bytes_downloaded: 1_000,
      bytes_total: 1_000,
      percent: 100,
      updated_at: "2026-08-14T11:58:00Z",
    },
  });

  assert.equal(view.state, "completed");
  assert.equal(view.showWorkflow, true);
  assert.equal(view.showDownloadProgress, false);
});
