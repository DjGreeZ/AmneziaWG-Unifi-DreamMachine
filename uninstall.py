"""Remove only this integration; never overwrite unrecognized system assets."""
import hashlib,json,re,shutil,subprocess,sys
from pathlib import Path
root=Path('/data/awg-native');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((root/'manifest.json').read_text())
restore=[]
for item in manifest:
    target=Path(item['target']);backup=root/'backup'/item['source']
    if not target.exists():continue
    digest=sha(target)
    if digest==item.get('original',sha(backup)):continue
    if digest not in item['allowed']:
        raise SystemExit('Неизвестный системный файл. Автоматическое удаление остановлено: '+target.name)
    if sha(backup)!=item.get('original',sha(backup)):raise SystemExit('Повреждена резервная копия: '+backup.name)
    restore.append((target,backup))
for unit in ['awg-native-maintain.timer','awg-native-maintain.service','awg-native.service']:
    subprocess.run(['systemctl','disable','--now',unit],check=False)
for target,backup in restore:
    temp=target.with_suffix('.awg-restore');temp.write_bytes(backup.read_bytes());temp.chmod(0o644);temp.replace(target)
p=Path('/data/unifi-core/config/http/shared-runnable-network.conf')
if p.exists():
    before=p.read_text();after=re.sub(r'\n# AWG-NATIVE-BEGIN.*?# AWG-NATIVE-END\n','\n',before,flags=re.S)
    p.write_text(after)
    if subprocess.run(['nginx','-t']).returncode:
        p.write_text(before);raise SystemExit('nginx не прошёл проверку. Конфигурация nginx восстановлена; файлы сохранены.')
    subprocess.run(['systemctl','reload','nginx'],check=True)
subprocess.run(['ip','netns','del','awgm'],capture_output=True)
for name in ['awg-native.service','awg-native-maintain.service','awg-native-maintain.timer','awg-native.service.d/persistence.conf']:
    (Path('/etc/systemd/system')/name).unlink(missing_ok=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
if '--purge' in sys.argv:
    shutil.rmtree(root);print('Интеграция, резервные копии, конфиги и ключи удалены.')
else:print('Интеграция отключена. Конфиги, ключи и резервные копии сохранены в /data/awg-native.')
print('Удалите связанный VPN-профиль и политики в UniFi, если они больше не нужны. Обновите страницу.')
