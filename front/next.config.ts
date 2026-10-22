import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  devIndicators: false, // keeps the dev badge out of demos and screenshots
  // Same-origin proxy to FastAPI (ADR-007): the browser never talks to the back directly.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.API_URL ?? "http://localhost:8000"}/api/:path*` }];
  },
};

export default nextConfig;
