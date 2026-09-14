#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Запустите от root.'; exit 1; }
case "${1-}" in ''|--purge) ;; *) echo 'Использование: uninstall.sh [--purge]'; exit 1;; esac
python3 /data/awg-native/uninstall.py "$@"
