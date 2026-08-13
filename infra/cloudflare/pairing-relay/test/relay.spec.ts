import { env } from "cloudflare:workers";
import { SELF, runDurableObjectAlarm } from "cloudflare:test";
import { describe, expect, it } from "vitest";

const BASE = "https://relay.test";

describe("Cloud Pairing Relay", () => {
  it("publishes a minimal health response", async () => {
    const response = await SELF.fetch(`${BASE}/health`);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      status: "ok",
      service: "affiliate-report-pairing-relay",
      version: "1.0.0",
    });
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("serves a nonce-protected mobile upload page without embedding capabilities", async () => {
    const sessionId = id();
    const response = await SELF.fetch(`${BASE}/pair/${sessionId}#k=secret-key&u=secret-upload-token`);
    const html = await response.text();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-security-policy")).toContain("script-src 'nonce-");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(html).toContain("Mã hóa và gửi");
    expect(html).toContain(JSON.stringify(sessionId));
    expect(html).not.toContain("secret-key");
    expect(html).not.toContain("secret-upload-token");
  });

  it("keeps ciphertext private, supports one upload, then deletes it on ACK", async () => {
    const session = await createSession();
    const plain = new TextEncoder().encode("PK\\x03\\x04-private-xlsx-marker");
    const encrypted = await encryptForSession(session.sessionId, session.key, plain);

    const upload = await putFile(session, encrypted);
    expect(upload.status).toBe(201);
    expect((await upload.json()) as { state: string }).toMatchObject({ state: "ready" });

    const listed = await env.PAIRING_FILES.list();
    expect(listed.objects).toHaveLength(1);
    const stored = await env.PAIRING_FILES.get(listed.objects[0]!.key);
    const storedBytes = new Uint8Array(await stored!.arrayBuffer());
    expect(storedBytes).toEqual(encrypted);
    expect(new TextDecoder().decode(storedBytes)).not.toContain("private-xlsx-marker");

    const status = await claim(session, "");
    expect(status.status).toBe(200);
    expect(await status.json()).toMatchObject({ state: "ready", encrypted_size: encrypted.byteLength });

    const download = await claim(session, "/file");
    expect(download.status).toBe(200);
    expect(new Uint8Array(await download.arrayBuffer())).toEqual(encrypted);

    const secondUpload = await putFile(session, encrypted);
    expect(secondUpload.status).toBe(409);
    expect(await secondUpload.json()).toMatchObject({ error: { code: "upload_consumed" } });

    const ack = await claim(session, "/ack", "POST");
    expect(ack.status).toBe(200);
    expect(await ack.json()).toEqual({ schema: 1, state: "deleted" });
    expect((await env.PAIRING_FILES.list()).objects).toHaveLength(0);
    expect((await claim(session, "")).status).toBe(404);
  });

  it("rejects invalid capabilities without leaking session state", async () => {
    const session = await createSession();
    const wrong = "Z".repeat(43);

    const status = await SELF.fetch(`${BASE}/api/v1/sessions/${session.sessionId}`, {
      headers: { authorization: `Pairing ${wrong}` },
    });
    const upload = await SELF.fetch(`${BASE}/api/v1/sessions/${session.sessionId}/file`, {
      method: "PUT",
      headers: {
        authorization: `Pairing ${wrong}`,
        "content-type": "application/octet-stream",
        "content-length": "64",
      },
      body: new Uint8Array(64),
    });

    expect(status.status).toBe(403);
    expect(upload.status).toBe(403);
    expect(await status.json()).toMatchObject({ error: { code: "invalid_capability" } });
  });

  it("fails closed for malformed sessions, content type and size", async () => {
    const malformed = await SELF.fetch(`${BASE}/api/v1/sessions`, {
      method: "POST",
      headers: { "content-type": "application/json", "cf-connecting-ip": uniqueIp() },
      body: JSON.stringify({ schema: 1, session_id: "short" }),
    });
    expect(malformed.status).toBe(422);

    const session = await createSession();
    const wrongType = await SELF.fetch(`${BASE}/api/v1/sessions/${session.sessionId}/file`, {
      method: "PUT",
      headers: {
        authorization: `Pairing ${session.uploadToken}`,
        "content-type": "text/plain",
        "content-length": "64",
      },
      body: new Uint8Array(64),
    });
    expect(wrongType.status).toBe(415);

    const oversized = await SELF.fetch(`${BASE}/api/v1/sessions/${session.sessionId}/file`, {
      method: "PUT",
      headers: {
        authorization: `Pairing ${session.uploadToken}`,
        "content-type": "application/octet-stream",
        "content-length": String(Number(env.MAX_ENCRYPTED_BYTES) + 1),
      },
      body: new Uint8Array(64),
    });
    expect(oversized.status).toBe(413);
    expect((await env.PAIRING_FILES.list()).objects).toHaveLength(0);
  });

  it("alarm removes abandoned ciphertext and state", async () => {
    const session = await createSession();
    const encrypted = crypto.getRandomValues(new Uint8Array(128));
    expect((await putFile(session, encrypted)).status).toBe(201);

    const stub = env.PAIRING_SESSIONS.getByName(session.sessionId);
    expect(await runDurableObjectAlarm(stub)).toBe(true);

    expect((await env.PAIRING_FILES.list()).objects).toHaveLength(0);
    expect((await claim(session, "")).status).toBe(404);
  });
});

type TestSession = {
  sessionId: string;
  uploadToken: string;
  claimToken: string;
  key: Uint8Array;
};

async function createSession(): Promise<TestSession> {
  const sessionId = id();
  const uploadToken = token("U");
  const claimToken = token("C");
  const response = await SELF.fetch(`${BASE}/api/v1/sessions`, {
    method: "POST",
    headers: { "content-type": "application/json", "cf-connecting-ip": uniqueIp() },
    body: JSON.stringify({
      schema: 1,
      session_id: sessionId,
      upload_token_hash: await hash(uploadToken),
      claim_token_hash: await hash(claimToken),
    }),
  });
  expect(response.status, await response.clone().text()).toBe(201);
  const body = (await response.json()) as Record<string, unknown>;
  expect(body).toMatchObject({ schema: 1, session_id: sessionId, state: "created" });
  expect(body.upload_url).toBe(`${BASE}/pair/${sessionId}`);
  expect(JSON.stringify(body)).not.toContain(uploadToken);
  expect(JSON.stringify(body)).not.toContain(claimToken);
  return { sessionId, uploadToken, claimToken, key: crypto.getRandomValues(new Uint8Array(32)) };
}

function putFile(session: TestSession, body: Uint8Array): Promise<Response> {
  return SELF.fetch(`${BASE}/api/v1/sessions/${session.sessionId}/file`, {
    method: "PUT",
    headers: {
      authorization: `Pairing ${session.uploadToken}`,
      "content-type": "application/octet-stream",
      "content-length": String(body.byteLength),
    },
    body: Uint8Array.from(body).buffer,
  });
}

function claim(session: TestSession, suffix: string, method = "GET"): Promise<Response> {
  return SELF.fetch(`${BASE}/api/v1/sessions/${session.sessionId}${suffix}`, {
    method,
    headers: { authorization: `Pairing ${session.claimToken}` },
  });
}

async function encryptForSession(sessionId: string, rawKey: Uint8Array, plain: Uint8Array): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey("raw", Uint8Array.from(rawKey).buffer, "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = new Uint8Array(
    await crypto.subtle.encrypt(
      {
        name: "AES-GCM",
        iv,
        additionalData: new TextEncoder().encode(`affiliate-report-pairing-v1:${sessionId}`).buffer,
      },
      key,
      Uint8Array.from(plain).buffer,
    ),
  );
  const result = new Uint8Array(iv.byteLength + encrypted.byteLength);
  result.set(iv);
  result.set(encrypted, iv.byteLength);
  return result;
}

async function hash(value: string): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value).buffer));
  return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function id(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

function token(prefix: string): string {
  return `${prefix}${crypto.randomUUID().replaceAll("-", "")}${crypto.randomUUID().replaceAll("-", "").slice(0, 10)}`;
}

function uniqueIp(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(3));
  return `10.${bytes[0]}.${bytes[1]}.${bytes[2]}`;
}
