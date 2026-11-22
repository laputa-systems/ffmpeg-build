PYTHON ?= sh bootstrap/buildlib-run --
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
MUTATION_BASE ?= origin/main
MUTATION_SCOPE ?=
MUTATION_BUILDLIB ?= $(HOME)/repos/laputa-systems/buildlib
VERSION = $(shell $(PYTHON) build.py version)

ifneq ($(findstring linux,$(TARGET)),)
build_profile = scripts/linux-build.sh $(TARGET) $(1)
verify_archive = scripts/linux-qualify.sh $(1)
else
build_profile = $(PYTHON) build.py build --target $(TARGET) --profile $(1) && $(PYTHON) build.py audit --target $(TARGET) --profile $(1)
verify_archive = $(PYTHON) build.py qualify --archive $(1)
endif

.PHONY: coverage mutants-diff fetch build package verify lint test setup clean

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
	$(PYTHON) -m unittest discover -s tests

setup:
	sh scripts/setup-dev

coverage:
	mkdir -p .work/coverage
	uv run --frozen coverage erase
	uv run --frozen coverage run -m unittest discover -s tests
	uv run --frozen coverage combine
	uv run --frozen coverage report
	uv run --frozen coverage json -o .work/coverage/report.json

mutants-diff:
	scripts/mutants-diff.sh "$(MUTATION_BASE)" "$(MUTATION_BUILDLIB)" "$(MUTATION_SCOPE)"

lint:
	uv run --frozen ruff check .
	uv run --frozen ty check

clean:
	@for parent in ./.work; do \
	  if test -L "$$parent"; then printf '%s\n' "make clean: $$parent must be a local directory" >&2; exit 1; fi; \
	done
	@for artifact in ./dist ./.work/build ./.work/stage; do \
	  if test -L "$$artifact" || { test -e "$$artifact" && ! test -d "$$artifact"; }; then \
	    printf '%s\n' "make clean: $$artifact must be a local build directory" >&2; exit 1; \
	  fi; \
	done
	rm -rf -- ./dist ./.work/build ./.work/stage
