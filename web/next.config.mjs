import createNextIntlPlugin from "next-intl/plugin";

// The dashboard talks to the API through its own origin (/api/*), so the
// httpOnly session cookie is always first-party: it works on localhost,
// 127.0.0.1, a LAN address or a real domain alike, without CORS. The
// target is baked into the build (standalone output); compose passes the
// in-network address, `next dev` defaults to a local API.
const apiProxyTarget = (process.env.API_PROXY_TARGET || "http://localhost:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiProxyTarget}/:path*` }];
  },
  experimental: {
    // Uploads and transcript downloads can outlast the 30 s proxy default.
    proxyTimeout: 10 * 60 * 1000,
  },
};

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

export default withNextIntl(nextConfig);
