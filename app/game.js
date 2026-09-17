const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
let ws=null, myId=null, myTeam=null, state=null, mode="ai", sens=1, keys={}, firing=false, yaw=0, lastPointer=0;
const menu=$("#menu"), lobby=$("#lobby"), game=$("#game"), result=$("#result"), canvas=$("#view"), ctx=canvas.getContext("2d");
function show(x){[menu,lobby,game,result].forEach(e=>e.classList.add("hidden"));x.classList.remove("hidden")}
function resize(){canvas.width=innerWidth*devicePixelRatio;canvas.height=innerHeight*devicePixelRatio;ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0)} addEventListener("resize",resize);resize();

$$("[data-mode]").forEach(b=>b.onclick=()=>{mode=b.dataset.mode; $("#modeText").textContent=mode==="ai"?"AI전 — A팀 플레이어 + AI vs B팀 AI":"로컬 — 브라우저 6명이 같은 방에서 대전"; connect()});
$("#settingsBtn").onclick=()=>$("#settings").classList.toggle("hidden");
$("#sens").oninput=e=>sens=+e.target.value;
$("#back").onclick=()=>show(menu);
$("#ready").onclick=()=>sendCheats();

function connect(){
 show(lobby); ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");
 ws.onopen=()=>ws.send(JSON.stringify({type:"join",mode}));
 ws.onmessage=e=>{let m=JSON.parse(e.data);if(m.type==="joined"){myId=m.id;myTeam=m.team;state=m.state;renderLobby();show(game);start();}else if(m.type==="state"){state=m.state;updateHUD();if(state.phase==="finished")finish();}};
 ws.onclose=()=>{};
}
function renderLobby(){
 $("#modeText").textContent+=(myTeam?" | 배정 팀: "+myTeam:"");
 for(const t of ["A","B"]){const box=$("#team"+t);box.innerHTML="";(state.players||[]).filter(p=>p.team===t).forEach(p=>{let d=document.createElement("div");d.className="player "+(p.id===myId?"me":"");d.textContent=p.name+(p.ai?" [AI]":"");box.appendChild(d)})}
}
function send(o){if(ws&&ws.readyState===1)ws.send(JSON.stringify(o))}
function sendCheats(){
 const o={type:"cheats"};
 $$("[data-cheat]").forEach(x=>{
   if(x.tagName==="INPUT") o[x.dataset.cheat]=x.checked;
   else if(x.tagName==="BUTTON") o[x.dataset.cheat]=x.classList.contains("active");
 });
 send(o);
}
$$("[data-cheat]").forEach(x=>x.addEventListener("change",()=>{if(x.tagName==="BUTTON"){x.classList.toggle("active");}sendCheats()}));

addEventListener("keydown",e=>{keys[e.code]=1;if(e.code==="Space")firing=true});
addEventListener("keyup",e=>{keys[e.code]=0;if(e.code==="Space")firing=false});
canvas.addEventListener("mousedown",e=>{if(e.button===0)firing=true});
addEventListener("mouseup",()=>firing=false);
canvas.addEventListener("mousemove",e=>{if(document.pointerLockElement===canvas||firing)send({type:"input",turn:e.movementX*.004*sens})});
canvas.onclick=()=>canvas.requestPointerLock?.();

function inputLoop(){
 let f=(keys.KeyW?1:0),b=(keys.KeyS?1:0),l=(keys.KeyA?1:0),r=(keys.KeyD?1:0);
 send({type:"input",f,b,l,r,turn:0,fire:firing});requestAnimationFrame(inputLoop)
}inputLoop();

let stick={active:false,x:0,y:0};
$("#stick").addEventListener("pointerdown",e=>{stick.active=true;$("#stick").setPointerCapture(e.pointerId)});
$("#stick").addEventListener("pointermove",e=>{if(!stick.active)return;let q=$("#stick").getBoundingClientRect(),x=e.clientX-(q.left+q.width/2),y=e.clientY-(q.top+q.height/2),m=Math.min(45,Math.hypot(x,y)),a=Math.atan2(y,x);x=Math.cos(a)*m;y=Math.sin(a)*m;$("#stick i").style.transform=`translate(${x}px,${y}px)`;send({type:"input",f:clamp(-y/35,0,1),b:clamp(y/35,0,1),l:clamp(-x/35,0,1),r:clamp(x/35,0,1),turn:0,fire:firing})});
$("#stick").addEventListener("pointerup",()=>{stick.active=false;$("#stick i").style.transform="";send({type:"input",f:0,b:0,l:0,r:0})});
$("#look").addEventListener("pointermove",e=>{if(e.buttons){send({type:"input",turn:e.movementX*.01*sens})}});
$("#fire").onpointerdown=()=>firing=true;$("#fire").onpointerup=()=>firing=false;

function clamp(v,a,b){return Math.max(a,Math.min(b,v))}
function updateHUD(){
 if(!state)return;
 $("#round").textContent=`ROUND ${state.round}/5`;$("#score").textContent=`${state.scores.A} : ${state.scores.B}`;$("#timer").textContent=`${state.time}s`;
 let me=state.players.find(p=>p.id===myId);if(me){$("#hp").textContent=`HP ${me.hp}`;$("#cheats").textContent=Object.entries(me.cheats||{}).filter(x=>x[1]).map(x=>x[0].toUpperCase()).join("  ")||"CHEATS OFF";}
 $("#alive").textContent=`A ${state.players.filter(p=>p.team==="A"&&p.alive).length}  —  ${state.players.filter(p=>p.team==="B"&&p.alive).length} B`;
 $("#log").innerHTML=state.events.map(e=>e.text||"").join("<br>");
}
function finish(){
 show(result);let me=state.players.find(p=>p.id===myId),win=state.scores[myTeam]>state.scores[myTeam==="A"?"B":"A"];
 $("#resultTitle").textContent=win?"ROUND SERIES COMPLETE":"MATCH COMPLETE";
 $("#resultStats").innerHTML=`최종 스코어 <b>${state.scores.A}:${state.scores.B}</b><br>킬 ${me?.kills||0} / 데스 ${me?.deaths||0}`;
}
$("#again").onclick=()=>location.reload();$("#home").onclick=()=>location.reload();

function start(){requestAnimationFrame(draw)}
function draw(){
 if(game.classList.contains("hidden"))return;
 const w=innerWidth,h=innerHeight;ctx.clearRect(0,0,w,h);
 const me=state?.players.find(p=>p.id===myId); if(!me){requestAnimationFrame(draw);return}
 // pseudo-3D raycasting renderer: compact browser FPS with a 2D world map and vertical wall slices
 const fov=Math.PI/2.9, rays=Math.min(420,Math.floor(w/2)), colW=w/rays;
 for(let i=0;i<rays;i++){
   const a=me.a-fov/2+fov*(i/rays), d=cast(me.x,me.y,a), corr=d*Math.cos(a-me.a);
   const wallH=Math.min(h*2,h/(corr*.085+0.02));ctx.fillStyle=i%2?"#1c2632":"#202c3a";ctx.fillRect(i*colW,(h-wallH)/2,colW+1,wallH);
 }
 // floor/ceiling
 ctx.globalAlpha=.3;ctx.fillStyle="#000";ctx.fillRect(0,h/2,w,h/2);ctx.globalAlpha=1;
 // ESP labels projected
 const esp=me.cheats?.esp;
 for(const p of state.players){if(!p.alive||p.id===myId)continue;if(p.team===me.team||esp||p.visible){
   const dx=p.x-me.x,dy=p.y-me.y,d=Math.hypot(dx,dy),rel=(Math.atan2(dy,dx)-me.a+Math.PI*3)%(Math.PI*2)-Math.PI;
   if(Math.abs(rel)<fov/2&&d<28){let sx=w/2+Math.tan(rel)/(Math.tan(fov/2))*w/2;let sy=h/2;ctx.fillStyle=p.team===me.team?"#6cf":"#f55";ctx.fillText(`${p.name} ${p.hp}`,sx-25,sy-d*7);ctx.beginPath();ctx.arc(sx,sy-d*5,4,0,7);ctx.fill()}
 }}
 if(!me.alive){ctx.fillStyle="#fff";ctx.font="bold 32px Arial";ctx.fillText("KNOCKED OUT — SPECTATING",w/2-220,h/2+100)}
 requestAnimationFrame(draw)
}
function cast(x,y,a){
 let dx=Math.cos(a),dy=Math.sin(a),d=0;
 while(d<35){d+=.035;if(wallAt(x+dx*d,y+dy*d))break}return d
}
function wallAt(x,y){let ix=Math.floor(x),iy=Math.floor(y);return !stateMap?.[iy]?.[ix]} // state map supplied below
const stateMap=[
"11111111111111111111111111111111","10000000000000001000000000000001","10111101111111001011111101111101","10000101000001001010000101000001","10110101011101011010110101011001","10000100010100000010010100010001","11110111010111101111010111011101","10000000010000101000010000000001","10111111111110101011111111111101","10000000000010101010000000000001","10111101111010101010111101111101","10000101000010000010000001000001","10110101111111101111111101011001","10000100000000100000000100010001","10111111101110111110111011111001","10000000001000000000100000000001","10111111111111101111111111111101","10000000000000000000000000000001","10000000000000000000000000000001","11111111111111111111111111111111"].map(r=>[...r]);
