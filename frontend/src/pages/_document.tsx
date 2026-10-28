import { Head, Html, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" data-theme="soldermask">
      <Head>
        {/* Synchronous on purpose: applies the saved theme before first paint. */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script src="/theme-init.js" />
        <meta name="description" content="A fine-tuned 1.5B code model that writes one typed, documented Python function, streamed from a $0 Lambda backend." />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
