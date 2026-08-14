import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "vn.io.huuhungn.affiliatereport",
  appName: "Affiliate Report",
  webDir: "web-bootstrap",
  android: {
    path: "native",
    backgroundColor: "#f6f7f4",
    minWebViewVersion: 60,
    webContentsDebuggingEnabled: false,
  },
  server: {
    allowNavigation: ["127.0.0.1"],
  },
};

export default config;
