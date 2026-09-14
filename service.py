#!/usr/bin/env python3
"""Single-profile AWG manager for the UDM development bridge."""
import base64, hashlib, hmac, html, ipaddress, json, os, secrets, signal, socket, ssl, subprocess, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs, urlparse

ROOT=Path('/data/awg-native'); NS='awgm'; OUT='awgmout0'; BR='awgbridge0'
GO=str(ROOT/'bin/amneziawg-go'); AWG=str(ROOT/'bin/awg'); WG='/usr/bin/wg'
BIND=os.environ.get('AWGM_BIND_ADDRESS','127.0.0.1'); PORT=int(os.environ.get('AWGM_PORT','8449'))
LOCK=threading.Lock(); JOB=threading.Lock(); STOP=threading.Event(); SESSIONS={}; ATTEMPTS={}
STATE={'phase':'starting','message':'Запуск менеджера','checked':0,'ip':'','last_handshake':0}
IFIELDS=set('Address DNS MTU PrivateKey ListenPort Jc Jmin Jmax S1 S2 S3 S4 H1 H2 H3 H4 I1 I2 I3 I4 I5 HeaderProtectionKey ContentPaddingAddition RekeyAfterTime RekeyTimeout RejectAfterTime KeepaliveTimeout MaxHandshakeAttempts RandomTrailers DisableCookies'.split())
PFIELDS=set('PublicKey PresharedKey AllowedIPs Endpoint PersistentKeepalive'.split())

def run(*args, input=None, timeout=15):
    p=subprocess.run(args,input=input,text=True,capture_output=True,timeout=timeout)
    if p.returncode: raise RuntimeError('Ошибка команды '+Path(args[0]).name)
    return p.stdout

def ns(*args,**kw): return run('ip','netns','exec',NS,*args,**kw)
def save(path,text):
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(text); tmp.chmod(0o600); os.replace(tmp,path)
def state(**kw): STATE.update(kw)
def parse(text):
    if len(text.encode())>65536: raise ValueError('Файл слишком большой')
    sections={}; current=None
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith(('#',';')):continue
        if line.startswith('['):
            if line not in ('[Interface]','[Peer]') or line in sections:raise ValueError('Нужны одна секция Interface и один Peer')
            current=line; sections[current]={};continue
        if current is None or '=' not in line:raise ValueError('Неверный формат конфигурации')
        k,v=map(str.strip,line.split('=',1)); allowed=IFIELDS if current=='[Interface]' else PFIELDS
        if k not in allowed:raise ValueError('Неподдерживаемый параметр: '+k[:40])
        if k in sections[current]:raise ValueError('Повторяющийся параметр: '+k)
        sections[current][k]=v
    i=sections.get('[Interface]',{}); p=sections.get('[Peer]',{})
    if not {'Address','PrivateKey'}<=i.keys() or not {'PublicKey','AllowedIPs','Endpoint'}<=p.keys():raise ValueError('Не хватает обязательных параметров')
    for obj,k in [(i,'PrivateKey'),(i,'HeaderProtectionKey'),(p,'PublicKey'),(p,'PresharedKey')]:
        if k in obj:
            try: valid=len(base64.b64decode(obj[k],validate=True))==32
            except Exception:valid=False
            if not valid:raise ValueError('Неверный формат ключа '+k)
    addresses=[ipaddress.ip_interface(a.strip()) for a in i['Address'].split(',')]
    v4=[a for a in addresses if a.version==4]
    if len(v4)!=1:raise ValueError('Для этой версии нужен один IPv4-адрес туннеля')
    if ipaddress.ip_address('10.254.252.1') in v4[0].network:raise ValueError('Адрес пересекается с локальным переходником')
    nets=[ipaddress.ip_network(a.strip(),strict=False) for a in p['AllowedIPs'].split(',')]
    if not any(ipaddress.ip_address('1.1.1.1') in n for n in nets if n.version==4):raise ValueError('Для проверки соединения AllowedIPs должен включать 1.1.1.1')
    host,sep,port=p['Endpoint'].rpartition(':')
    if not sep or not host or any(c.isspace() for c in host) or not port.isdigit() or not 1<=int(port)<=65535:raise ValueError('Неверный Endpoint')
    engine='[Interface]\n'+''.join(k+' = '+v+'\n' for k,v in i.items() if k not in ('Address','DNS','MTU'))+'[Peer]\n'+''.join(k+' = '+v+'\n' for k,v in p.items())
    return str(v4[0]),engine

def bridge(up):
    try:ns('ip','link','set',BR,'up' if up else 'down')
    except Exception:pass

def ensure_bridge():
    if NS not in [l.split()[0] for l in run('ip','netns','list').splitlines()]:run('ip','netns','add',NS)
    try:ns('ip','link','show',BR)
    except Exception:
        run('ip','link','add',BR,'type','wireguard')
        run(WG,'setconf',BR,str(ROOT/'bridge.conf'))
        run('ip','link','set',BR,'netns',NS)
    ns('ip','addr','replace','10.254.252.1/30','dev',BR)
    ns('ip','link','set',BR,'mtu','1280')
    ns('ip','link','set','lo','up')
    ns('sysctl','-qw','net.ipv4.ip_forward=1')
    ns('sysctl','-qw','net.ipv4.conf.all.rp_filter=0')
    try:ns('iptables','-t','nat','-C','POSTROUTING','-o',OUT,'-j','MASQUERADE')
    except Exception:ns('iptables','-t','nat','-A','POSTROUTING','-o',OUT,'-j','MASQUERADE')

def stop_engine():
    try:
        pid=int((ROOT/'engine.pid').read_text())
        if os.readlink('/proc/'+str(pid)+'/exe')==GO:
            os.kill(pid,signal.SIGTERM)
            for _ in range(30):
                if not Path('/proc/'+str(pid)).exists():break
                time.sleep(.1)
    except (FileNotFoundError,ProcessLookupError,ValueError):pass
    try:ns('ip','link','del',OUT)
    except Exception:pass

def start_engine(text):
    address,engine=parse(text); bridge(False);stop_engine();save(ROOT/'tunnel.conf',engine)
    with open(ROOT/'engine.log','w') as log:
        p=subprocess.Popen([GO,'-f',OUT],stdin=subprocess.DEVNULL,stdout=log,stderr=log)
    save(ROOT/'engine.pid',str(p.pid))
    for _ in range(40):
        if p.poll() is not None:raise RuntimeError('Движок AWG завершился при запуске')
        if Path('/var/run/amneziawg/'+OUT+'.sock').exists():break
        time.sleep(.1)
    run(AWG,'setconf',OUT,str(ROOT/'tunnel.conf'))
    run('ip','link','set',OUT,'netns',NS)
    ns('ip','addr','add',address,'dev',OUT)
    ns('ip','link','set',OUT,'mtu','1280','up')
    ns('sysctl','-qw','net.ipv4.conf.'+OUT+'.rp_filter=0')
    ns('ip','route','replace','default','dev',OUT)

def probe():
    out=ns('curl','-4','--connect-timeout','5','--max-time','8','--fail','--silent','https://1.1.1.1/cdn-cgi/trace',timeout=10)
    ip=next((l[3:] for l in out.splitlines() if l.startswith('ip=')),'')
    ipaddress.ip_address(ip)
    stamp=max([int(l.split()[1]) for l in run(AWG,'show',OUT,'latest-handshakes').splitlines()] or [0])
    if not stamp:raise RuntimeError('Нет handshake')
    return ip,stamp

def activate(text,replacing=True):
    with LOCK:
        old=(ROOT/'active.conf').read_text() if (ROOT/'active.conf').exists() else None;state(phase='testing',message='Проверка нового соединения',ip='')
        try:
            ensure_bridge();start_engine(text);ip,stamp=probe()
            if replacing and old is not None:save(ROOT/'previous.conf',old)
            save(ROOT/'active.conf',text);bridge(True)
            state(phase='active',message='VPN работает',ip=ip,last_handshake=stamp,checked=time.time())
        except Exception:
            if old is None:
                bridge(False);stop_engine()
                state(phase='unconfigured',message='Подключение не прошло проверку. Проверьте конфиг и загрузите его снова.',ip='',last_handshake=0,checked=time.time())
                return
            state(phase='restoring',message='Подключение не прошло проверку. Восстановление прежнего конфига.')
            try:
                start_engine(old);ip,stamp=probe();bridge(True)
                state(phase='active',message='Новый конфиг не подключился. Восстановлен прежний.',ip=ip,last_handshake=stamp,checked=time.time())
            except Exception:
                bridge(False);state(phase='error',message='VPN недоступен. Переходник остановлен; трафик через него не проходит.',ip='',checked=time.time())

def monitor():
    try:
        if (ROOT/'active.conf').exists():activate((ROOT/'active.conf').read_text(),False)
        else:state(phase='unconfigured',message='Загрузите первый конфиг AWG, чтобы подключить VPN.')
    except Exception:state(phase='error',message='Ошибка запуска переходника')
    failures=0
    while not STOP.wait(15):
        if not LOCK.acquire(False):continue
        try:
            if not (ROOT/'active.conf').exists():
                failures=0
                continue
            try:
                pid=int((ROOT/'engine.pid').read_text())
                alive=os.readlink('/proc/'+str(pid)+'/exe')==GO
            except (OSError,ValueError):alive=False
            if not alive:start_engine((ROOT/'active.conf').read_text())
            ip,stamp=probe();failures=0;bridge(True)
            state(phase='active',message=STATE['message'] if STATE['phase']=='active' else 'VPN работает',ip=ip,last_handshake=stamp,checked=time.time())
        except Exception:
            failures+=1
            state(phase='checking',message='Проверяется доступность AWG',ip='',checked=time.time())
            if failures>=2:
                bridge(False);state(phase='error',message='AWG недоступен. Передача через переходник заблокирована.',ip='',checked=time.time())
        finally:LOCK.release()

PREPARE_UNTIL=0

def native_enabled():
    clients=json.loads(run('ubios-udapi-client','-r','GET','/vpn/wireguard/clients'))
    if not isinstance(clients,list):raise ValueError('Invalid native client list')
    key=(ROOT/'client.key').read_text().strip()
    matches=[c for c in clients if c.get('privateKey')==key]
    return any(c.get('enabled') is True for c in matches), bool(matches)

def engine_alive():
    try:return os.readlink('/proc/'+str(int((ROOT/'engine.pid').read_text()))+'/exe')==GO
    except (OSError,ValueError):return False

def lifecycle_tick():
    if JOB.locked() or time.monotonic()<PREPARE_UNTIL:return
    enabled,present=native_enabled()
    with LOCK:
        if JOB.locked():return
        if not enabled:
            bridge(False)
            if engine_alive():stop_engine()
            state(phase='disabled' if present else 'unbound',message='Профиль отключён в UniFi' if present else 'Профиль отсутствует в UniFi',ip='',last_handshake=0)
            return
        if not (ROOT/'active.conf').exists():
            bridge(False);state(phase='unconfigured',message='Загрузите конфиг AWG');return
        ensure_bridge()
        if not engine_alive():start_engine((ROOT/'active.conf').read_text())
        ip,stamp=probe();bridge(True)
        state(phase='active',message='VPN работает',ip=ip,last_handshake=stamp,checked=time.time())

def native_monitor():
    failures=0
    while not STOP.is_set():
        try:lifecycle_tick();failures=0
        except Exception:
            failures+=1
            if failures>=2 and not JOB.locked():
                with LOCK:
                    bridge(False);state(phase='error',message='AWG или профиль UniFi недоступен',ip='')
        if STOP.wait(5):break
# The Unix socket is reachable only by root and nginx. Nginx authenticates the
# UniFi session and replaces the identity headers before forwarding requests.
import socketserver
class API(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,data,code=200):
        body=json.dumps(data).encode();self.send_response(code)
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def authorized(self):
        return bool(self.headers.get('X-UserId')) and self.headers.get('X-UserRole','').lower() in ('owner','super_admin','admin')
    def do_GET(self):
        if not self.authorized():return self.reply({'error':'Требуется администратор UniFi'},403)
        return self.reply({'phase':STATE['phase'],'message':STATE['message']})
    def do_POST(self):
        global PREPARE_UNTIL
        if not self.authorized():return self.reply({'error':'Требуется администратор UniFi'},403)
        expected=self.headers.get('X-Expected-Csrf-Token','');provided=self.headers.get('X-Provided-Csrf-Token','')
        if not expected or not hmac.compare_digest(expected,provided):return self.reply({'error':'Недействительный CSRF-токен'},403)
        if self.path!='/prepare':return self.reply({'error':'Not found'},404)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100000:raise ValueError('Неверный размер файла')
            data=json.loads(self.rfile.read(length));text=data['config'];parse(text)
            if not data.get('editing') and native_enabled()[1]:return self.reply({'error':'Пока поддерживается один AWG-профиль. Измените существующий.'},409)
            current=(ROOT/'unifi-client.conf').read_text()
            if text==current and (ROOT/'active.conf').exists():return self.reply({'config':current})
            if not JOB.acquire(False):return self.reply({'error':'Проверка уже выполняется'},409)
            try:
                PREPARE_UNTIL=time.monotonic()+60
                activate(text)
                if not (ROOT/'active.conf').exists() or (ROOT/'active.conf').read_text()!=text or STATE['phase']!='active':
                    return self.reply({'error':STATE['message']},400)
                return self.reply({'config':current})
            finally:JOB.release()
        except (ValueError,KeyError,TypeError):return self.reply({'error':'Неверный AWG-конфиг'},400)
        except Exception:return self.reply({'error':'Не удалось применить AWG-конфиг'},500)
class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
if __name__=='__main__':
    os.umask(0o077)
    sock=Path('/run/awg-native/api.sock');sock.unlink(missing_ok=True)
    server=Server(str(sock),API)
    import grp
    os.chown(sock,0,grp.getgrnam('nginx').gr_gid);os.chmod(sock,0o660)
    def end(*_):STOP.set();bridge(False);stop_engine();os._exit(0)
    signal.signal(signal.SIGTERM,end);signal.signal(signal.SIGINT,end)
    threading.Thread(target=native_monitor,daemon=True).start();server.serve_forever()
