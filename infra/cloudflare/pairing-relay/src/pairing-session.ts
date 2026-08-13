import { DurableObject } from "cloudflare:workers";

import {
  type InitSessionInput,
  PROTOCOL_SCHEMA,
  ProtocolError,
  type SessionRecord,
  constantTimeEqualHex,
  json,
  problem,
  readSmallJson,
  sha256Hex,
  validateCapability,
} from "./protocol";

const SESSION_KEY = "session";

export class PairingSession extends DurableObject<Cloudflare.Env> {
  override async fetch(request: Request): Promise<Response> {
    try {
      const { pathname } = new URL(request.url);
      if (request.method === "POST" && pathname === "/init") return await this.initialize(request);
      if (request.method === "PUT" && pathname === "/upload") return await this.upload(request);
      if (request.method === "GET" && pathname === "/status") return await this.status(request);
      if (request.method === "GET" && pathname === "/file") return await this.download(request);
      if (request.method === "POST" && pathname === "/ack") return await this.acknowledge(request);
      if (request.method === "DELETE" && pathname === "/cancel") return await this.cancel(request);
      return problem(404, "not_found", "Không tìm thấy tài nguyên.");
    } catch (error) {
      if (error instanceof ProtocolError) return problem(error.status, error.code, error.message);
      console.error(JSON.stringify({ event: "pairing_session_error", message: safeError(error) }));
      return problem(500, "relay_error", "Cloud relay gặp lỗi tạm thời.");
    }
  }

  override async alarm(): Promise<void> {
    await this.cleanup();
  }

  private async initialize(request: Request): Promise<Response> {
    const current = await this.ctx.storage.get<SessionRecord>(SESSION_KEY);
    if (current) return problem(409, "session_exists", "Phiên ghép cặp đã tồn tại.");
    const raw = await readSmallJson(request);
    if (!isInitSession(raw)) {
      return problem(422, "invalid_session", "Thông tin phiên không hợp lệ.");
    }
    const now = Date.now();
    if (raw.expires_at <= now || raw.hard_expires_at <= raw.expires_at) {
      return problem(422, "invalid_expiry", "Thời hạn phiên không hợp lệ.");
    }
    const session: SessionRecord = {
      schema: PROTOCOL_SCHEMA,
      sessionId: raw.session_id,
      phase: "created",
      uploadTokenHash: raw.upload_token_hash,
      claimTokenHash: raw.claim_token_hash,
      objectKey: raw.object_key,
      createdAt: now,
      expiresAt: raw.expires_at,
      hardExpiresAt: raw.hard_expires_at,
    };
    await this.ctx.storage.put(SESSION_KEY, session);
    await this.ctx.storage.setAlarm(session.hardExpiresAt);
    return json(publicStatus(session), 201);
  }

  private async upload(request: Request): Promise<Response> {
    const session = await this.requireSession();
    await this.requireCapability(request, session.uploadTokenHash);
    if (Date.now() >= session.expiresAt) {
      await this.cleanup(session);
      return problem(410, "session_expired", "Mã ghép cặp đã hết hạn.");
    }
    if (session.phase !== "created") {
      return problem(409, "upload_consumed", "Phiên này không còn nhận thêm file.");
    }
    if (request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase() !== "application/octet-stream") {
      return problem(415, "content_type", "File mã hóa phải dùng application/octet-stream.");
    }
    const declaredSize = Number(request.headers.get("content-length") ?? "");
    const maxSize = Number(this.env.MAX_ENCRYPTED_BYTES);
    if (!Number.isSafeInteger(declaredSize) || declaredSize < 29) {
      return problem(411, "content_length", "Không xác định được dung lượng file mã hóa.");
    }
    if (declaredSize > maxSize) {
      return problem(413, "file_too_large", "File vượt giới hạn 20 MiB.");
    }
    if (!request.body) return problem(400, "missing_body", "Không có nội dung file.");

    const uploading: SessionRecord = { ...session, phase: "uploading" };
    await this.ctx.storage.put(SESSION_KEY, uploading);
    try {
      const object = await this.env.PAIRING_FILES.put(session.objectKey, request.body, {
        httpMetadata: { contentType: "application/octet-stream" },
        customMetadata: { schema: String(PROTOCOL_SCHEMA) },
      });
      if (object.size !== declaredSize || object.size > maxSize) {
        await this.env.PAIRING_FILES.delete(session.objectKey);
        await this.ctx.storage.put(SESSION_KEY, session);
        return problem(413, "file_size_mismatch", "Dung lượng file mã hóa không hợp lệ.");
      }
      const ready: SessionRecord = { ...session, phase: "ready", encryptedSize: object.size };
      await this.ctx.storage.put(SESSION_KEY, ready);
      return json(publicStatus(ready), 201);
    } catch (error) {
      await this.ctx.storage.put(SESSION_KEY, session);
      console.error(JSON.stringify({ event: "pairing_r2_put_failed", session_id: session.sessionId, message: safeError(error) }));
      return problem(503, "storage_unavailable", "Không lưu được file tạm thời. Hãy thử lại.");
    }
  }

  private async status(request: Request): Promise<Response> {
    const session = await this.requireSession();
    await this.requireCapability(request, session.claimTokenHash);
    if (this.isExpired(session)) {
      await this.cleanup(session);
      return problem(410, "session_expired", "Phiên ghép cặp đã hết hạn.");
    }
    return json(publicStatus(session));
  }

  private async download(request: Request): Promise<Response> {
    const session = await this.requireSession();
    await this.requireCapability(request, session.claimTokenHash);
    if (this.isExpired(session)) {
      await this.cleanup(session);
      return problem(410, "session_expired", "Phiên ghép cặp đã hết hạn.");
    }
    if (session.phase !== "ready") return problem(409, "file_not_ready", "Điện thoại chưa gửi file xong.");
    const object = await this.env.PAIRING_FILES.get(session.objectKey);
    if (!object) return problem(503, "file_missing", "File tạm thời không còn tồn tại.");
    return new Response(object.body, {
      headers: {
        "content-type": "application/octet-stream",
        "content-length": String(object.size),
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    });
  }

  private async acknowledge(request: Request): Promise<Response> {
    const session = await this.requireSession();
    await this.requireCapability(request, session.claimTokenHash);
    if (session.phase !== "ready") return problem(409, "file_not_ready", "Không có file sẵn sàng để xác nhận.");
    await this.cleanup(session);
    return json({ schema: PROTOCOL_SCHEMA, state: "deleted" });
  }

  private async cancel(request: Request): Promise<Response> {
    const session = await this.requireSession();
    await this.requireCapability(request, session.claimTokenHash);
    await this.cleanup(session);
    return json({ schema: PROTOCOL_SCHEMA, state: "deleted" });
  }

  private async requireSession(): Promise<SessionRecord> {
    const session = await this.ctx.storage.get<SessionRecord>(SESSION_KEY);
    if (!session) throw new ProtocolError(404, "session_not_found", "Phiên ghép cặp không tồn tại.");
    return session;
  }

  private async requireCapability(request: Request, expectedHash: string): Promise<void> {
    const token = validateCapability(request.headers.get("authorization"));
    const actualHash = token ? await sha256Hex(token) : "0".repeat(64);
    if (!constantTimeEqualHex(actualHash, expectedHash)) {
      throw new ProtocolError(403, "invalid_capability", "Capability không hợp lệ.");
    }
  }

  private isExpired(session: SessionRecord): boolean {
    const now = Date.now();
    return now >= session.hardExpiresAt || (session.phase !== "ready" && now >= session.expiresAt);
  }

  private async cleanup(existing?: SessionRecord): Promise<void> {
    const session = existing ?? (await this.ctx.storage.get<SessionRecord>(SESSION_KEY));
    if (session) await this.env.PAIRING_FILES.delete(session.objectKey);
    await this.ctx.storage.deleteAlarm();
    await this.ctx.storage.deleteAll();
  }
}

function publicStatus(session: SessionRecord): Record<string, unknown> {
  return {
    schema: PROTOCOL_SCHEMA,
    session_id: session.sessionId,
    state: session.phase,
    expires_at: new Date(session.expiresAt).toISOString(),
    hard_expires_at: new Date(session.hardExpiresAt).toISOString(),
    ...(session.encryptedSize === undefined ? {} : { encrypted_size: session.encryptedSize }),
  };
}

function isInitSession(value: unknown): value is InitSessionInput {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  return (
    item.schema === PROTOCOL_SCHEMA &&
    typeof item.session_id === "string" &&
    typeof item.upload_token_hash === "string" &&
    typeof item.claim_token_hash === "string" &&
    typeof item.expires_at === "number" &&
    Number.isSafeInteger(item.expires_at) &&
    typeof item.hard_expires_at === "number" &&
    Number.isSafeInteger(item.hard_expires_at) &&
    typeof item.object_key === "string" &&
    /^pairing\/[A-Za-z0-9_-]{20,80}\/[0-9a-f-]{36}\.bin$/.test(item.object_key)
  );
}

function safeError(error: unknown): string {
  return error instanceof Error ? error.name : "unknown";
}
