import "./globals.css";
import type { Metadata } from "next";
import Navbar from "@/components/Navbar";
import { LocaleProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "A股投资决策中心",
  description: "个人A股资产、市场环境、研究、仓位与复盘系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="pt-14 lg:pl-60 lg:pt-0">
        <LocaleProvider>
          <Navbar />
          {children}
        </LocaleProvider>
      </body>
    </html>
  );
}
