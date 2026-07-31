import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ContractSense",
  description: "AI-powered contract analysis — risk, key terms and Q&A.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
