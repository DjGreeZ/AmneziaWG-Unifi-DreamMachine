#!/bin/sh
set -eu
printf '\n  AWG Manager · загрузка v0.1.1\n  Developed by Roman Tselischev / https://vk.com/greez\n\n'
BASE=https://raw.githubusercontent.com/DjGreeZ/AmneziaWG-Unifi-DreamMachine/v0.1.1
TMPDIR_AWG=$(mktemp -d /tmp/awg-download.XXXXXX)
trap 'rm -rf "$TMPDIR_AWG"' EXIT HUP INT TERM
cd "$TMPDIR_AWG"
curl -fL --progress-bar "$BASE/AWG-Manager-UDM-5.1.33.run" -o AWG-Manager-UDM-5.1.33.run
curl -fL --progress-bar "$BASE/AWG-Manager-UDM-5.1.33.sha256" -o checksums
printf '\n  Проверка целостности пакета…\n'
sha256sum -c checksums
sh ./AWG-Manager-UDM-5.1.33.run
