/* Local AWG patch: version only its two UniFi modules before they are loaded. */
(()=>{
  const versions={"/app-assets/network/react/js/94924.70c7742fc8b69f7ab986.js": "cc6899b9e5b38bfa", "/app-assets/network/react/js/settings.c9b2a0ee0544312b21d4.js": "7dad476ec39ea1db"};
  const versioned=value=>{
    try {
      const url=new URL(value,document.baseURI);
      if(url.origin===location.origin && versions[url.pathname]){
        url.searchParams.set('awg',versions[url.pathname]);
        return url.href;
      }
    } catch (_) {}
    return value;
  };
  const descriptor=Object.getOwnPropertyDescriptor(HTMLScriptElement.prototype,'src');
  if(descriptor?.set && descriptor.configurable){
    Object.defineProperty(HTMLScriptElement.prototype,'src',{
      ...descriptor,set(value){descriptor.set.call(this,versioned(value));}
    });
  }
  const setAttribute=HTMLScriptElement.prototype.setAttribute;
  HTMLScriptElement.prototype.setAttribute=function(name,value){
    return setAttribute.call(this,name,String(name).toLowerCase()==='src'?versioned(value):value);
  };
})();
