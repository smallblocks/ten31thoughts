# Contributing to Ten31 Thoughts for StartOS

## Prerequisites

Follow the [StartOS Packaging Guide — Environment Setup](https://docs.start9.com/packaging/environment-setup.html) to install:

- Docker + Buildx
- Node.js v22 (LTS)
- Make
- SquashFS tools
- `start-cli`

## Build

```bash
npm ci
make
```

This produces a `tenthoughts_<arch>.s9pk` in the project root.

## Install to StartOS

Configure your server in `~/.startos/config.yaml`:

```yaml
host: http://your-server.local
```

Then:

```bash
make install
```

## Architecture

Build for a specific architecture:

```bash
make x86   # x86_64 only
make arm   # aarch64 only
```
