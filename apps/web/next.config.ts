import type { NextConfig } from "next";

import { securityHeaders } from "./src/lib/security-headers";

// NEXT_PUBLIC_DEMO=1 builds the static demo for GitHub Pages: a plain export under
// DEMO_BASE_PATH with the API answered in the browser (src/demo). Route handlers
// and the session proxy are .ts files, so limiting page files to .tsx leaves them
// out; "demo.tsx" adds the layout.demo.tsx files that list the pages to pre-render.
const demo = process.env.NEXT_PUBLIC_DEMO === "1";

const nextConfig: NextConfig = {
  // A self-contained server for the container image (apps/web/Dockerfile).
  output: demo ? "export" : "standalone",
  ...(demo && {
    basePath: process.env.DEMO_BASE_PATH ?? "",
    trailingSlash: true,
    images: { unoptimized: true },
    pageExtensions: ["tsx", "demo.tsx"],
  }),
  // Both need a server; an export renders everything at build time.
  cacheComponents: !demo,
  partialPrefetching: !demo,
  poweredByHeader: false,
  // An export has no server to send headers (and GitHub Pages cannot set them).
  ...(!demo && {
    async headers() {
      return [
        {
          source: "/:path*",
          headers: securityHeaders({ dev: process.env.NODE_ENV === "development" }),
        },
      ];
    },
  }),
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
