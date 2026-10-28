import { Head, Html, Main, NextScript } from "next/document";
import { SITE } from "@/data/facts";

const TITLE = "Codegen-1.5B: a fine-tuned code model, deployed to AWS for $0";
const DESCRIPTION = "A 1.5B code model fine-tuned to almost always answer in one clean, typed, documented Python function. "
  + "Watch real recorded runs and test the code in your browser.";

export default function Document() {
  return (
    <Html lang="en" data-theme="soldermask">
      <Head>
        {/* Synchronous on purpose: applies the saved theme before first paint. */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script src="/theme-init.js" />
        <meta name="description" content={DESCRIPTION} />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        {/* link previews (chat apps, social sites): one card for the whole site */}
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content="Codegen-1.5B" />
        <meta property="og:title" content={TITLE} />
        <meta property="og:description" content={DESCRIPTION} />
        <meta property="og:url" content={`${SITE}/`} />
        <meta property="og:image" content={`${SITE}/og.png`} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content="The playground: a plain-language summary and the before/after results table" />
        <meta name="twitter:card" content="summary_large_image" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
