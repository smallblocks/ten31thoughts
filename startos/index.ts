/**
 * Ten31 Thoughts — StartOS V2 SDK Procedures
 * 
 * This file defines the service lifecycle hooks that StartOS calls:
 * - init: Called on first install
 * - uninit: Called on uninstall  
 * - main: The service entrypoint (starts the container)
 * - health: Health check definitions
 * - config: Configuration get/set (null = no config UI)
 * - properties: Runtime properties displayed in the UI
 * - migration: Version migration logic
 * - backup: Backup create/restore
 */
import {
  setupManifest,
  setupInit,
  setupUninit,
  setupMain,
  setupHealth,
  setupConfig,
  setupProperties,
  setupMigrations,
  setupBackups,
  setupActions,
  createService,
} from "@start9labs/start-sdk";

// Re-export the manifest
export const manifest = setupManifest({
  id: "tenthoughts",
  title: "Ten31 Thoughts",
  license: "mit",
  wrapperRepo: "https://github.com/smallblocks/ten31thoughts",
  upstreamRepo: "https://github.com/smallblocks/ten31thoughts",
  supportSite: "https://ten31.xyz",
  marketingSite: "https://ten31timestamp.com",
  description: {
    short: "Macro intelligence service coordinating your thesis with external voices",
    long: "Ten31 Thoughts ingests your published macro framework alongside external macro interviews to surface the top mental models for navigating the current macro landscape.",
  },
  releaseNotes: "Initial release of Ten31 Thoughts macro intelligence service.",
  images: {
    main: {
      source: {
        dockerTag: "start9/tenthoughts/main",
      },
    },
  },
  volumes: {
    main: "data",
  },
  assets: {},
  alerts: {},
  dependencies: {},
});

// Init: runs on first install
export const init = setupInit(async ({ effects }) => {
  // Nothing special needed — data dirs are created by the Dockerfile
});

// Uninit: runs on uninstall
export const uninit = setupUninit(async ({ effects }) => {
  // Cleanup if needed
});

// Main: service entrypoint
export const main = setupMain(async ({ effects, started }) => {
  return effects.runDaemon(
    {
      command: "/usr/local/bin/uvicorn",
      args: [
        "src.app:app",
        "--host", "0.0.0.0",
        "--port", "8431",
        "--workers", "1",
      ],
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: "/app",
        DATABASE_URL: "sqlite:////data/ten31thoughts.db",
        CHROMADB_PERSIST_DIR: "/data/chromadb",
      },
    },
    {
      started,
    }
  );
});

// Health checks
export const health = setupHealth([
  {
    id: "web-ui",
    name: "Web Interface",
    fn: async ({ effects }) => {
      const result = await effects.fetch("http://localhost:8431/api/health");
      if (!result.ok) {
        return { status: "failing", message: "Web interface not responding" };
      }
      return { status: "passing", message: "Ten31 Thoughts is ready" };
    },
  },
]);

// Config: null means no config UI
export const config = setupConfig(null);

// Properties: displayed in the service detail page
export const properties = setupProperties(async ({ effects }) => {
  return {
    "API Endpoint": {
      type: "string",
      value: "http://tenthoughts.embassy:8431",
      description: "Internal API endpoint",
      copyable: true,
    },
  };
});

// Migrations
export const migrations = setupMigrations({});

// Backups
export const backups = setupBackups({
  create: async ({ effects }) => {
    // The main volume is automatically backed up
  },
  restore: async ({ effects }) => {
    // The main volume is automatically restored
  },
});

// Actions (optional custom actions from the UI)
export const actions = setupActions({});

// Export the full service
export default createService({
  manifest,
  init,
  uninit,
  main,
  health,
  config,
  properties,
  migrations,
  backups,
  actions,
});
