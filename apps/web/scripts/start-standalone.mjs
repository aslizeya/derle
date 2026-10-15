// Serve the standalone production build the same way the Docker image does.
//   node scripts/start-standalone.mjs [port]
import { spawn } from "node:child_process";
import { cpSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const standalone = join(web, ".next", "standalone");
if (!existsSync(join(standalone, "server.js"))) {
  console.error("No standalone build found. Run `npm run build` first.");
  process.exit(1);
}
// The standalone server does not include static assets; the Dockerfile copies them too.
cpSync(join(web, ".next", "static"), join(standalone, ".next", "static"), { recursive: true });

const port = process.argv[2] ?? process.env.PORT ?? "3000";
const child = spawn(process.execPath, ["server.js"], {
  cwd: standalone,
  env: { ...process.env, PORT: port, HOSTNAME: "127.0.0.1" },
  stdio: "inherit",
});
child.on("exit", (code) => process.exit(code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
