#!/bin/sh
set -eu
echo 'Developed by Roman Tselischev / https://vk.com/greez'
BASE=https://raw.githubusercontent.com/DjGreeZ/AmneziaWG-Unifi-DreamMachine/main
TMPDIR_AWG=$(mktemp -d /tmp/awg-download.XXXXXX)
trap 'rm -rf "$TMPDIR_AWG"' EXIT HUP INT TERM
cd "$TMPDIR_AWG"
curl -fL "$BASE/AWG-Manager-UDM-5.1.33.run" -o AWG-Manager-UDM-5.1.33.run
curl -fL "$BASE/AWG-Manager-UDM-5.1.33.sha256" -o checksums
sha256sum -c checksums
sh ./AWG-Manager-UDM-5.1.33.run
