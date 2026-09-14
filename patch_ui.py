from pathlib import Path
import sys
root=Path(sys.argv[1])
s=(root/'backup/frontend.js').read_text()
a=s.index('Le=({form:e,existingRecord:t})=>');b=s.index(',we=({form:e})',a)
new='''Le=({form:e,existingRecord:t})=>{const v=(0,l.FH)({control:e.control,name:"vpn_type"}),f=(0,l.FH)({control:e.control,name:"awg_native"}),aw=f??(t?.wireguard_client_configuration_filename==="amneziawg-native.conf"),selected=aw?"awg":v;return(0,s.jsx)(H.A,{waypoint:W.vpnClientTypeFieldWaypoint,label:"Type",children:(0,s.jsx)(be.A,{children:[{value:A.EF.WIREGUARD_CLIENT,label:"WireGuard"},{value:A.EF.OPENVPN_CLIENT,label:"OpenVPN"},{value:"awg",label:"AmneziaWG"}].map(x=>(0,s.jsxs)("label",{style:{display:"inline-flex",gap:6,alignItems:"center",cursor:"pointer"},children:[(0,s.jsx)("input",{type:"radio",name:"awg-native-type",checked:selected===x.value,disabled:!!t&&selected!==x.value,onChange:()=>{e.setValue("awg_native",x.value==="awg");e.setValue("vpn_type",x.value==="awg"?A.EF.WIREGUARD_CLIENT:x.value,{shouldDirty:true});if(x.value==="awg")e.setValue("setup_mode",p.hS.FILE)}}),x.label]},x.value))})})}'''
s=s[:a]+new+s[b:]
old='_e=ne.handleSubmit(async e=>{try{const n='
new='''_e=ne.handleSubmit(async e=>{try{if(ne.getValues("awg_native")??(t?.wireguard_client_configuration_filename==="amneziawg-native.conf")){const status=await fetch("/proxy/network/awg-native/status",{credentials:"same-origin"});if(!status.ok)throw new Error("AWG service unavailable");const response=await fetch("/proxy/network/awg-native/prepare",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRF-Token":status.headers.get("X-CSRF-Token")||""},body:JSON.stringify({config:e.wireguard_configuration_file.content,editing:!!t})});const result=await response.json();if(!response.ok){window.alert(result.error||"AWG connection failed");return}e.wireguard_configuration_file={name:"amneziawg-native.conf",content:result.config};e.setup_mode=p.hS.FILE;}const n='''
assert s.count(old)==1;s=s.replace(old,new)
(root/'frontend.js').write_text(s)
settings=(root/'backup/settings.js').read_text()
old='renderCell:({protocol:e,enabled:t})=>(0,n.jsx)(o.A,{color:t?"inherit":"disabled",children:(0,n.jsx)(l.sA,{id:e||"COMMON_FALLBACK"})})'
new='renderCell:({protocol:e,enabled:t,network:w})=>(0,n.jsx)(o.A,{color:t?"inherit":"disabled",children:w?.wireguard_client_configuration_filename==="amneziawg-native.conf"?"AmneziaWG":(0,n.jsx)(l.sA,{id:e||"COMMON_FALLBACK"})})'
assert settings.count(old)==1
(root/'settings.js').write_text(settings.replace(old,new))

portal=(root/"backup/portal-index.html").read_text()
assert portal.count("<head>")==1
(root/"portal-index.html").write_text(portal.replace("<head>", '<head><script src="/awg-native-cache.js" data-awg-native="cache"></script>',1))
