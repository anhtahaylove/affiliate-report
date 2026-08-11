export function normalizeRoutePath(path: string) {
  if (!path || path === "/") return "/";
  return path.replace(/\/+$/, "") || "/";
}

export function routeIsActive(pathname: string, href: string) {
  return normalizeRoutePath(pathname) === normalizeRoutePath(href);
}
