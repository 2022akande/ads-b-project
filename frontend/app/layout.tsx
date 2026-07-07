import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ai-sysdef — ADS-B Injection Defense",
  description: "Live detection of ADS-B path, velocity, and ghost injection attacks.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-mono antialiased">{children}</body>
    </html>
  );
}
