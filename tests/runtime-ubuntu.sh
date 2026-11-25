#!/bin/sh
set -eu

apt-get update
apt-get install -y --no-install-recommends musl
/opt/ffmpeg/bin/ffmpeg -version
