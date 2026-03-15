# Ten31 Thoughts — StartOS V2 Packaging Issue

## Summary
Building a StartOS 0.4.0 package for Ten31 Thoughts. The package builds successfully as V1 format but StartOS 0.4 requires V2 format. Conversion and native V2 builds both fail.

## Environment
- **Target:** StartOS 0.4.0-alpha.20
- **Package ID:** `tenthoughts`
- **Repo:** https://github.com/smallblocks/ten31thoughts
- **Build:** GitHub Actions with `Start9Labs/sdk@v1` action

## What Works
1. ✅ Docker image builds successfully (FastAPI + React + ChromaDB)
2. ✅ V1 s9pk packages successfully with `start-sdk pack`
3. ✅ All dependencies compile (including chromadb native extensions)

## What Fails

### Failure 1: V1 s9pk rejected by StartOS 0.4
```
Version 1 s9pk detected. This package format is deprecated.
```
StartOS 0.4 UI shows this error when trying to sideload the V1 package.

### Failure 2: V2 conversion fails
When `start-sdk pack` auto-converts to V2:
```
S9PK Parsing Error: Single arch legacy s9pk is malformed
```

### Failure 3: Native V2 build with `start-cli s9pk pack`
```
Javascript Engine Error: Cannot find module './javascript/index.js'
```
The V2 SDK requires JavaScript SDK files that we don't have properly structured.

### Failure 4: Minimal JavaScript stubs
Created `javascript/index.js` with minimal exports:
```javascript
export const setConfig = null;
export const getConfig = null;
export const properties = null;
export const migration = null;
```
Result: `Deserialization Error: expected value at line 1 column 1`

## Current File Structure
```
ten31-thoughts/
├── .github/workflows/buildService.yml
├── Dockerfile
├── Makefile
├── manifest.yaml
├── INSTRUCTIONS.md
├── LICENSE
├── icon.png
├── icon.svg
├── javascript/
│   └── index.js          # Minimal stubs (doesn't work)
├── scripts/
│   └── seed_feeds.py
├── docker_entrypoint/
│   └── migration.sh
├── frontend/              # React app
├── src/                   # FastAPI app
└── requirements.txt
```

## Current manifest.yaml
```yaml
id: tenthoughts
title: "Ten31 Thoughts"
version: 0.3.0.1
release-notes: "Initial release of Ten31 Thoughts macro intelligence service."
license: mit
wrapper-repo: "https://github.com/smallblocks/ten31thoughts"
upstream-repo: "https://github.com/smallblocks/ten31thoughts"
support-site: "https://ten31.xyz"
marketing-site: "https://ten31timestamp.com"
build:
  - make
min-os-version: 0.3.5
description:
  short: "Macro intelligence service coordinating your thesis with external voices"
  long: "Ten31 Thoughts ingests your published macro framework alongside external macro interviews to surface the top mental models for navigating the current macro landscape."
assets:
  license: LICENSE
  icon: icon.png
  instructions: INSTRUCTIONS.md
  docker-images: image.tar
main:
  type: docker
  image: main
  entrypoint: "/usr/local/bin/uvicorn"
  args:
    - "src.app:app"
    - "--host"
    - "0.0.0.0"
    - "--port"
    - "8431"
    - "--workers"
    - "1"
  mounts:
    main: /data
health-checks:
  web-ui:
    name: Web Interface
    success-message: Ten31 Thoughts is ready
    type: docker
    image: main
    entrypoint: "curl"
    args:
      - "-f"
      - "http://tenthoughts.embassy:8431/api/health"
    inject: true
    system: false
    io-format: json
config: ~
properties: ~
volumes:
  main:
    type: data
interfaces:
  main:
    name: Web Interface
    description: Access the Ten31 Thoughts dashboard and chat
    tor-config:
      port-mapping:
        80: "8431"
    lan-config:
      443:
        ssl: true
        internal: 8431
    ui: true
    protocols:
      - tcp
      - http
dependencies: {}
backup:
  create:
    type: docker
    image: compat
    system: true
    entrypoint: compat
    args:
      - duplicity
      - tenthoughts
      - /mnt/backup
      - /root/data
    mounts:
      BACKUP: /mnt/backup
      main: /root/data
  restore:
    type: docker
    image: compat
    system: true
    entrypoint: compat
    args:
      - duplicity
      - tenthoughts
      - /mnt/backup
      - /root/data
    mounts:
      BACKUP: /mnt/backup
      main: /root/data
migrations:
  from: {}
  to: {}
```

## Key Questions for Start9

1. **What is the minimum JavaScript SDK structure for V2 packages?**
   - For a simple package with no config UI (`config: ~`)
   - What exports are required?
   - What TypeScript compilation is needed?

2. **Why does "Single arch legacy s9pk is malformed" occur?**
   - The V1 package builds successfully
   - The auto-conversion to V2 fails with this error
   - Is it an image.tar format issue? Manifest issue?

3. **Is there a working example of a simple V2 package?**
   - No config, no properties, just a Docker container with web UI
   - Similar to our use case

## Attempted Solutions
1. ❌ Using `start-cli s9pk pack` directly (requires JavaScript SDK)
2. ❌ Creating minimal `javascript/index.js` stubs (parse error)
3. ❌ Building V1 then converting with `start-cli s9pk convert` (malformed error)
4. ❌ Various manifest adjustments (migrations, health-check format)

## Recommendations

### Option A: Get Start9 Guidance
Ask in Start9 Discord/Matrix for:
- Minimal V2 package template
- JavaScript SDK documentation for 0.4
- Working example to copy

### Option B: Proper JavaScript SDK Setup
1. Look at `filebrowser-startos` which has `scripts/embassy.ts`
2. Set up TypeScript compilation with `@start9labs/start-sdk`
3. Export proper functions even if they're stubs

### Option C: Alternative Deployment
Run Ten31 Thoughts as standalone Docker on the StartOS host without packaging.

## Files to Share with Claude
1. This document
2. `/data/.openclaw/workspace/ten31-thoughts/manifest.yaml`
3. `/data/.openclaw/workspace/ten31-thoughts/Makefile`
4. `/data/.openclaw/workspace/ten31-thoughts/.github/workflows/buildService.yml`
5. Reference: https://github.com/Start9Labs/filebrowser-startos (working V2 package)

## Build Logs
Latest failed build: https://github.com/smallblocks/ten31thoughts/actions
Error: `S9PK Parsing Error: Single arch legacy s9pk is malformed`
