export const REPO = "https://github.com/Kunj157/opspilot";
export const DOCS = `${REPO}/tree/main/docs`;
export const THREAT_MODEL = `${REPO}/blob/main/docs/threat-model/threat-model.md`;
export const RELEASES = `${REPO}/releases`;
/** The real web app replaying a recorded incident in the browser (apps/web built with NEXT_PUBLIC_DEMO=1). */
export const DEMO = `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/demo/`;

/** Static assets live under the GitHub Pages base path. */
export const asset = (path: string) => `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}${path}`;
