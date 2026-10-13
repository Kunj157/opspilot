import "server-only";

import { createClient } from "redis";

import { serverConfig } from "./config";

type Client = ReturnType<typeof createClient>;

const globalForRedis = globalThis as unknown as { opspilotRedis?: Promise<Client> };

/** One connection per server process (kept across hot reloads in development). */
export function redis(): Promise<Client> {
  globalForRedis.opspilotRedis ??= createClient({ url: serverConfig().redisUrl })
    .on("error", (err: unknown) => console.error("redis error", err))
    .connect() as Promise<Client>;
  return globalForRedis.opspilotRedis;
}
