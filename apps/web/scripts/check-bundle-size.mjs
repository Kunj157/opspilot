// JS bundle-size budget for the production build (run after `next build`).
//
// For every prerendered page, the initial JavaScript is the set of
// /_next/static/... scripts its HTML loads; their gzipped sizes are summed
// and compared with bundle-budget.json, as is the total of all client chunks.
//   node scripts/check-bundle-size.mjs   (from apps/web)
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { gzipSync } from "node:zlib";

const NEXT = ".next";
const budget = JSON.parse(readFileSync("bundle-budget.json", "utf8"));
const kib = (bytes) => Math.round((bytes / 1024) * 10) / 10;
const gzipped = new Map();
const gzipSize = (file) => {
  if (!gzipped.has(file)) gzipped.set(file, gzipSync(readFileSync(file), { level: 9 }).length);
  return gzipped.get(file);
};
const walk = (dir) =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });

const pages = walk(join(NEXT, "server", "app"))
  .filter((file) => file.endsWith(".html"))
  .map((file) => {
    const html = readFileSync(file, "utf8");
    const scripts = new Set([...html.matchAll(/src="\/_next\/(static\/[^"]+\.js)"/g)].map((m) => m[1]));
    const bytes = [...scripts].reduce((sum, src) => sum + gzipSize(join(NEXT, src)), 0);
    const route = "/" + relative(join(NEXT, "server", "app"), file).replace(/(index)?\.html$/, "");
    return { route, scripts: scripts.size, gzipKiB: kib(bytes) };
  })
  .filter((page) => !page.route.startsWith("/_"))
  .sort((a, b) => b.gzipKiB - a.gzipKiB);

const chunks = walk(join(NEXT, "static", "chunks")).filter((file) => file.endsWith(".js"));
const totalKiB = kib(chunks.reduce((sum, file) => sum + gzipSize(file), 0));

console.table(pages);
console.log(`all client chunks: ${chunks.length} files, ${totalKiB} KiB gzipped`);

const failures = [
  ...pages
    .filter((page) => page.gzipKiB > budget.pageInitialJsGzipKiB)
    .map((page) => `${page.route}: ${page.gzipKiB} KiB initial JS > ${budget.pageInitialJsGzipKiB} KiB`),
  ...(totalKiB > budget.totalJsGzipKiB ? [`all chunks: ${totalKiB} KiB > ${budget.totalJsGzipKiB} KiB`] : []),
];
if (pages.length === 0) failures.push("no prerendered pages found: run `next build` first");
for (const failure of failures) console.error(`over budget: ${failure}`);
process.exit(failures.length ? 1 : 0);
