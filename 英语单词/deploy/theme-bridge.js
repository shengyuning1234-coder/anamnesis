/* Obtain the mapped platform identity before reusing a browser's chat token. */
if(window.parent!==window) {
  fetch('/words/api/chat/session',{credentials:'same-origin',cache:'no-store'}).then(async response=>{
    if(!response.ok) { localStorage.removeItem('token');location.replace('/words/login');return; }
    const session=await response.json(),previous=localStorage.getItem('anamnesis-chat-user');
    const changed=previous!==session.user_id || localStorage.getItem('token')!==session.token;
    if(changed) {
      localStorage.setItem('token',session.token);localStorage.setItem('anamnesis-chat-user',session.user_id);
      location.reload();
    }
  }).catch(()=>{});
}
/* Only an allowlisted embedding parent may send a colour. This never
   posts settings back to the parent or changes OpenWebUI's persistent config. */
window.addEventListener('message',event=>{
  if(event.source!==window.parent || window.parent===window) return;
  const allowed=__PARENT_ORIGINS__;
  if(!allowed.includes(event.origin)) return;
  // The embedding application may use Referrer-Policy: no-referrer.
  // source===parent plus the explicit origin allowlist still authenticates it.
  if(document.referrer) {
    try { if(event.origin!==new URL(document.referrer).origin) return; } catch (_) { return; }
  }
  const data=event.data;
  if(data?.type!=='anamnesis-theme' || !/^#[0-9a-f]{6}$/i.test(data.accent)) return;
  let style=document.getElementById('anamnesis-accent');
  if(!style) { style=document.createElement('style');style.id='anamnesis-accent';document.head.append(style); }
  style.textContent=`:root{--anamnesis-accent:${data.accent};--color-brand-500:${data.accent};--color-brand-600:${data.accent}}a:focus-visible,button:focus-visible{outline-color:var(--anamnesis-accent)}[aria-selected="true"]{border-color:var(--anamnesis-accent)}`;
});
