/**
 * Only same-site relative paths may be used as a post-login destination;
 * anything else (absolute URLs, protocol-relative "//host", backslashes)
 * falls back to the home page so login can't be turned into an open redirect.
 */
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/";
  }
  try {
    const url = new URL(value, "http://placeholder.invalid");
    if (url.origin !== "http://placeholder.invalid") return "/";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}
