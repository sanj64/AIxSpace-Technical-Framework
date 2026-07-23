import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const isLocal = host.startsWith("localhost") || host.startsWith("127.0.0.1");
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (isLocal ? "http" : "https");
  const origin = `${protocol}://${host}`;

  return {
    title: "SATISH — Explainable Space Operations",
    description: "A local advisory-only monitor replaying third-party ESA-ADB Mission1 benchmark telemetry with faithful evidence and deterministic policy. Not affiliated with or endorsed by ESA.",
    openGraph: {
      title: "SATISH — See every recommendation. Trace every reason.",
      description: "An advisory-only live monitor replaying third-party ESA Anomaly Detection Benchmark (Mission1) telemetry. Not affiliated with or endorsed by ESA.",
      type: "website",
      url: origin,
      images: [{ url: `${origin}/og.png`, width: 1536, height: 1024, alt: "SATISH ESA-ADB Mission1 replay monitor" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "SATISH — Explainable Space Operations",
      description: "ESA-ADB Mission1 replay · Advisory only · No actuation",
      images: [`${origin}/og.png`],
    },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
