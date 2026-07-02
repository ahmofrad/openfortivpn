#!/bin/sh

set -e

PREFIX="$1"

[ -x "${PREFIX}/bin/openssl" ] && exit 0

# OpenSSL 1.0.2u source tarball is no longer available at openssl.org.
# Use the system libssl-dev instead of building from source.
if pkg-config --exists openssl; then
    exit 0
fi

sudo apt-get update
sudo apt-get install -y libssl-dev
