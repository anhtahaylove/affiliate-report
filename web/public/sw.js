const CACHE_PREFIX = "tiktok-affiliate-report-shell-";
// FastAPI thay token này bằng APP_VERSION trước khi phục vụ bản production.
// Next dev giữ nguyên token nhưng vẫn dùng một namespace riêng, không ảnh hưởng bản cài.
const CACHE = `${CACHE_PREFIX}__APP_VERSION__`;
// Next export chạy trailingSlash: true, nên route thật có dấu gạch chéo cuối. Thiếu nó thì
// cache phụ thuộc redirect và chỉ một URL hỏng là cả lần cài service worker thất bại.
const APP_SHELL = [
  "/",
  "/analytics/",
  "/orders/",
  "/imports/",
  "/targets/",
  "/accounts/",
  "/settings/preferences/",
  "/settings/data/",
  "/settings/sync/",
  "/settings/update/",
  "/settings/users/",
  "/offline.html",
  "/icon-192.png",
  "/icon-512.png",
  "/manifest.webmanifest",
];
const BYPASS_PREFIXES = ["/api/", "/auth/", "/health"];

function shouldBypass(request) {
  const url = new URL(request.url);
  return url.origin !== self.location.origin || BYPASS_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
}

self.addEventListener("install", (event) => {
  // Cache từng URL riêng: một URL hỏng chỉ mất đúng URL đó, không kéo đổ cả lần cài.
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      Promise.all(APP_SHELL.map((url) => cache.add(url).catch(() => undefined))),
    ),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE).map((key) => caches.delete(key))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET" || shouldBypass(event.request)) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) return cached;
        if (event.request.mode === "navigate") return (await caches.match("/offline.html")) || Response.error();
        return Response.error();
      }),
  );
});
