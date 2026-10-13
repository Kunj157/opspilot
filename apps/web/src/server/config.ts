import "server-only";

/** Server configuration, read at request time so one build runs in any environment. */
export function serverConfig() {
  const required = (name: string) => {
    const value = process.env[name];
    if (!value) throw new Error(`${name} is not set`);
    return value;
  };
  return {
    apiUrl: process.env.API_URL ?? "http://127.0.0.1:8000",
    redisUrl: required("REDIS_URL"),
    oidcIssuer: required("OIDC_ISSUER"),
    oidcClientId: required("OIDC_CLIENT_ID"),
    oidcClientSecret: required("OIDC_CLIENT_SECRET"),
    production: process.env.APP_ENV === "production",
    /** Reverse proxies in front of this server that append X-Forwarded-For (0 locally). */
    trustedProxyHops: Number.parseInt(process.env.TRUSTED_PROXY_HOPS ?? "0", 10) || 0,
  };
}
