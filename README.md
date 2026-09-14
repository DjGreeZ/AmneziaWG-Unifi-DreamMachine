# AWG Manager — UDM prototype 0.1

Requires UDM al324, UniFi OS >= 5.1.33 and Network >= 10.6.101.
Newer versions are allowed; tested on OS 5.1.33 / Network 10.6.101.

Developed by Roman Tselischev / https://vk.com/greez
One AWG profile, IPv4 routing. This is an experimental release.

Install over SSH as root (no AWG config required):

```sh
curl -fL https://raw.githubusercontent.com/DjGreeZ/AmneziaWG-Unifi-DreamMachine/main/install.sh -o /tmp/awg-install.sh && sh /tmp/awg-install.sh
```

Or download and run the self-extracting installer:

    sh AWG-Manager-UDM-5.1.33.run

Existing keys, active configuration and password are preserved on updates.

The manager is served via HTTPS on the br0 IPv4 address, port 8449. Its certificate
is self-signed. A fresh install prompts in the SSH terminal for a password
(at least 12 characters) and confirmation. Input is hidden; only a salted hash
is stored. Existing installations retain their password.

After installation, open the manager and upload your first AWG .conf. The manager
checks the connection; after success, download the UniFi profile. If the first
check fails, correct the config and upload again. No config is required by the installer.
All AWG binaries are bundled; a public download command needs a published release URL.

Import the generated UniFi WireGuard config once, then configure routing policies
in UniFi. Replacing the AWG config through the manager preserves the local profile.
A failing candidate is rolled back. Keep UniFi Kill Switch enabled. DNS from the
AWG file is not applied to the LAN; generated UniFi config specifies 1.1.1.1.

Architecture: the native UniFi WG client connects over 127.0.0.1:51899 to a kernel
WG server whose interface lives in a dedicated network namespace. That namespace
routes and NATs traffic through the AWG TUN. The AWG UDP socket remains in the
root namespace. No native wg binary or UniFi web assets are replaced.

Health checks send an HTTPS request to 1.1.1.1 through AWG every 15 seconds. Two
consecutive failures lower the bridge; native UniFi status may lag. The manager
shows the external connection status. Restarting a failed engine is automatic.

Reserved resources: namespace awgm, interfaces awgbridge0 and awgmout0,
10.254.252.0/30, root UDP port 51899, LAN TCP port 8449. Ensure these are unused.

Removal:

    sh /data/awg-manager/uninstall.sh

Configurations/keys are retained. The associated native UniFi profile and policies
are not deleted. Persistence across UniFi OS upgrades and a fresh-device install
have not been tested. Service restart, config replacement, failed-candidate rollback,
engine recovery, a full UDM reboot (confirmed by the user), and end-to-end traffic have been tested on the development UDM.

Sources included for the bundled tools:
- amneziawg-go b5928efb6ca19f0153958460c3d141f04abc5c2e
- amneziawg-tools ee0f0a9aa34ff0a0da4b3433b9512781cfe02843
Built natively on ARM64 using Go 1.27.1 and Debian GCC 10.
The archive contains no VPN configs, private keys, or manager credentials.
