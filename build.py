"""Build the installer from this directory; bundled tools and licenses included."""
import hashlib,io,tarfile
from pathlib import Path
root=Path(__file__).resolve().parent;out=root/'dist';out.mkdir(exist_ok=True)
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as archive:
 for p in sorted(root.iterdir()):
  if p.name not in ('dist','__pycache__'):archive.add(p,arcname=p.name,filter=lambda i:None if '__pycache__' in i.name else i)
data=buf.getvalue();digest=hashlib.sha256(data).hexdigest()
script='''#!/bin/sh
set -eu
TMP=$(mktemp -d /tmp/awg-native-install.XXXXXX)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
LINE=$(awk '/^__AWG_PAYLOAD__$/ {print NR+1;exit}' "$0")
tail -n +"$LINE" "$0" > "$TMP/payload.tar.gz"
printf '%s  %s\\n' 'DIGEST' "$TMP/payload.tar.gz" | sha256sum -c - >/dev/null
tar -xzf "$TMP/payload.tar.gz" -C "$TMP"
if [ "${1-}" = --extract ]; then
 [ $# -eq 2 ] || exit 1
 mkdir -p "$2"
 tar -xzf "$TMP/payload.tar.gz" -C "$2"
 exit 0
fi
sh "$TMP/install.sh" "$@"
exit 0
__AWG_PAYLOAD__
'''.replace('DIGEST',digest)
p=out/'AmneziaWG-UniFi-v0.2.0.run';p.write_bytes(script.encode()+data);p.chmod(0o755)
(out/'AmneziaWG-UniFi-v0.2.0.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n')
(out/'AmneziaWG-UniFi-v0.2.0-source.tar.gz').write_bytes(data)
print('Built',p.name,p.stat().st_size,'bytes')
