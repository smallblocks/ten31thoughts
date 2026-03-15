# Ten31 Thoughts — V2 s9pk Migration Guide

## What Changed (V1 → V2)

The StartOS 0.4.0 SDK has a completely different TypeScript API from what was
in the existing repo. Here's a summary of the key architectural changes:

### Old (V1) API — ❌ Does not exist in 0.4.0-beta SDK
```ts
import { setupManifest, setupMain, setupHealth, setupConfig,
         setupInit, setupUninit, createService } from "@start9labs/start-sdk"
// These function signatures were guessed/wrong.
// createService(), setupHealth([...]), effects.runDaemon() — none of these exist.
```

### New (V2) API — ✅ Actual SDK surface
```ts
import { setupManifest, StartSdk, VersionInfo, VersionGraph, IMPOSSIBLE,
         setupI18n } from "@start9labs/start-sdk"

const sdk = StartSdk.of(manifest)    // typed SDK instance
sdk.setupMain(...)                    // uses sdk.Daemons.of(), sdk.SubContainer.of()
sdk.setupInterfaces(...)              // uses sdk.MultiHost, sdk.createInterface()
sdk.setupBackups(...)                 // returns { backups, restoreInit }
sdk.setupInit(...)                    // ordered list of init functions
sdk.setupDependencies(...)            // dependency declarations
sdk.setupActions(...)                 // custom actions
```

### Key Architectural Differences

| Concept | Old (Wrong) | New (V2) |
|---------|-------------|----------|
| Service entry | `createService({...})` | Exports from `startos/index.ts` |
| Daemons | `effects.runDaemon({command, args, env})` | `sdk.Daemons.of(effects).addDaemon(...)` with SubContainer |
| Health checks | `setupHealth([{fn: ...}])` | Built into daemon's `ready:` field |
| Config | `setupConfig(null)` | Not needed — no config = no file |
| Properties | `setupProperties(...)` | Replaced by interfaces + actions |
| Interfaces | Defined in `manifest.yaml` | `sdk.setupInterfaces()` in TypeScript |
| Backups | `setupBackups({create, restore})` | `sdk.setupBackups({ volumes: [...] })` |
| Migrations | `setupMigrations({})` | `VersionGraph.of()` + `VersionInfo.of()` |
| Manifest | Both `manifest.yaml` + TS | TS only via `setupManifest()` |
| Build | `start-sdk pack` (direct) | `ncc build` → `javascript/index.js` → `start-cli pack` |
| Docker images | Single `image.tar` | Multi-arch via `s9pk.mk` shared build logic |
| CI | Custom workflow | Shared workflows from `start9labs/shared-workflows` |

## Files to DELETE from old repo

```
startos/index.ts          # Completely rewritten (wrong API)
tsconfig.json             # Replaced with V2 version
package.json              # Replaced with V2 version (ncc build)
manifest.yaml             # No longer needed — manifest is in TypeScript
Makefile                  # Replaced with V2 minimal version
.github/workflows/buildService.yml  # Replaced with shared workflow
```

## Files to ADD (from this package)

```
package.json              # ncc + start-sdk deps
tsconfig.json             # CommonJS output for ncc
Makefile                  # Minimal: `include s9pk.mk`
s9pk.mk                   # MUST DOWNLOAD from hello-world-startos template
.gitignore                # Updated for V2 artifacts
CONTRIBUTING.md           # Build instructions
assets/ABOUT.md           # Required (can be minimal)

startos/
├── sdk.ts                # SDK init boilerplate
├── utils.ts              # Constants (uiPort)
├── index.ts              # Module exports
├── main.ts               # Daemons + health check
├── interfaces.ts         # Network interface definitions
├── backups.ts            # Volume backup config
├── dependencies.ts       # Empty deps
├── manifest/
│   ├── index.ts          # setupManifest()
│   └── i18n.ts           # Locale strings
├── i18n/
│   ├── index.ts          # setupI18n()
│   └── dictionaries/
│       ├── default.ts    # English strings
│       └── translations.ts
├── init/
│   └── index.ts          # Init sequence
├── install/
│   ├── versionGraph.ts   # Version graph
│   └── versions/
│       ├── index.ts      # Current version export
│       └── v0.3.0.1.a0.ts
└── actions/
    └── index.ts          # Empty actions

.github/workflows/
├── buildService.yml      # V2 shared build workflow
└── releaseService.yml    # V2 shared release workflow
```

## Files to KEEP (unchanged)

```
Dockerfile                # Your working Docker build — no changes needed
src/                      # Your Python/FastAPI app — no changes needed
frontend/                 # Your React frontend — no changes needed
scripts/                  # Seed scripts — no changes needed
docker_entrypoint/        # Migration scripts — no changes needed
requirements.txt          # Python deps — no changes needed
icon.png / icon.svg       # Service icon — keep (rename to icon.svg if needed)
LICENSE                   # Keep
INSTRUCTIONS.md           # Keep (referenced by assets/)
README.md                 # Update to reflect V2 build process
```

## Step-by-Step Migration

### 1. Download s9pk.mk (CRITICAL)
```bash
curl -fsSL https://raw.githubusercontent.com/Start9Labs/hello-world-startos/update/040/s9pk.mk -o s9pk.mk
```

### 2. Delete old files
```bash
rm -f manifest.yaml
rm -f startos/index.ts
rm -f tsconfig.json
rm -f package.json
rm -f package-lock.json
rm -rf node_modules
```

### 3. Copy all new files from this package
Copy the entire contents of this delivery into your repo root, preserving
the directory structure.

### 4. Install dependencies
```bash
npm install
```

### 5. Verify TypeScript compiles
```bash
npx tsc --noEmit
```

### 6. Build
```bash
make x86    # or make arm, or just make
```

### 7. Set up GitHub Secrets
For CI, add these repository secrets:
- `DEV_KEY` — your StartOS developer key

For releases, also add:
- `REGISTRY`, `S3_S9PKS_BASE_URL` (as repository variables)
- `S3_ACCESS_KEY`, `S3_SECRET_KEY` (as secrets)

## Version String

The V2 SDK uses Extended Versioning (ExVer): `<upstream>:<downstream>[-prerelease]`

Your old version `0.3.0.1` maps to ExVer as `0.3.0:1-alpha.0`.

When you're ready for a stable release, create a new version file for `0.3.0:1`.
