/**
 * A URL from stored data, if it is safe to put in an href: absolute http(s)
 * only. The API validates link fields too; this keeps a `javascript:` or
 * `data:` value that reached the database another way from becoming a link.
 */
export function safeHref(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}
