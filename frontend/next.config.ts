import type { NextConfig } from "next";

// The FastAPI backend. Browser calls go to /api/* on this app and are forwarded there,
// so the login cookie stays on the same site as the pages.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
