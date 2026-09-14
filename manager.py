#!/usr/bin/env python3
"""Single-profile AWG manager for the UDM development bridge."""
import base64, hashlib, hmac, html, ipaddress, json, os, secrets, signal, socket, ssl, subprocess, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs, urlparse

ROOT=Path('/data/awg-manager'); NS='awgm'; OUT='awgmout0'; BR='awgbridge0'
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

STYLE='''body{font:16px system-ui;background:#0b111a;color:#e6eef8;margin:0}main{max-width:760px;margin:60px auto;padding:24px}h1{font-size:32px;margin-bottom:8px}.muted{color:#9aaec5}section{background:#141f2f;border:1px solid #29394e;border-radius:16px;padding:24px;margin:20px 0}button,a.button{background:#3797ff;color:#061222;border:0;border-radius:8px;padding:12px 18px;font-weight:650;cursor:pointer;text-decoration:none;display:inline-block}input{display:block;margin:16px 0;padding:12px;max-width:95%;color:inherit;background:#0c1522;border:1px solid #40546d;border-radius:8px}small{display:block;line-height:1.6}.good{color:#64e5b0}.bad{color:#ffb276}a{color:#72b7ff}label{display:block;margin-top:18px}code{word-break:break-all}'''
AUTH=json.loads((ROOT/'auth.json').read_text())
def password_ok(p):return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(AUTH['salt']),200000).hex(),AUTH['hash'])
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,body,code=200,ctype='text/html; charset=utf-8',cookie=None,download=None,location=None,refresh=None):
        data=body if isinstance(body,bytes) else body.encode();self.send_response(code)
        self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        if location:self.send_header('Location',location)
        if refresh:self.send_header('Refresh',refresh)
        if cookie:self.send_header('Set-Cookie',cookie)
        if download:self.send_header('Content-Disposition','attachment; filename="'+download+'"')
        self.end_headers();self.wfile.write(data)
    def page(self,body,code=200,cookie=None):self.send('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AWG Manager</title><style>'+STYLE+'</style><main><h1>AWG Manager</h1><p class="muted">Dream Machine · AmneziaWG 3.1</p>'+body+'<footer class="muted">Developed by <a href="https://vk.com/greez" target="_blank" rel="noopener noreferrer">Roman Tselischev</a></footer></main></html>',code,cookie=cookie)
    def send_header_refresh_page(self,s):
        body='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Проверка AWG</title><style>'+STYLE+'</style><main><h1>AWG Manager</h1><section><h2>Проверяем подключение…</h2><p>'+html.escape(s['message'])+'</p><p class="muted">Результат появится автоматически. Обычно проверка занимает до 20 секунд; восстановление прежнего соединения может занять дольше.</p></section><footer>Developed by <a href="https://vk.com/greez" target="_blank" rel="noopener noreferrer">Roman Tselischev</a></footer></main></html>'
        return self.send(body,refresh='2; url=/')
    def redirect(self,cookie=None):
        return self.send('',303,cookie=cookie,location='/')
    def session(self):
        for part in self.headers.get('Cookie','').split(';'):
            if part.strip().startswith('awgm='):
                s=SESSIONS.get(part.strip()[5:])
                if s and s['expires']>time.time():return s
        return None
    def do_GET(self):
        sess=self.session()
        if not sess:
            return self.page('<section><h2>Вход</h2><form method="post" action="/login"><label>Пароль менеджера</label><input type="password" name="password" required autocomplete="current-password"><button>Войти</button></form></section>')
        path=urlparse(self.path).path
        if path=='/unifi.conf' and not (ROOT/'active.conf').exists():return self.page('Сначала загрузите и проверьте конфиг AWG. <a href="/">Назад</a>',409)
        if path=='/unifi.conf':return self.send((ROOT/'unifi-client.conf').read_bytes(),ctype='application/octet-stream',download='UniFi-AWG-Bridge.conf')
        if path=='/status':return self.send(json.dumps(STATE),ctype='application/json')
        if path!='/':return self.page('Страница не найдена',404)
        s=STATE.copy();good=s['phase']=='active';csrf=html.escape(sess['csrf'])
        if JOB.locked():
            self.send_header_refresh_page(s)
            return
        configured=(ROOT/'active.conf').exists()
        if not configured:
            return self.page('<section><h2>Настройка VPN</h2><p>'+html.escape(s['message'])+'</p><form action="/upload" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="'+csrf+'"><label>Конфиг AmneziaWG (.conf)</label><input type="file" name="config" accept=".conf" required><button>Загрузить и проверить</button></form><p>После успешной проверки здесь появится конфиг для импорта в UniFi VPN Client.</p></section>')
        self.page('<section><h2 class="'+('good' if good else 'bad')+'">'+('Подключён' if good else 'Проверка / нет соединения')+'</h2><p>'+html.escape(s['message'])+'</p><p>Внешний IP: <code>'+html.escape(s['ip'] or '—')+'</code></p><a href="/">Обновить статус</a></section><section><h2>Заменить конфиг AWG</h2><p>Профиль UniFi и его политики сохранятся. При неудачном подключении вернётся прежний конфиг.</p><form action="/upload" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="'+csrf+'"><input type="file" name="config" accept=".conf" required><button>Загрузить и проверить</button></form><small class="muted">Во время проверки возможен краткий перерыв. Эта версия обслуживает один профиль и IPv4.</small></section><section><h2>Профиль для UniFi</h2><p>Импортируйте этот файл один раз в VPN Client. Для замены AWG используйте форму выше.</p><a class="button" href="/unifi.conf">Скачать конфиг UniFi</a><p class="muted">DNS в политиках настраивается отдельно. Поле DNS из AWG-файла не меняет настройки вашей сети.</p></section>')
    def do_POST(self):
        if self.headers.get('Origin') and self.headers['Origin']!='https://'+self.headers.get('Host',''):return self.page('Запрос отклонён',403)
        try:n=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.page('Неверный запрос',400)
        if n<=0 or n>100000:return self.page('Неверный размер запроса',413)
        data=self.rfile.read(n);path=urlparse(self.path).path
        if path=='/login':
            now=time.time();ip=self.client_address[0];recent=[t for t in ATTEMPTS.get(ip,[]) if now-t<60]
            if len(recent)>=5:return self.page('Подождите минуту перед следующей попыткой.',429)
            p=parse_qs(data.decode()).get('password',[''])[0]
            if not password_ok(p):ATTEMPTS[ip]=recent+[now];return self.page('Неверный пароль. <a href="/">Повторить</a>',403)
            token=secrets.token_urlsafe(32);SESSIONS[token]={'expires':now+3600,'csrf':secrets.token_urlsafe(24)}
            return self.redirect(cookie='awgm='+token+'; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600')
        sess=self.session()
        if not sess:return self.page('Войдите в менеджер',401)
        if path!='/upload':return self.page('Страница не найдена',404)
        if LOCK.locked():return self.page('Дождитесь завершения текущей проверки.',409)
        try:
            msg=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers.get('Content-Type','')+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+data)
            fields={}
            for part in msg.iter_parts():fields[part.get_param('name',header='content-disposition')]=part.get_payload(decode=True)
            if not hmac.compare_digest(fields.get('csrf',b'').decode(),sess['csrf']):return self.page('Запрос отклонён',403)
            text=fields['config'].decode('utf-8-sig');parse(text)
        except ValueError as e:return self.page(html.escape(str(e))+' <a href="/">Назад</a>',400)
        except Exception:return self.page('Не удалось прочитать файл конфигурации.',400)
        if not JOB.acquire(False):return self.page('Дождитесь завершения текущей проверки.',409)
        state(phase='testing',message='Новый конфиг принят. Проверка подключения.')
        def task():
            try:activate(text)
            finally:JOB.release()
        threading.Thread(target=task,daemon=True).start()
        self.redirect()

if __name__=='__main__':
    os.umask(0o077)
    server=ThreadingHTTPServer((BIND,PORT),Handler)
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(ROOT/'cert.pem',ROOT/'tls.key');server.socket=ctx.wrap_socket(server.socket,server_side=True)
    def end(*_):STOP.set();bridge(False);stop_engine();os._exit(0)
    signal.signal(signal.SIGTERM,end);signal.signal(signal.SIGINT,end)
    threading.Thread(target=monitor,daemon=True).start()
    server.serve_forever()
