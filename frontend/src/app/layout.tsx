import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Enterprise AI Analyst",
  description:
    "Ask questions about your business data. Get trusted insights, secure SQL and interactive visualizations.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // translate="no": automatic translation would rewrite column names and SQL.
    <html
      lang="en"
      translate="no"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
