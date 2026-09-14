"""Model-independent minimum UniFi versions; UI hashes are checked separately."""
import re
import subprocess
from pathlib import Path

MIN_OS = '5.1.33'
MIN_NETWORK = '10.6.101'

def release_version(value, firmware=False):
    # UniFi firmware may include a model/platform prefix, e.g. UDM.al324.v5.1.33.
    pattern = r'(?:^|\.)v?(\d+\.\d+\.\d+)(?=$|[.\-+~])' if firmware else r'^(?:\d+:)?(\d+\.\d+\.\d+)(?=$|[.\-+~])'
    match = re.search(pattern, value.strip())
    if not match:
        raise ValueError('Не удалось определить версию: ' + value[:100])
    return match.group(1)

def validate_versions(firmware, network):
    os_version = release_version(firmware, firmware=True)
    network_version = release_version(network)
    for label, version, minimum in [('UniFi OS', os_version, MIN_OS), ('UniFi Network', network_version, MIN_NETWORK)]:
        if tuple(map(int, version.split('.'))) < tuple(map(int, minimum.split('.'))):
            raise ValueError(f'Требуется {label} не ниже {minimum}; обнаружена {version}.')
    return os_version, network_version

def check_system():
    firmware = Path('/usr/lib/version').read_text().strip()
    for package in ('unifi-native', 'unifi'):
        result = subprocess.run(['dpkg-query', '-W', '-f=${Status}\t${Version}', package], text=True, capture_output=True)
        status, separator, version = result.stdout.strip().partition('\t')
        if result.returncode == 0 and separator and status == 'install ok installed' and version:
            return validate_versions(firmware, version)
    raise ValueError('Не найден установленный UniFi Network.')
