import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FaceFlux — Local AI Face Swap",
  description: "Privacy-first local face swap. Your files stay on this device.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased font-sans bg-slate-950 text-white">
        {children}
      </body>
    </html>
  );
}
