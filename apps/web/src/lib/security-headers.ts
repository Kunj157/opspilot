/**
 * Response headers for every page and route of the web app (wired in next.config.ts).
 *
 * Why scripts allow 'unsafe-inline' and not a nonce: the app is built with
 * Cache Components (partial prerendering), whose static shells are rendered
 * before any request exists, so they cannot carry a per-request nonce. Next.js
 * streams its RSC payload in inline <script> tags, so inline scripts must be
 * allowed. Everything else is locked to this origin: no eval (React, Next.js,
 * and three.js do not need it in production), no plugins, no foreign
 * connections, no framing, and <base> cannot be rewritten. Rendered content is
 * escaped by React (there is no raw-HTML rendering in the app), which is the
 * primary XSS defence; the CSP limits what an injection could reach.
 *
 * form-action is deliberately absent: signing out posts to /auth/logout, which
 * redirects to the identity provider's end-session URL, and browsers apply
 * form-action to that redirect. The provider's origin is only known at runtime,
 * while these headers are fixed at build time.
 */

export type Header = { key: string; value: string };

export function contentSecurityPolicy({ dev }: { dev: boolean }): string {
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    // Development only: React rebuilds server error stacks with eval.
    "script-src": ["'self'", "'unsafe-inline'", ...(dev ? ["'unsafe-eval'"] : [])],
    // Inline style attributes (React style props, the 3D canvas).
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'", "data:"],
    // Same-origin fetch, the API proxy, SSE streams, and dev hot reload.
    "connect-src": ["'self'"],
    "worker-src": ["'self'", "blob:"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "frame-ancestors": ["'none'"],
  };
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${sources.join(" ")}`)
    .join("; ");
}

export function securityHeaders({ dev }: { dev: boolean }): Header[] {
  return [
    { key: "Content-Security-Policy", value: contentSecurityPolicy({ dev }) },
    // Ignored by browsers over plain HTTP, so it is safe to send everywhere.
    { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    {
      key: "Permissions-Policy",
      value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  ];
}
