import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Async Standup Intelligence",
  description: "Behavioral signal analysis replacing daily standups",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
