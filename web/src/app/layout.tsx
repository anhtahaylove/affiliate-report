import type { Metadata } from "next";
import { Be_Vietnam_Pro } from "next/font/google";
import { ServiceWorkerRegistration } from "@/components/service-worker";
import "./globals.css";

const appFont = Be_Vietnam_Pro({
  variable: "--font-app",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "TikTok Affiliate Report",
  description: "Báo cáo vận hành TikTok Affiliate từ dữ liệu Excel đã xuất",
  applicationName: "TikTok Affiliate Report",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "TikTok Affiliate Report",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className={appFont.variable}>
      <head>
        {/* Áp chế độ đã lưu trước khi vẽ, nếu không màn hình sẽ loé sáng rồi mới chuyển tối. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("tiktok-affiliate-theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t)}catch(e){}`,
          }}
        />
      </head>
      <body>
        {children}
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
