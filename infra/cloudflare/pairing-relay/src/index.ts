import { PairingSession } from "./pairing-session";
import {
  ProtocolError,
  SESSION_ID_PATTERN,
  json,
  problem,
  readSmallJson,
  sha256Hex,
  validateCreateSession,
} from "./protocol";
import { uploadPage } from "./upload-page";

export { PairingSession };

export default {
  async fetch(request, env): Promise<Response> {
    try {
      const url = new URL(request.url);
      if (request.method === "GET" && url.pathname === "/health") {
        return json({ status: "ok", service: "affiliate-report-pairing-relay", version: env.SERVICE_VERSION });
      }
      if (request.method === "POST" && url.pathname === "/api/v1/sessions") {
        return await createSession(request, env, url.origin);
      }
      const pairMatch = url.pathname.match(/^\/pair\/([A-Za-z0-9_-]{20,80})$/);
      if (request.method === "GET" && pairMatch?.[1]) return uploadPage(pairMatch[1]);

      const apiMatch = url.pathname.match(/^\/api\/v1\/sessions\/([A-Za-z0-9_-]{20,80})(?:\/(file|ack))?$/);
      if (apiMatch?.[1]) return await routeSession(request, env, apiMatch[1], apiMatch[2]);
      return problem(404, "not_found", "Không tìm thấy tài nguyên.");
    } catch (error) {
      if (error instanceof ProtocolError) return problem(error.status, error.code, error.message);
      console.error(JSON.stringify({ event: "pairing_worker_error", message: error instanceof Error ? error.name : "unknown" }));
      return problem(500, "relay_error", "Cloud relay gặp lỗi tạm thời.");
    }
  },
} satisfies ExportedHandler<Cloudflare.Env>;

async function createSession(request: Request, env: Cloudflare.Env, origin: string): Promise<Response> {
  const network = request.headers.get("cf-connecting-ip") ?? "unknown";
  const networkKey = (await sha256Hex(network)).slice(0, 32);
  const allowed = await env.SESSION_CREATION_RATE_LIMITER.limit({ key: `create:${networkKey}` });
  if (!allowed.success) return problem(429, "rate_limited", "Tạo mã quá nhanh. Hãy đợi một phút rồi thử lại.");

  const input = validateCreateSession(await readSmallJson(request));
  const now = Date.now();
  const expiresAt = now + numberSetting(env.SESSION_TTL_SECONDS, 300) * 1000;
  const hardExpiresAt = now + numberSetting(env.HARD_TTL_SECONDS, 900) * 1000;
  const objectKey = `pairing/${input.session_id}/${crypto.randomUUID()}.bin`;
  const response = await sessionStub(env, input.session_id).fetch("https://session.internal/init", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      ...input,
      expires_at: expiresAt,
      hard_expires_at: hardExpiresAt,
      object_key: objectKey,
    }),
  });
  if (!response.ok) return response;
  const status = (await response.json()) as Record<string, unknown>;
  return json({ ...status, upload_url: `${origin}/pair/${input.session_id}` }, 201);
}

async function routeSession(
  request: Request,
  env: Cloudflare.Env,
  sessionId: string,
  action: string | undefined,
): Promise<Response> {
  if (!SESSION_ID_PATTERN.test(sessionId)) return problem(404, "not_found", "Không tìm thấy tài nguyên.");
  let internalPath: string;
  if (request.method === "PUT" && action === "file") internalPath = "/upload";
  else if (request.method === "GET" && action === "file") internalPath = "/file";
  else if (request.method === "POST" && action === "ack") internalPath = "/ack";
  else if (request.method === "GET" && !action) internalPath = "/status";
  else if (request.method === "DELETE" && !action) internalPath = "/cancel";
  else return problem(405, "method_not_allowed", "Phương thức không được hỗ trợ.");

  const headers = new Headers();
  for (const name of ["authorization", "content-type", "content-length"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  return await sessionStub(env, sessionId).fetch(`https://session.internal${internalPath}`, {
    method: request.method,
    headers,
    body: request.method === "PUT" ? request.body : null,
  });
}

function sessionStub(env: Cloudflare.Env, sessionId: string): DurableObjectStub {
  return env.PAIRING_SESSIONS.getByName(sessionId);
}

function numberSetting(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : fallback;
}
