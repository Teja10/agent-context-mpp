import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Thoth",
  description: "A marketplace for ideas — where publishers are paid for insight and readers invest in understanding.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans bg-ivory text-espresso">
        {children}
      </body>
    </html>
  );
}
