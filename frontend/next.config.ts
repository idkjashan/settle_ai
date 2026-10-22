import type { NextConfig } from "next";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/api/:path*` },
      { source: "/health", destination: `${API}/health` },
      { source: "/test_assets/:path*", destination: `${API}/test_assets/:path*` },
      { source: "/docs_assets/:path*", destination: `${API}/docs_assets/:path*` },
      { source: "/evals/:path*", destination: `${API}/evals/:path*` },
    ];
  },
};

export default nextConfig;
