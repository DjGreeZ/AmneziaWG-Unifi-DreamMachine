#!/bin/sh
set -eu
printf '\n  AWG MANAGER  ·  v0.1.1\n  AmneziaWG для UniFi Dream Machine\n  Developed by Roman Tselischev / https://vk.com/greez\n\n'
step() { printf '\n  [%s/5] %s\n' "$1" "$2"; }
step 1 'Проверка совместимости'
[ "$(id -u)" = 0 ] || { echo 'Run as root.'; exit 1; }
python3 - <<'PYVERSION'
import re, subprocess
from pathlib import Path
firmware = Path('/usr/lib/version').read_text().strip()
m = re.match(r'UDM\.al324\.v(\d+)\.(\d+)\.(\d+)(?:\.|$)', firmware)
if not m:
    raise SystemExit('Supported hardware: UDM al324 only.')
if tuple(map(int, m.groups())) < (5, 1, 33):
    raise SystemExit('UniFi OS 5.1.33 or newer is required.')
network = None
for package in ('unifi-native', 'unifi'):
    result = subprocess.run(['dpkg-query', '-W', '-f=${Status}\t${Version}', package], text=True, capture_output=True)
    status, separator, version = result.stdout.strip().partition('\t')
    if result.returncode == 0 and separator and status == 'install ok installed':
        network = version
        break
if network is None:
    raise SystemExit('Installed UniFi Network package (unifi-native or unifi) not found.')
n = re.match(r'(?:\d+:)?(\d+)\.(\d+)\.(\d+)(?:[-+~.]|$)', network)
if not n or tuple(map(int, n.groups())) < (10, 6, 101):
    raise SystemExit('UniFi Network 10.6.101 or newer is required; detected: ' + network)
print('Version requirements met. Tested on OS 5.1.33 / Network 10.6.101; newer versions are allowed.')
PYVERSION
[ "$(uname -m)" = aarch64 ] || exit 1
for tool in python3 ip wg openssl systemctl curl iptables; do command -v "$tool" >/dev/null || { echo "Missing: $tool"; exit 1; }; done
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=/data/awg-manager
umask 077
if [ ! -f "$ROOT/manager.py" ]; then
 if ip netns list | awk '{print $1}' | grep -qx awgm; then echo 'Namespace awgm already exists; aborting.'; exit 1; fi
 if ss -lntu | grep -Eq ':(51899|8449)[[:space:]]'; then echo 'A required port is occupied; aborting.'; exit 1; fi
fi
mkdir -p "$ROOT/bin"
step 2 'Пароль менеджера'
python3 "$HERE/setup_auth.py"
if [ -f "$ROOT/manager.py" ]; then cp "$ROOT/manager.py" "$ROOT/manager.previous.py"; fi
step 3 'Установка компонентов'
systemctl stop awg-manager.service 2>/dev/null || true
install -m 755 "$HERE/bin/awg" "$HERE/bin/amneziawg-go" "$ROOT/bin/"
install -m 700 "$HERE/manager.py" "$ROOT/manager.py"
install -m 700 "$HERE/uninstall.sh" "$ROOT/uninstall.sh"
step 4 'Настройка локального подключения'
if [ ! -f "$ROOT/settings.env" ]; then
 ADDR=$(ip -4 -o addr show dev br0 | awk 'NR==1 {split($4,a,"/");print a[1]}')
 [ -n "$ADDR" ] || { echo 'LAN address on br0 not found.'; exit 1; }
 printf 'AWGM_BIND_ADDRESS=%s\nAWGM_PORT=8449\n' "$ADDR" > "$ROOT/settings.env"
fi
. "$ROOT/settings.env"
export AWGM_BIND_ADDRESS AWGM_PORT
if [ ! -f "$ROOT/bridge.key" ]; then wg genkey > "$ROOT/bridge.key"; wg pubkey < "$ROOT/bridge.key" > "$ROOT/bridge.pub"; fi
if [ ! -f "$ROOT/client.key" ]; then wg genkey > "$ROOT/client.key"; wg pubkey < "$ROOT/client.key" > "$ROOT/client.pub"; fi
python3 - <<'PY'
from pathlib import Path
import runpy,os
p=Path('/data/awg-manager');read=lambda n:(p/n).read_text().strip()
module=runpy.run_path(str(p/'manager.py'),run_name='installer_validation')
if (p/'active.conf').exists():module['parse']((p/'active.conf').read_text())
(p/'bridge.conf').write_text('[Interface]\nPrivateKey = '+read('bridge.key')+'\nListenPort = 51899\nListenIP = 127.0.0.1\n[Peer]\nPublicKey = '+read('client.pub')+'\nAllowedIPs = 0.0.0.0/0\n')
(p/'unifi-client.conf').write_text('[Interface]\nPrivateKey = '+read('client.key')+'\nAddress = 10.254.252.2/32\nDNS = 1.1.1.1\nMTU = 1280\n[Peer]\nPublicKey = '+read('bridge.pub')+'\nAllowedIPs = 0.0.0.0/0\nEndpoint = 127.0.0.1:51899\nPersistentKeepalive = 15\n')
PY
if [ ! -f "$ROOT/cert.pem" ]; then
 openssl req -x509 -newkey rsa:2048 -nodes -keyout "$ROOT/tls.key" -out "$ROOT/cert.pem" -days 365 -subj "/CN=$AWGM_BIND_ADDRESS" -addext "subjectAltName=IP:$AWGM_BIND_ADDRESS" >/dev/null 2>&1
fi
cat > /etc/systemd/system/awg-manager.service <<'UNIT'
[Unit]
Description=AWG Manager development bridge
After=network-online.target unifi.service
Wants=network-online.target
[Service]
Type=simple
EnvironmentFile=/data/awg-manager/settings.env
Environment=GOMEMLIMIT=128MiB
ExecStart=/usr/bin/python3 /data/awg-manager/manager.py
Restart=on-failure
RestartSec=10
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
step 5 'Запуск менеджера'
systemctl daemon-reload
systemctl enable --now awg-manager.service
printf '\n  ГОТОВО — AWG Manager установлен\n\n  Открыть: https://%s:%s/\n\n' "$AWGM_BIND_ADDRESS" "$AWGM_PORT"
echo '  1. Войдите с паролем менеджера.'
echo '  2. Загрузите AWG-конфиг и дождитесь проверки.'
echo '  3. Скачайте профиль и импортируйте его в UniFi VPN Client.'
echo '  При обновлении существующие пароль и конфиг сохраняются.'
printf '\n'
