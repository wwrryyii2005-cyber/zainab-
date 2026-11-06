'use strict';
/* EyeSpeak AI — extras: sign out, voice, dwell mode, nurse alerts, PWA */
Object.assign(dict.en,{logout:'Sign out',install:'Install app',speakAloud:'Speak aloud',dwellMode:'Eye-dwell mode',dwellHint:'Hold the pointer on a card for 1.5 s to send it.',loggedOut:'Signed out safely. See you soon!',newAlert:'New patient request!',urgentAlert:'URGENT request received!'});
Object.assign(dict.ar,{logout:'تسجيل الخروج',install:'تثبيت التطبيق',speakAloud:'نطق صوتي',dwellMode:'وضع التثبيت بالعين',dwellHint:'ثبّت المؤشر على البطاقة 1.5 ثانية حتى ترسل.',loggedOut:'تم تسجيل الخروج بأمان. نشوفك على خير!',newAlert:'وصل طلب جديد من مريض!',urgentAlert:'وصل طلب عاجل!'});

/* ---- Sign out ---- */
$('logoutBtn').addEventListener('click',async()=>{
  try{await api('/api/logout',{method:'POST'})}catch{}
  token='';localStorage.removeItem('care_token');
  if('speechSynthesis' in window)speechSynthesis.cancel();
  $('loginPass').value='';$('authMessage').textContent='';
  document.body.classList.remove('dwell-on');
  setAuthView();toast(t('loggedOut'));
});

/* ---- Speak aloud (Web Speech API) ---- */
let speakOn=true;
function speak(text){
  if(!speakOn||!('speechSynthesis' in window))return;
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(text);
  u.lang=language==='ar'?'ar-SA':'en-US';u.rate=.95;
  speechSynthesis.speak(u);
}
$('speakToggle').addEventListener('click',e=>{speakOn=!speakOn;e.currentTarget.classList.toggle('on',speakOn);e.currentTarget.setAttribute('aria-pressed',speakOn)});
const _send=window.sendPatientRequest;
window.sendPatientRequest=async function(text){
  const c=choices.find(x=>x[3]===text);
  speak(c?t(c[1]):text);
  return _send(text);
};

/* ---- Dwell mode: hold pointer on a card to select (works with eye-trackers / head pointers) ---- */
let dwellTimer=null,dwellCard=null;
function clearDwell(){clearTimeout(dwellTimer);if(dwellCard)dwellCard.classList.remove('dwelling');dwellCard=null}
$('dwellToggle').addEventListener('click',e=>{
  const on=!document.body.classList.contains('dwell-on');
  document.body.classList.toggle('dwell-on',on);
  e.currentTarget.classList.toggle('on',on);e.currentTarget.setAttribute('aria-pressed',on);clearDwell();
});
$('requestGrid').addEventListener('pointerover',e=>{
  if(!document.body.classList.contains('dwell-on'))return;
  const card=e.target.closest('.request-card');if(!card||card===dwellCard)return;
  clearDwell();dwellCard=card;card.classList.add('dwelling');
  dwellTimer=setTimeout(()=>{const c=dwellCard;clearDwell();c&&c.click()},1500);
});
$('requestGrid').addEventListener('pointerleave',clearDwell);

/* ---- Nurse alerts: sound + toast when a new request arrives ---- */
let lastNew=null;
function beep(urgent){
  try{const a=new (window.AudioContext||window.webkitAudioContext)(),o=a.createOscillator(),g=a.createGain();
    o.type='sine';o.frequency.value=urgent?880:660;g.gain.setValueAtTime(.001,a.currentTime);
    g.gain.exponentialRampToValueAtTime(.25,a.currentTime+.03);g.gain.exponentialRampToValueAtTime(.001,a.currentTime+.45);
    o.connect(g).connect(a.destination);o.start();o.stop(a.currentTime+.5)}catch{}
}
new MutationObserver(()=>{
  const n=parseInt($('statNew').textContent)||0;
  if(lastNew!==null&&n>lastNew){const urgent=!!document.querySelector('#nurseRows tr.prio-Urgent .status-New, #nurseRows tr.prio-Urgent');beep(urgent);toast(t(urgent?'urgentAlert':'newAlert'))}
  lastNew=n;
}).observe($('statNew'),{childList:true});

/* ---- PWA: service worker + install button ---- */
if('serviceWorker' in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
let deferredInstall=null;
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstall=e;$('installBtn').classList.remove('hidden')});
$('installBtn').addEventListener('click',async()=>{if(!deferredInstall)return;deferredInstall.prompt();await deferredInstall.userChoice;deferredInstall=null;$('installBtn').classList.add('hidden')});

applyLanguage();
