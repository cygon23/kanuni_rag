import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Nav } from "@/components/Nav";

import "./globals.css";

export const metadata: Metadata = {
  title: "Kanuni",
  description: "Cited, versioned answers to Bank of Tanzania regulatory questions.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-neutral-900 antialiased dark:bg-neutral-950 dark:text-neutral-100">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-blue-600 focus:px-4 focus:py-2 focus:text-white"
        >
          Skip to content
        </a>
        <Nav />
        <main id="main-content">{children}</main>
      </body>
    </html>
  );
}
