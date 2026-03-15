PKG_ID := tenthoughts
PKG_VERSION := 0.3.0.1

TS_FILES := $(shell find startos -name '*.ts' 2>/dev/null)

.PHONY: all clean verify install

all: $(PKG_ID).s9pk

clean:
	rm -rf docker-images javascript node_modules
	rm -f $(PKG_ID).s9pk

# Install npm dependencies
node_modules: package.json
	npm install

# Build TypeScript SDK to JavaScript bundle
javascript/index.js: $(TS_FILES) node_modules
	npm run build

# Build x86_64 Docker image
docker-images/x86_64.tar: Dockerfile src/ requirements.txt frontend/
	mkdir -p docker-images
	DOCKER_BUILDKIT=1 docker buildx build \
		--tag start9/$(PKG_ID)/main:$(PKG_VERSION) \
		--platform=linux/amd64 \
		-o type=docker,dest=docker-images/x86_64.tar \
		.

# Build aarch64 Docker image
docker-images/aarch64.tar: Dockerfile src/ requirements.txt frontend/
	mkdir -p docker-images
	DOCKER_BUILDKIT=1 docker buildx build \
		--tag start9/$(PKG_ID)/main:$(PKG_VERSION) \
		--platform=linux/arm64/v8 \
		-o type=docker,dest=docker-images/aarch64.tar \
		.

# Package into s9pk
$(PKG_ID).s9pk: manifest.yaml INSTRUCTIONS.md LICENSE icon.png javascript/index.js docker-images/x86_64.tar docker-images/aarch64.tar
	start-sdk pack

# Verify the package
verify: $(PKG_ID).s9pk
	start-sdk verify s9pk $(PKG_ID).s9pk

# Install to StartOS
install: $(PKG_ID).s9pk
	start-cli package install $(PKG_ID).s9pk
