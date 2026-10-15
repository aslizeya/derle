// Regenerate the typed API client contract from the FastAPI app (no running server needed).
//   npm run gen:api
import { execFileSync } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const api = resolve(web, "../api");
const venvPython = [join(api, ".venv/Scripts/python.exe"), join(api, ".venv/bin/python")].find(existsSync);
const python = process.env.PYTHON ?? venvPython ?? "python";

const spec = execFileSync(
  python,
  ["-c", "import json; from derle.main import create_app; print(json.dumps(create_app().openapi()))"],
  { cwd: api, env: { ...process.env, PYTHONPATH: join(api, "src") }, encoding: "utf-8" },
);
const specPath = join(web, "openapi.json");
writeFileSync(specPath, JSON.stringify(JSON.parse(spec), null, 2) + "\n");

execFileSync("npx", ["openapi-typescript", specPath, "-o", "src/lib/api/schema.d.ts"], {
  cwd: web,
  stdio: "inherit",
  shell: process.platform === "win32",
});
