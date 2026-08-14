import type { MetadataRoute } from "next";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Affiliate Report",
    short_name: "Affiliate Report",
    description: "Dashboard báo cáo affiliate từ dữ liệu export",
    start_url: "/",
    display: "standalone",
    background_color: "#f6f8fa",
    theme_color: "#0f766e",
    lang: "vi",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
