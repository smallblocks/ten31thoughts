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

# Build Docker image
# CRITICAL: The tag format MUST be start9/PKG_ID/IMAGE_NAME:PKG_VERSION
# where IMAGE_NAME matches the `main.image` field in manifest.yaml
image.tar: Dockerfile src/ requirements.txt frontend/
	docker buildx build \
		--tag start9/$(PKG_ID)/main:$(PKG_VERSION) \
		--platform linux/$(ARCH) \
		-o type=docker,dest=image.tar \
		.

# Package into s9pk (V1 format - will be converted to V2)
$(PKG_ID).s9pk: manifest.yaml image.tar INSTRUCTIONS.md LICENSE icon.png
	start-sdk pack

# Verify the built package
verify: $(PKG_ID).s9pk
	start-sdk verify $(PKG_ID).s9pk

# Install to a running StartOS device (requires start-cli configured)
install: $(PKG_ID).s9pk
	start-cli package install $(PKG_ID).s9pk
