export const PROTOCOL_SCHEMA = 1 as const;
export const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{20,80}$/;
export const TOKEN_PATTERN = /^[A-Za-z0-9_-]{40,64}$/;
export const TOKEN_HASH_PATTERN = /^[a-f0-9]{64}$/;

export type SessionPhase = "created" | "uploading" | "ready";

export type SessionRecord = {
  schema: typeof PROTOCOL_SCHEMA;
  sessionId: string;
  phase: SessionPhase;
  uploadTokenHash: string;
  claimTokenHash: string;
  objectKey: string;
  createdAt: number;
  expiresAt: number;
  hardExpiresAt: number;
  encryptedSize?: number;
};

export type CreateSessionInput = {
  schema: typeof PROTOCOL_SCHEMA;
  session_id: string;
  upload_token_hash: string;
  claim_token_hash: string;
};

export type InitSessionInput = CreateSessionInput & {
  expires_at: number;
  hard_expires_at: number;
  object_key: string;
};

export function json(data: unknown, status = 200, headers?: HeadersInit): Response {
  const responseHeaders = new Headers(headers);
  responseHeaders.set("content-type", "application/json; charset=utf-8");
  responseHeaders.set("cache-control", "no-store");
  responseHeaders.set("x-content-type-options", "nosniff");
  return new Response(JSON.stringify(data), { status, headers: responseHeaders });
}

export function problem(status: number, code: string, detail: string): Response {
  return json({ error: { code, detail } }, status);
}

export async function readSmallJson(request: Request, maxBytes = 4096): Promise<unknown> {
  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (contentType !== "application/json") {
    throw new ProtocolError(415, "content_type", "Yêu cầu phải dùng application/json.");
  }
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > maxBytes) {
    throw new ProtocolError(413, "body_too_large", "Nội dung yêu cầu vượt giới hạn.");
  }
  const body = await request.arrayBuffer();
  if (body.byteLength > maxBytes) {
    throw new ProtocolError(413, "body_too_large", "Nội dung yêu cầu vượt giới hạn.");
  }
  try {
    return JSON.parse(new TextDecoder().decode(body));
  } catch {
    throw new ProtocolError(400, "invalid_json", "Nội dung JSON không hợp lệ.");
  }
}

export function validateCreateSession(value: unknown): CreateSessionInput {
  if (!isRecord(value)) {
    throw new ProtocolError(422, "invalid_session", "Thông tin phiên không hợp lệ.");
  }
  const schema = value.schema;
  const sessionId = value.session_id;
  const uploadHash = value.upload_token_hash;
  const claimHash = value.claim_token_hash;
  if (schema !== PROTOCOL_SCHEMA) {
    throw new ProtocolError(422, "unsupported_schema", "Phiên bản giao thức không được hỗ trợ.");
  }
  if (typeof sessionId !== "string" || !SESSION_ID_PATTERN.test(sessionId)) {
    throw new ProtocolError(422, "invalid_session_id", "Mã phiên không hợp lệ.");
  }
  if (typeof uploadHash !== "string" || !TOKEN_HASH_PATTERN.test(uploadHash)) {
    throw new ProtocolError(422, "invalid_upload_capability", "Capability upload không hợp lệ.");
  }
  if (typeof claimHash !== "string" || !TOKEN_HASH_PATTERN.test(claimHash)) {
    throw new ProtocolError(422, "invalid_claim_capability", "Capability nhận file không hợp lệ.");
  }
  if (constantTimeEqualHex(uploadHash, claimHash)) {
    throw new ProtocolError(422, "capability_reuse", "Hai capability phải độc lập.");
  }
  return {
    schema: PROTOCOL_SCHEMA,
    session_id: sessionId,
    upload_token_hash: uploadHash,
    claim_token_hash: claimHash,
  };
}

export function validateCapability(value: string | null): string | null {
  if (!value?.startsWith("Pairing ")) return null;
  const token = value.slice("Pairing ".length).trim();
  return TOKEN_PATTERN.test(token) ? token : null;
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function constantTimeEqualHex(left: string, right: string): boolean {
  if (left.length !== 64 || right.length !== 64) return false;
  let difference = 0;
  for (let index = 0; index < 64; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

export class ProtocolError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
