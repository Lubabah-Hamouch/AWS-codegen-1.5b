import type { AppProps } from "next/app";
import { IBM_Plex_Mono, IBM_Plex_Sans_Condensed } from "next/font/google";
import "@/styles/globals.css";

// Self-hosted at build time by next/font: no request to Google from the browser (CSP font-src 'self').
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-mono" });
const silk = IBM_Plex_Sans_Condensed({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-silk" });

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className={`app ${mono.variable} ${silk.variable}`}>
      <Component {...pageProps} />
    </div>
  );
}
