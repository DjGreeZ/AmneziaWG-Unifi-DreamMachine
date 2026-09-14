#!/bin/sh
set -eu
printf '\n  AmneziaWG для UniFi Dream Machine · v0.2.1\n  Developed by Roman Tselischev / https://vk.com/greez\n\n'
BASE=https://raw.githubusercontent.com/DjGreeZ/AmneziaWG-Unifi-DreamMachine/v0.2.1
TMP=$(mktemp -d /tmp/awg-download.XXXXXX)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
cd "$TMP"
curl -fL --progress-bar "$BASE/AmneziaWG-UniFi-v0.2.1.run" -o AmneziaWG-UniFi-v0.2.1.run
curl -fsSL "$BASE/AmneziaWG-UniFi-v0.2.1.sha256" -o checksums
sha256sum -c checksums
sh AmneziaWG-UniFi-v0.2.1.run
