import { existsSync, mkdirSync, rmSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const apiPort = process.env.E2E_API_PORT ?? "18100";
const runtimeDir = path.join(root, ".local", "playwright");
const databasePath = path.join(runtimeDir, "password-detective-e2e.db");
const pythonCandidates = [
  process.env.E2E_PYTHON,
  process.platform === "win32"
    ? path.join(root, "apps", "api", ".venv", "Scripts", "python.exe")
    : path.join(root, "apps", "api", ".venv", "bin", "python"),
  process.platform === "win32" ? "python.exe" : "python3",
].filter(Boolean);
const python = pythonCandidates.find((candidate) =>
  path.isAbsolute(candidate) ? existsSync(candidate) : true,
);

if (!python) {
  throw new Error("未找到可用于 Playwright API 服务的 Python 运行时");
}

mkdirSync(runtimeDir, { recursive: true });
for (const suffix of ["", "-shm", "-wal"]) {
  rmSync(`${databasePath}${suffix}`, { force: true });
}

const environment = {
  ...process.env,
  APP_ENV: "integration",
  APP_DEBUG: "false",
  APP_SECRET_KEY: "synthetic-playwright-secret-key-2026",
  DIRECT_MESSAGE_KEY_VERSION: "v1",
  DIRECT_MESSAGE_KEYRING: JSON.stringify({
    v1: "synthetic-playwright-direct-message-key-at-least-32",
  }),
  DATABASE_URL: "sqlite:///./.local/playwright/password-detective-e2e.db",
  RATE_LIMIT_BACKEND: "memory",
  WEB_LOGIN_RATE_LIMIT: "100",
  ADMIN_LOGIN_RATE_LIMIT: "100",
  WEB_ANNOUNCEMENT_LIST_RATE_LIMIT: "1000",
  NOTIFICATION_BACKEND: "memory",
  AUTO_CREATE_TABLES: "true",
  BROWSER_COOKIE_SECURE: "false",
  CORS_ORIGINS: [process.env.E2E_WEB_ORIGIN, process.env.E2E_ADMIN_ORIGIN]
    .filter(Boolean)
    .join(","),
  PYTHONUNBUFFERED: "1",
};

const seed = spawnSync(
  python,
  [path.join(root, "tests", "e2e", "support", "seed_api.py")],
  { cwd: root, env: environment, stdio: "inherit" },
);
if (seed.status !== 0) {
  process.exit(seed.status ?? 1);
}

const api = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "password_detective.main:app",
    "--app-dir",
    path.join(root, "apps", "api", "src"),
    "--host",
    "127.0.0.1",
    "--port",
    apiPort,
  ],
  { cwd: root, env: environment, stdio: "inherit" },
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (!api.killed) api.kill(signal);
  });
}

api.on("exit", (code) => process.exit(code ?? 0));
