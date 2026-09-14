"""Validate the installed build, preserve originals, and generate local UI patches."""
import hashlib,json,re,subprocess,sys
from pathlib import Path
root=Path('/data/awg-native'); package=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
firmware=Path('/usr/lib/version').read_text().strip()
if not re.match(r'UDM\.al324\.v5\.1\.33(?:\.|$)',firmware):
    raise SystemExit('Требуется UDM al324 / UniFi OS 5.1.33. Другие версии не проверены.')
v=subprocess.check_output(['dpkg-query','-W','-f=${Status}\t${Version}','unifi-native'],text=True).strip()
if v!='install ok installed\t10.6.101-35991-1':
    raise SystemExit('Требуется UniFi Network 10.6.101, сборка 35991-1.')
manifest=json.loads((package/'manifest.json').read_text())
for item in manifest:
    target=Path(item['target']);backup=root/'backup'/item['source']
    if sha(target) not in item['allowed']:raise SystemExit('Неизвестная версия файла: '+target.name)
    if backup.exists():
        if sha(backup)!=item['original']:raise SystemExit('Резервная копия не прошла проверку: '+backup.name)
    elif sha(target)!=item['original']:
        raise SystemExit('Для изменённого файла отсутствует исходная резервная копия: '+target.name)
if '--check' in sys.argv:sys.exit(0)
root.mkdir(mode=0o755,exist_ok=True);root.chmod(0o755)
(root/'backup').mkdir(mode=0o700,exist_ok=True);(root/'backup').chmod(0o700)
for item in manifest:
    backup=root/'backup'/item['source']
    if not backup.exists():backup.write_bytes(Path(item['target']).read_bytes());backup.chmod(0o600)
subprocess.run([sys.executable,str(package/'patch_ui.py'),str(root)],check=True)
for item in manifest:
    digest=sha(root/item['source'])
    if digest not in item['allowed']:item['allowed'].append(digest)
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
