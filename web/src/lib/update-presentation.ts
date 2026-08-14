import type { UpdateProgress, UpdateStatus } from "./api";

export type UpdateIssueKind = "offline" | "permission" | "source" | "busy" | "generic" | null;

export type UpdateExperienceState =
  | "checking"
  | "latest"
  | "available"
  | "manual"
  | "active"
  | "reconnecting"
  | "completed"
  | "failed"
  | "offline"
  | "issue";

export type UpdatePresentation = {
  state: UpdateExperienceState;
  phase: UpdateProgress["phase"] | "preparing";
  currentVersion: string | null;
  feedVersion: string | null;
  availableVersion: string | null;
  targetVersion: string | null;
  availabilityText: string;
  feedBehindCurrent: boolean;
  showWorkflow: boolean;
  showDownloadProgress: boolean;
};

type DeriveUpdatePresentationInput = {
  status: UpdateStatus | null;
  progress: UpdateProgress | null;
  busy: boolean;
  installing: boolean;
  reconnecting: boolean;
  issueKind: UpdateIssueKind;
  hasIssue: boolean;
  now?: Date;
};

const ACTIVE_PHASES: UpdateProgress["phase"][] = ["downloading", "verifying", "waiting_for_exit", "installing", "restarting"];
const FRESH_COMPLETION_MS = 5 * 60_000;

function versionParts(value: string | null | undefined) {
  const match = String(value ?? "").trim().match(/^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/);
  return match ? match.slice(1, 4).map(Number) : null;
}

export function compareSemanticVersions(left: string | null | undefined, right: string | null | undefined) {
  const leftParts = versionParts(left);
  const rightParts = versionParts(right);
  if (!leftParts || !rightParts) return null;
  for (let index = 0; index < leftParts.length; index += 1) {
    const difference = leftParts[index] - rightParts[index];
    if (difference !== 0) return Math.sign(difference);
  }
  return 0;
}

function completionIsFresh(progress: UpdateProgress | null, currentVersion: string | null, now: Date) {
  if (progress?.phase !== "installed" || !progress.updated_at || !progress.target_version || !currentVersion) return false;
  if (compareSemanticVersions(progress.target_version, currentVersion) !== 0) return false;
  const completedAt = new Date(progress.updated_at).getTime();
  const age = now.getTime() - completedAt;
  return Number.isFinite(completedAt) && age >= 0 && age <= FRESH_COMPLETION_MS;
}

export function deriveUpdatePresentation({
  status,
  progress,
  busy,
  installing,
  reconnecting,
  issueKind,
  hasIssue,
  now = new Date(),
}: DeriveUpdatePresentationInput): UpdatePresentation {
  // Trạng thái kiểm tra phiên bản phản ánh runtime đang chạy; file tiến trình có thể còn sót
  // từ lần cập nhật trước nên chỉ được dùng làm fallback khi endpoint trạng thái chưa có dữ liệu.
  const currentVersion = status?.current_version || progress?.current_version || null;
  const feedVersion = status?.latest_version || null;
  const feedOrder = compareSemanticVersions(feedVersion, currentVersion);
  const feedBehindCurrent = feedOrder === -1;
  const releaseIsNewer = Boolean(status?.available && (feedOrder === null || feedOrder === 1));
  const availableVersion = releaseIsNewer ? feedVersion : null;
  const progressOrder = compareSemanticVersions(progress?.target_version, currentVersion);
  const progressIsStale = progressOrder === -1;
  const activePhase = Boolean(progress && ACTIVE_PHASES.includes(progress.phase));
  const workflowActive = !progressIsStale && (installing || reconnecting || activePhase);
  const freshCompletion = completionIsFresh(progress, currentVersion, now);
  const failed = Boolean(progress?.phase === "failed" && !progressIsStale);
  const phase = installing && !progress ? "preparing" : progress?.phase ?? "idle";

  let state: UpdateExperienceState;
  if (failed) state = "failed";
  else if (issueKind === "offline") state = "offline";
  else if (hasIssue) state = "issue";
  else if (reconnecting) state = "reconnecting";
  else if (workflowActive) state = "active";
  else if (freshCompletion) state = "completed";
  else if (!status && busy) state = "checking";
  else if (releaseIsNewer && (!status?.installable || !status.automatic_install_supported)) state = "manual";
  else if (releaseIsNewer) state = "available";
  else state = "latest";

  return {
    state,
    phase,
    currentVersion,
    feedVersion,
    availableVersion,
    targetVersion: workflowActive || freshCompletion ? progress?.target_version ?? availableVersion : availableVersion,
    availabilityText: availableVersion ?? "Không có bản mới hơn",
    feedBehindCurrent,
    showWorkflow: workflowActive || freshCompletion,
    showDownloadProgress: workflowActive && phase === "downloading" && Boolean(progress?.bytes_total || progress?.percent != null),
  };
}
