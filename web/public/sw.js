const CACHE = "tiktok-affiliate-report-shell-v4";
const APP_SHELL = [
  "/",
  "/analytics",
  "/orders",
  "/imports",
  "/targets",
  "/accounts",
  "/settings/data",
  "/settings/update",
  "/settings/users",
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
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
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
        if (event.request.mode === "navigate") return (await caches.match("/")) || Response.error();
        return Response.error();
      }),
  );
});
