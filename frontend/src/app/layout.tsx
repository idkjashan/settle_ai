import type { Metadata } from "next";
import "./globals.css";
import { ClaimsProvider } from "@/lib/store";
import { ThemeProvider, ToastProvider } from "@/components/providers";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "Auto-Settle AI · Claims desk",
  description: "Autonomous video-to-cash claims adjuster — clear, guardrailed vehicle claim settlement.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="theme-color" content="#f6f6f2" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,400;6..72,500&family=IBM+Plex+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("settleai_theme")||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.dataset.theme=t;}catch(e){}`,
          }}
        />
      </head>
      <body>
        <ThemeProvider>
          <ToastProvider>
            <ClaimsProvider>
              <Shell>{children}</Shell>
            </ClaimsProvider>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
