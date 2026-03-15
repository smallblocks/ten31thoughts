# Ten31 Thoughts - StartOS Package
# Overrides to s9pk.mk must precede the include statement

# Custom image ingredients (not from registry)
images/main.tar: Dockerfile src/ requirements.txt frontend/
	mkdir -p images
	docker buildx build \
		--tag start9/tenthoughts/main:0.3.0.1 \
		--platform=linux/amd64 \
		-o type=docker,dest=images/main.tar \
		.

include s9pk.mk
