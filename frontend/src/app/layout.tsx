import "./globals.css";
import React from "react";

export const metadata = {
  title: "Lokachakra - Bi-Temporal Personal Intelligence Graph",
  description: "Autonomous OSINT, Warm Pathfinder, and Personal Relationship Graph",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#090d16] text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}
