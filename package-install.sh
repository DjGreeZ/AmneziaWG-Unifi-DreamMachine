#!/bin/sh
set -eu
printf '\n  AmneziaWG · UniFi Dream Machine · v0.2.0\n  Developed by Roman Tselischev / https://vk.com/greez\n\n'
printf '  Экспериментальная интеграция. Используйте на свой страх и риск.\n  Обновления UniFi OS и Network не проверены и не рекомендуются.\n\n'
[ "$(id -u)" = 0 ] || { echo 'Запустите установщик от root.'; exit 1; }
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=/data/awg-native
for tool in python3 ip wg systemctl curl iptables nginx ss ubios-udapi-client; do
 command -v "$tool" >/dev/null || { echo "Отсутствует компонент: $tool"; exit 1; }
done
[ "$(uname -m)" = aarch64 ] || { echo 'Требуется aarch64.'; exit 1; }
[ -c /dev/net/tun ] || { echo 'Недоступен TUN.'; exit 1; }
[ ! -f /data/awg-manager/manager.py ] || { echo 'Сначала удалите AWG Manager.'; exit 1; }
printf '  [1/4] Проверка системы и исходных файлов\n'
python3 "$HERE/prepare_install.py" --check
if [ ! -f "$ROOT/service.py" ]; then
 if ip netns list | awk '{print $1}' | grep -qx awgm; then echo 'Имя awgm уже занято.'; exit 1; fi
 if ss -lnu | grep -Eq ':51899[[:space:]]'; then echo 'Порт 51899 уже занят.'; exit 1; fi
fi
umask 077
printf '  [2/4] Подготовка компонентов и резервных копий\n'
python3 "$HERE/prepare_install.py"
systemctl stop awg-native-maintain.timer awg-native-maintain.service awg-native.service 2>/dev/null || true
mkdir -p "$ROOT/bin"
install -m 755 "$HERE/bin/awg" "$HERE/bin/amneziawg-go" "$ROOT/bin/"
for file in service.py maintain.py uninstall.py uninstall.sh; do install -m 700 "$HERE/$file" "$ROOT/$file"; done
for file in route.conf cache-loader.js refresh.html; do install -m 644 "$HERE/$file" "$ROOT/$file"; done
for name in bridge client; do
 if [ ! -f "$ROOT/$name.key" ]; then wg genkey > "$ROOT/$name.key"; fi
 wg pubkey < "$ROOT/$name.key" > "$ROOT/$name.pub"
done
python3 - <<'PY'
from pathlib import Path
p=Path('/data/awg-native');read=lambda n:(p/n).read_text().strip()
(p/'bridge.conf').write_text('[Interface]\nPrivateKey = '+read('bridge.key')+'\nListenPort = 51899\nListenIP = 127.0.0.1\n[Peer]\nPublicKey = '+read('client.pub')+'\nAllowedIPs = 0.0.0.0/0\n')
(p/'unifi-client.conf').write_text('[Interface]\nPrivateKey = '+read('client.key')+'\nAddress = 10.254.252.2/32\nDNS = 1.1.1.1\nMTU = 1280\n[Peer]\nPublicKey = '+read('bridge.pub')+'\nAllowedIPs = 0.0.0.0/0\nEndpoint = 127.0.0.1:51899\nPersistentKeepalive = 15\n')
PY
printf '  [3/4] Подключение к панели UniFi\n'
cat > /etc/systemd/system/awg-native.service <<'UNIT'
[Unit]
Description=AmneziaWG integration for UniFi
After=network-online.target unifi-core.service unifi.service nginx.service
[Service]
Type=simple
RuntimeDirectory=awg-native
RuntimeDirectoryMode=0750
Group=nginx
UMask=0077
Environment=GOMEMLIMIT=128MiB
ExecStartPre=/usr/bin/python3 /data/awg-native/maintain.py
ExecStart=/usr/bin/python3 /data/awg-native/service.py
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
# Remove only the legacy drop-in belonging to this integration.
rm -f /etc/systemd/system/awg-native.service.d/persistence.conf
cat > /etc/systemd/system/awg-native-maintain.service <<'UNIT'
[Unit]
Description=Maintain version-checked UniFi AWG integration
After=unifi-core.service nginx.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /data/awg-native/maintain.py
UNIT
cat > /etc/systemd/system/awg-native-maintain.timer <<'UNIT'
[Unit]
Description=Restore AWG integration after UniFi route regeneration
[Timer]
OnBootSec=45s
OnUnitActiveSec=15s
Unit=awg-native-maintain.service
[Install]
WantedBy=timers.target
UNIT
python3 "$ROOT/maintain.py"
printf '  [4/4] Запуск\n'
systemctl daemon-reload
systemctl enable --now awg-native.service awg-native-maintain.timer
systemctl is-active --quiet awg-native.service
printf '\n  Готово. Откройте UniFi Network → Settings → VPN → VPN Client.\n  Создайте профиль типа AmneziaWG и загрузите ваш AWG-конфиг.\n  В политике маршрутизации включите Kill Switch.\n\n  Удаление: sh /data/awg-native/uninstall.sh\n\n'
