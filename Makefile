PYTHON ?= python3
HOST_OS := $(shell uname -s)
HOST_ARCH := $(shell uname -m)
ifeq ($(HOST_OS),Darwin)
TARGET ?= aarch64-apple-darwin
else ifeq ($(filter aarch64 arm64,$(HOST_ARCH)),$(HOST_ARCH))
TARGET ?= aarch64-unknown-linux-musl
else
TARGET ?= x86_64-unknown-linux-musl
endif
PROFILES ?= play-sdk tools runtime $(if $(filter x86_64-unknown-linux-musl,$(TARGET)),fixtures)
VERSION = $(shell $(PYTHON) build.py version)

ifneq ($(findstring linux,$(TARGET)),)
build_profile = scripts/linux-build.sh $(TARGET) $(1)
verify_archive = scripts/linux-qualify.sh $(1)
else
build_profile = $(PYTHON) build.py build --target $(TARGET) --profile $(1) && $(PYTHON) build.py audit --target $(TARGET) --profile $(1)
verify_archive = $(PYTHON) build.py qualify --archive $(1)
endif

.PHONY: fetch build package verify lint test clean

fetch:
	@set -eu; for profile in $(PROFILES); do $(PYTHON) build.py fetch --target $(TARGET) --profile $$profile; done

build:
	@set -eu; for profile in $(PROFILES); do \
		$(call build_profile,$$profile); \
		$(PYTHON) build.py package --target $(TARGET) --profile $$profile; \
	done

package:
	@set -eu; for profile in $(PROFILES); do $(PYTHON) build.py package --target $(TARGET) --profile $$profile; done

verify:
	@set -eu; version=$(VERSION); for profile in $(PROFILES); do \
		$(call verify_archive,dist/ffmpeg-$$profile-$$version-$(TARGET).tar.xz); \
	done

test:
	uv run --frozen python -m unittest discover -s tests

lint:
	uv run --frozen ruff check .
	uv run --frozen ty check

clean:
	rm -rf dist .work/build .work/stage .work/tmp .venv
	find . -path './.git' -prune -o -path './.work' -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
