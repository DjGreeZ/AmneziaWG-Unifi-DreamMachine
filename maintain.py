"""Restore this version-specific local patch after UniFi regenerates nginx routes."""
import hashlib,json,subprocess,re
from pathlib import Path
ROOT=Path('/data/awg-native')
from compatibility import check_system
try:
    check_system()
except (ValueError, OSError) as error:
    raise SystemExit(str(error))
manifest=json.loads((ROOT/'manifest.json').read_text())
for item in manifest:
    path=Path(item['target'])
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest not in item['allowed']:raise SystemExit('Unknown asset hash; patch left untouched: '+path.name)
for item in manifest:
    path=Path(item['target']);data=(ROOT/item['source']).read_bytes()
    if path.read_bytes()!=data:
        temp=path.with_suffix('.awg-tmp');temp.write_bytes(data);temp.chmod(0o644);temp.replace(path)
loader=ROOT/'cache-loader.js'
if loader.exists():
    versions={'/app-assets/network/react/js/'+Path(x['target']).name:hashlib.sha256((ROOT/x['source']).read_bytes()).hexdigest()[:16] for x in manifest if x['source'] in ('frontend.js','settings.js')}
    content=loader.read_text();updated_loader=re.sub(r'const versions=.*?;',lambda _:'const versions='+json.dumps(versions)+';',content,count=1)
    if updated_loader!=content:loader.write_text(updated_loader);loader.chmod(0o644)
p=Path('/data/unifi-core/config/http/shared-runnable-network.conf')
if not p.exists():raise SystemExit('UniFi nginx configuration not ready')
s=p.read_text()
route=(ROOT/'route.conf').read_text()
updated=re.sub(r'\n# AWG-NATIVE-BEGIN.*?# AWG-NATIVE-END\n',lambda _:route,s,flags=re.S) if '# AWG-NATIVE-BEGIN' in s else s+route
if updated!=s:
    p.write_text(updated)
    result=subprocess.run(['nginx','-t'],capture_output=True)
    if result.returncode:
        p.write_text(s);raise SystemExit('nginx validation failed; restored previous configuration')
    subprocess.run(['systemctl','reload','nginx'],check=True)
