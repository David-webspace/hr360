import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "曜川 HR",
  description: "曜川科技人事助理：查假勤、薪資，辦請假",
};

export const viewport: Viewport = {
  themeColor: "#146b6f",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-Hant-TW" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
