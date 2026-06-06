import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Quant Copilot",
  description: "AI-powered quant research platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
