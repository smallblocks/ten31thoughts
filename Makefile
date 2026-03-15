PKG_ID := tenthoughts
PKG_VERSION := 0.3.0.1

# Detect platform
PLATFORM := $(shell uname -m)
ifeq ($(PLATFORM),x86_64)
ARCH := amd64
else ifeq ($(PLATFORM),aarch64)
ARCH := arm64
else
ARCH := amd64
endif

.PHONY: all clean verify install

all: $(PKG_ID).s9pk

clean:
	rm -f image.tar $(PKG_ID).s9pk
	rm -rf node_modules dist

# Install SDK TypeScript dependencies if package.json exists
node_modules: package.json
	npm install || true

# Build Docker image
image.tar: Dockerfile src/ requirements.txt frontend/
	docker buildx build \
		--tag start9/$(PKG_ID)/main:$(PKG_VERSION) \
		--platform linux/$(ARCH) \
		-o type=docker,dest=image.tar \
		.

# Package into s9pk
# The SDK will compile TypeScript from startos/ if present,
# or use manifest.yaml directly for V1-style packages
$(PKG_ID).s9pk: manifest.yaml image.tar INSTRUCTIONS.md LICENSE icon.png node_modules
	start-sdk pack

# Verify
verify: $(PKG_ID).s9pk
	start-sdk verify $(PKG_ID).s9pk

# Install to a running StartOS device
install: $(PKG_ID).s9pk
	start-cli package install $(PKG_ID).s9pk
