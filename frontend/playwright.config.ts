import { defineConfig, devices } from "@playwright/test";

// BASE_URL defaults to the deployed site, so the real CSP and status.json are what get tested.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  use: { baseURL: process.env.BASE_URL ?? "https://d2js86b0xg0ozs.cloudfront.net", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
