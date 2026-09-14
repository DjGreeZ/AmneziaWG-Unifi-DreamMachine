#!/bin/sh
set -eu
systemctl disable --now awg-manager.service
ip netns del awgm 2>/dev/null || true
rm -f /etc/systemd/system/awg-manager.service
systemctl daemon-reload
echo 'Service removed. Configurations and keys preserved in /data/awg-manager.'
echo 'Disable or update the associated VPN policy/profile in UniFi if no longer needed.'
