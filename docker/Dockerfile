FROM --platform=linux/amd64 alpine@sha256:266f29255458134745f2bf588cb23ed1ed1768b96ff2580a05d70a8aba59e145 AS alpine-amd64
FROM --platform=linux/arm64 alpine@sha256:42d86a3173522de4786cfba0b5d631dbadb3d03a86d218dafb070dafd9809c7e AS alpine-arm64

ARG TARGETARCH
FROM alpine-${TARGETARCH} AS build
RUN apk add --no-cache \
        bash build-base binutils curl file git linux-headers meson nasm ninja \
        pkgconf python3 tar xz bzip2 \
        libva-dev libdrm-dev
WORKDIR /work

FROM alpine-${TARGETARCH} AS fixtures
RUN apk add --no-cache bash ffmpeg file python3
WORKDIR /work

FROM alpine-${TARGETARCH} AS runtime
RUN apk add --no-cache bash file python3
WORKDIR /work
