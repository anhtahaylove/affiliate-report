import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TikTok Affiliate Report",
    short_name: "Affiliate Report",
    description: "Dashboard báo cáo TikTok Affiliate từ dữ liệu export",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#ee1d52",
    lang: "vi",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
