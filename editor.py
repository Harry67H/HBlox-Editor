# editor.py
from flask import Flask, render_template_string, request, send_file
import json, io

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>HBlock — All-in-One Game Editor</title>
  <style>
    :root { --bg:#222; --panel:#333; --white:#fff; }
    html,body { height:100%; margin:0; background:var(--bg); color:var(--white); font-family:Inter, Arial, sans-serif; }
    #topbar { display:flex; gap:8px; padding:10px; align-items:center; background:var(--panel); flex-wrap:wrap; }
    button, input[type="range"], input[type="color"] { cursor:pointer; }
    button { background:#555; color:white; border:0; padding:8px 10px; border-radius:8px; }
    #canvasWrap { display:flex; justify-content:center; padding:12px; }
    canvas { background:white; border:2px solid #000; touch-action: none; }
    .menu { position:absolute; background:white; color:black; padding:10px; border-radius:10px; box-shadow:0 6px 24px rgba(0,0,0,0.5); display:none; z-index:50; min-width:240px; }
    .menu h3 { margin:0 0 8px 0; font-size:16px; }
    .menu label { display:block; margin:6px 0; font-size:13px; }
    .small { padding:6px 8px; font-size:13px; }
    #windowSlider { width:200px; }
    #inventoryButton { background:#4a90e2; }
    #mobileTapButton { position:fixed; right:18px; bottom:18px; padding:12px 16px; border-radius:12px; background:#1abc9c; color:#fff; border:0; z-index:60; display:none; }
    #inventoryPreview { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
    .invItem { background:#eee; color:#000; padding:6px; border-radius:6px; display:flex; gap:6px; align-items:center; }
    .tiny { font-size:12px; padding:4px 6px; }
    /* small helper UI */
    #status { margin-left:8px; color:#ddd; font-size:13px; }
  </style>
</head>
<body>
  <div id="topbar">
    <button onclick="addShape()">Add Shape</button>
    <button onclick="addText()">Add Text</button>
    <button onclick="openPlayerMenu()">Player Settings</button>
    <button onclick="openEventMenu()">Events</button>
    <button id="inventoryButton" onclick="openInventoryMenu()">Inventory</button>
    <button onclick="saveFile()">Save .Hblock</button>
    <button onclick="openFile()">Open .Hblock</button>
    <label style="display:flex;align-items:center;gap:8px;">
      Window:
      <input id="windowSlider" type="range" min="0" max="0" value="0" oninput="switchWindow(this.value)">
    </label>
    <span id="status">Window 0</span>
  </div>

  <div id="canvasWrap">
    <div style="position:relative;">
      <canvas id="gameCanvas" width="900" height="600"></canvas>

      <!-- Menus -->
      <div id="shapeMenu" class="menu"></div>
      <div id="textMenu" class="menu"></div>
      <div id="playerMenu" class="menu"></div>
      <div id="eventMenu" class="menu"></div>
      <div id="inventoryMenu" class="menu"></div>
    </div>
  </div>

  <!-- Mobile equip button (appears when a mobile-tap binding is assigned) -->
  <button id="mobileTapButton" ontouchstart="mobileTapEquip(event)" onclick="mobileTapEquip(event)">Tap</button>

  <input type="file" id="fileInput" accept=".Hblock" style="display:none" />

<script>
/*
HBlock Editor — single-file JS editor inside Flask template.
Data model:
- windows: array of arrays. each window is list of objects.
- object types: shape, text, eventZone
- inventory: array of inventory items (shapes)
- playerSettings: { count, speed, controls } controls mapping action->keyString
- events assigned to eventZones: zone.event = { type: "addShape"|"newWindow"|"inventoryEquip"|"addText"|"removeText", params: {...} }
- save: serializes windows, inventory, playerSettings
*/

/////////////////////////
// editor state
/////////////////////////
let windows = [[]];          // array of windows (each window is array of objects)
let currentWindow = 0;
let inventory = [];          // stored shapes (objects)
let playerSettings = { count:0, speed:5, controls: {} }; // controls: action->key
let equipped = null;         // when equipping an inventory item (preview)
let mobileTapBindings = {};  // inventoryIndex -> true (show mobile tap button)
let mobileTapAssignedIndex = null; // which inventory item currently assigned to mobile button
let eventZones = [];         // we also store zones inside windows but keep helper array if needed

const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const shapeMenu = document.getElementById('shapeMenu');
const textMenu = document.getElementById('textMenu');
const playerMenu = document.getElementById('playerMenu');
const eventMenu = document.getElementById('eventMenu');
const inventoryMenu = document.getElementById('inventoryMenu');
const fileInput = document.getElementById('fileInput');
const windowSlider = document.getElementById('windowSlider');
const statusSpan = document.getElementById('status');
const mobileTapButton = document.getElementById('mobileTapButton');

let dragTarget = null;
let dragOffset = {x:0,y:0};
let dragStart = {x:0,y:0};
let dragging = false;
let maybeClickTarget = null;
let clickMoved = false;
const clickThreshold = 6;

let zoneEditing = null; // eventZone being edited/resized
let zoneResizeHandle = null;

// small helpers
function objects() { return windows[currentWindow]; }
function clamp(v,a,b) { return Math.max(a, Math.min(b, v)); }

/////////////////////////
// Drawing
/////////////////////////
function drawAll(){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  // background white is already canvas background
  let objs = objects();
  for(let obj of objs){
    if(obj.type === 'shape'){
      if(obj.image){
        let img = new Image();
        img.src = obj.image;
        // draw once loaded (simple approach)
        img.onload = () => { ctx.drawImage(img, obj.x, obj.y, obj.size, obj.size); }
        // draw placeholder rect while loading
        ctx.fillStyle = obj.color || 'blue';
        ctx.fillRect(obj.x, obj.y, obj.size, obj.size);
      } else {
        ctx.fillStyle = obj.color || 'blue';
        if(obj.shape === 'square') ctx.fillRect(obj.x, obj.y, obj.size, obj.size);
        else if(obj.shape === 'circle'){
          ctx.beginPath();
          ctx.arc(obj.x + obj.size/2, obj.y + obj.size/2, obj.size/2, 0, Math.PI*2);
          ctx.fill();
        } else if(obj.shape === 'triangle'){
          ctx.beginPath();
          ctx.moveTo(obj.x + obj.size/2, obj.y);
          ctx.lineTo(obj.x, obj.y + obj.size);
          ctx.lineTo(obj.x + obj.size, obj.y + obj.size);
          ctx.closePath();
          ctx.fill();
        } else if(obj.shape === 'hexagon'){
          ctx.beginPath();
          let s = obj.size/2;
          let cx = obj.x + s, cy = obj.y + s;
          for(let i=0;i<6;i++){
            let a = Math.PI/3*i;
            let px = cx + s*Math.cos(a), py = cy + s*Math.sin(a);
            if(i===0) ctx.moveTo(px,py); else ctx.lineTo(px,py);
          }
          ctx.closePath();
          ctx.fill();
        }
      }

      // overlay indicators for player/collide/kill
      if(obj.player){
        ctx.strokeStyle = '#FF0000';
        ctx.lineWidth = 2;
        ctx.strokeRect(obj.x-2, obj.y-2, obj.size+4, obj.size+4);
      } else if(obj.collide){
        ctx.strokeStyle = '#0000FF';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(obj.x-2, obj.y-2, obj.size+4, obj.size+4);
      }
      if(obj.kill){
        ctx.beginPath();
        ctx.moveTo(obj.x, obj.y);
        ctx.lineTo(obj.x+obj.size, obj.y+obj.size);
        ctx.moveTo(obj.x+obj.size, obj.y);
        ctx.lineTo(obj.x, obj.y+obj.size);
        ctx.strokeStyle = '#000';
        ctx.stroke();
      }

    } else if(obj.type === 'text'){
      ctx.fillStyle = obj.color || '#000';
      ctx.font = (obj.size || 24) + 'px Arial';
      ctx.fillText(obj.text || '', obj.x, obj.y);
    } else if(obj.type === 'eventZone'){
      if(obj.visible){
        ctx.strokeStyle = 'rgba(255,0,0,0.9)';
        ctx.lineWidth = 2;
        ctx.strokeRect(obj.x, obj.y, obj.w, obj.h);
        // corner handles
        ctx.fillStyle = 'rgba(255,0,0,0.9)';
        let hs = 8;
        [[obj.x,obj.y],[obj.x+obj.w,obj.y],[obj.x,obj.y+obj.h],[obj.x+obj.w,obj.y+obj.h]].forEach(p=>{
          ctx.fillRect(p[0]-hs/2, p[1]-hs/2, hs, hs);
        });
      }
    }
  }

  // draw equipped preview following mouse if exists
  if(equipped && equipped.previewPos){
    ctx.save();
    ctx.globalAlpha = 0.8;
    let eq = equipped.item;
    if(eq.type === 'shape'){
      ctx.fillStyle = eq.color || 'blue';
      if(eq.image){
        let img = new Image(); img.src = eq.image;
        img.onload = ()=>{ ctx.drawImage(img, equipped.previewPos.x, equipped.previewPos.y, eq.size, eq.size); }
        ctx.fillRect(equipped.previewPos.x, equipped.previewPos.y, eq.size, eq.size);
      } else {
        if(eq.shape === 'square') ctx.fillRect(equipped.previewPos.x, equipped.previewPos.y, eq.size, eq.size);
        else if(eq.shape === 'circle'){
          ctx.beginPath();
          ctx.arc(equipped.previewPos.x + eq.size/2, equipped.previewPos.y + eq.size/2, eq.size/2, 0, Math.PI*2);
          ctx.fill();
        } else if(eq.shape === 'triangle'){
          ctx.beginPath();
          ctx.moveTo(equipped.previewPos.x + eq.size/2, equipped.previewPos.y);
          ctx.lineTo(equipped.previewPos.x, equipped.previewPos.y + eq.size);
          ctx.lineTo(equipped.previewPos.x + eq.size, equipped.previewPos.y + eq.size);
          ctx.closePath();
          ctx.fill();
        } else if(eq.shape === 'hexagon'){
          ctx.beginPath();
          let s = eq.size/2;
          let cx = equipped.previewPos.x + s, cy = equipped.previewPos.y + s;
          for(let i=0;i<6;i++){
            let a = Math.PI/3*i;
            let px = cx + s*Math.cos(a), py = cy + s*Math.sin(a);
            if(i===0) ctx.moveTo(px,py); else ctx.lineTo(px,py);
          }
          ctx.closePath();
          ctx.fill();
        }
      }
    }
    ctx.restore();
  }
}

/////////////////////////
// Utilities for hit testing
/////////////////////////
function findTopObjectAt(x,y){
  let objs = objects();
  for(let i=objs.length-1;i>=0;i--){
    let o = objs[i];
    if(o.type === 'shape'){
      if(x >= o.x && x <= o.x+o.size && y >= o.y && y <= o.y+o.size) return o;
    } else if(o.type === 'text'){
      // approximate bounding box width 200
      if(x >= o.x && x <= o.x+200 && y >= o.y - o.size && y <= o.y) return o;
    } else if(o.type === 'eventZone'){
      if(x >= o.x && x <= o.x+o.w && y >= o.y && y <= o.y+o.h) return o;
    }
  }
  return null;
}

/////////////////////////
// Mouse / touch events: drag vs click logic
/////////////////////////
canvas.addEventListener('pointerdown', (ev)=>{
  ev.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
  dragStart = {x,y};
  clickMoved = false;
  dragging = true;

  // if editing a zone, check handles
  let top = findTopObjectAt(x,y);
  if(top && top.type === 'eventZone' && top.visible){
    // check corner handles
    let hs = 10;
    let corners = [
      {name:'tl', x:top.x, y:top.y},
      {name:'tr', x:top.x+top.w, y:top.y},
      {name:'bl', x:top.x, y:top.y+top.h},
      {name:'br', x:top.x+top.w, y:top.y+top.h}
    ];
    for(let c of corners){
      if(Math.abs(x-c.x) <= hs && Math.abs(y-c.y) <= hs){
        zoneEditing = top;
        zoneResizeHandle = c.name;
        return;
      }
    }
    // else select zone for dragging
    if(top.type === 'eventZone'){
      zoneEditing = top;
      zoneResizeHandle = null;
      dragOffset.x = x - top.x;
      dragOffset.y = y - top.y;
      return;
    }
  }

  // otherwise select object for dragging
  if(top && (top.type === 'shape' || top.type === 'text')){
    dragTarget = top;
    dragOffset.x = x - dragTarget.x;
    dragOffset.y = y - dragTarget.y;
    maybeClickTarget = top;
  } else {
    dragTarget = null;
    maybeClickTarget = null;
  }
});

canvas.addEventListener('pointermove', (ev)=>{
  if(!dragging) return;
  const rect = canvas.getBoundingClientRect();
  const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
  if(zoneEditing){
    // resize or move zoneEditing
    if(zoneResizeHandle){
      // resize by handle name
      if(zoneResizeHandle === 'tl'){
        let newx = x, newy = y;
        let oldr = zoneEditing.x + zoneEditing.w, oldb = zoneEditing.y + zoneEditing.h;
        zoneEditing.x = Math.min(newx, oldr-10);
        zoneEditing.y = Math.min(newy, oldb-10);
        zoneEditing.w = oldr - zoneEditing.x;
        zoneEditing.h = oldb - zoneEditing.y;
      } else if(zoneResizeHandle === 'tr'){
        let oldl = zoneEditing.x, oldb = zoneEditing.y + zoneEditing.h;
        zoneEditing.y = Math.min(y, oldb-10);
        zoneEditing.w = Math.max(10, x - zoneEditing.x);
        zoneEditing.h = oldb - zoneEditing.y;
      } else if(zoneResizeHandle === 'bl'){
        let oldr = zoneEditing.x + zoneEditing.w, oldt = zoneEditing.y;
        zoneEditing.x = Math.min(x, oldr-10);
        zoneEditing.w = oldr - zoneEditing.x;
        zoneEditing.h = Math.max(10, y - zoneEditing.y);
      } else if(zoneResizeHandle === 'br'){
        zoneEditing.w = Math.max(10, x - zoneEditing.x);
        zoneEditing.h = Math.max(10, y - zoneEditing.y);
      }
      drawAll();
      clickMoved = true;
      return;
    } else {
      // dragging zone
      zoneEditing.x = x - dragOffset.x;
      zoneEditing.y = y - dragOffset.y;
      drawAll();
      clickMoved = true;
      return;
    }
  }

  if(dragTarget){
    // move object
    dragTarget.x = x - dragOffset.x;
    dragTarget.y = y - dragOffset.y;
    drawAll();
    clickMoved = true;
    return;
  }

  // if equipped preview, update preview pos
  if(equipped){
    equipped.previewPos = {x: x - (equipped.item.size||50)/2, y: y - (equipped.item.size||50)/2};
    drawAll();
  }
});

canvas.addEventListener('pointerup', (ev)=>{
  dragging = false;
  // if there was zone editing and we weren't moving significantly, maybe open zone menu on click
  if(zoneEditing){
    if(!clickMoved){
      openZoneMenu(zoneEditing);
    }
    zoneEditing = null;
    zoneResizeHandle = null;
    return;
  }

  if(dragTarget){
    // if mouse didn't move (a click) then treat as click: open menu
    if(!clickMoved && maybeClickTarget){
      if(maybeClickTarget.type === 'shape') openShapeMenu(maybeClickTarget);
      else if(maybeClickTarget.type === 'text') openTextMenu(maybeClickTarget);
    }
  } else {
    // if no object and equipped present and no big move, then place the equipped item
    const rect = canvas.getBoundingClientRect();
    const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
    if(equipped && !clickMoved){
      // place copy
      let copy = JSON.parse(JSON.stringify(equipped.item));
      copy.x = x - (copy.size||50)/2;
      copy.y = y - (copy.size||50)/2;
      objects().push(copy);
      // if the inventory item wanted to be removed on place, we could do that, but for now leave inventory untouched
      equipped = null;
      mobileTapButton.style.display = mobileTapAssignedIndex !== null ? 'inline-block' : 'none';
      drawAll();
    }
  }

  dragTarget = null;
  maybeClickTarget = null;
  clickMoved = false;
});

/////////////////////////
// Create / Add items
/////////////////////////
function addShape(){
  let obj = { type:'shape', x:120, y:120, size:80, color:'blue', shape:'square', image:null, player:false, collide:false, kill:false, speed:playerSettings.speed || 5, controls:{} };
  objects().push(obj);
  drawAll();
}

function addText(){
  let obj = { type:'text', x:200, y:200, text:'Hello world', color:'#000000', size:28 };
  objects().push(obj);
  drawAll();
}

/////////////////////////
// Menus: shape & text
/////////////////////////
function closeAllMenus(){
  [shapeMenu, textMenu, playerMenu, eventMenu, inventoryMenu].forEach(m => m.style.display = 'none');
}

function openShapeMenu(obj){
  closeAllMenus();
  shapeMenu.style.left = (canvas.getBoundingClientRect().left + 20) + 'px';
  shapeMenu.style.top = (canvas.getBoundingClientRect().top + 20) + 'px';
  shapeMenu.innerHTML = `
    <h3>Shape Options</h3>
    <label>Color <input id="shapeColor" type="color" value="${obj.color || '#0000ff'}"></label>
    <label>Shape
      <select id="shapeType">
        <option value="square">Square</option>
        <option value="circle">Circle</option>
        <option value="triangle">Triangle</option>
        <option value="hexagon">Hexagon</option>
      </select>
    </label>
    <label>Import Image <input id="shapeImage" type="file" accept="image/*"></label>
    <div style="display:flex;gap:6px;margin-top:8px;">
      <button class="small" id="makePlayerBtn">Make Player</button>
      <button class="small" id="makeCollideBtn">Make Collideable</button>
      <button class="small" id="makeKillBtn">Make Kill</button>
    </div>
    <label>Size <input id="shapeSize" type="range" min="20" max="300" value="${obj.size}"></label>
    <div style="display:flex;gap:6px;margin-top:8px;">
      <button onclick="deleteObject()" class="small">Delete</button>
      <button onclick="closeAllMenus()" class="small">Close</button>
    </div>
  `;
  // set select to current shape
  shapeMenu.querySelector('#shapeType').value = obj.shape || 'square';

  // attach events
  shapeMenu.querySelector('#shapeColor').oninput = (e)=>{ obj.color = e.target.value; drawAll(); }
  shapeMenu.querySelector('#shapeType').onchange = (e)=>{ obj.shape = e.target.value; obj.image = null; drawAll(); }
  shapeMenu.querySelector('#shapeSize').oninput = (e)=>{ obj.size = parseInt(e.target.value); drawAll(); }

  shapeMenu.querySelector('#shapeImage').onchange = (ev)=>{
    let f = ev.target.files[0];
    let r = new FileReader();
    r.onload = ()=>{ obj.image = r.result; drawAll(); }
    r.readAsDataURL(f);
  }

  shapeMenu.querySelector('#makePlayerBtn').onclick = ()=>{
    obj.player = true;
    obj.collide = false;
    obj.kill = false;
    drawAll();
  }
  shapeMenu.querySelector('#makeCollideBtn').onclick = ()=>{
    obj.collide = true;
    obj.player = false;
    drawAll();
  }
  shapeMenu.querySelector('#makeKillBtn').onclick = ()=>{
    obj.kill = true;
    obj.player = false;
    drawAll();
  }

  // show menu
  shapeMenu.style.display = 'block';
}

function openTextMenu(obj){
  closeAllMenus();
  textMenu.style.left = (canvas.getBoundingClientRect().left + 40) + 'px';
  textMenu.style.top = (canvas.getBoundingClientRect().top + 40) + 'px';
  textMenu.innerHTML = `
    <h3>Text Options</h3>
    <label>Content <input id="textContent" type="text" value="${escapeHtml(obj.text || '')}"></label>
    <label>Color <input id="textColor" type="color" value="${obj.color || '#000000'}"></label>
    <label>Size <input id="textSize" type="range" min="8" max="120" value="${obj.size || 24}"></label>
    <div style="display:flex;gap:6px;margin-top:8px;">
      <button onclick="deleteObject()" class="small">Delete</button>
      <button onclick="closeAllMenus()" class="small">Close</button>
    </div>
  `;

  textMenu.querySelector('#textContent').oninput = (e)=>{ obj.text = e.target.value; drawAll(); }
  textMenu.querySelector('#textColor').oninput = (e)=>{ obj.color = e.target.value; drawAll(); }
  textMenu.querySelector('#textSize').oninput = (e)=>{ obj.size = parseInt(e.target.value); drawAll(); }

  textMenu.style.display = 'block';
}

function deleteObject(){
  // find and remove current open-target by checking menus to see which object they reference (quick approach: capture last clicked object by maybeClickTarget)
  // Simpler: allow delete of top-most object under the last click position by re-using maybeClickTarget or search selected shapes in proximity of menu
  // For safety: remove last object in objects() that intersects with the menu left/top area
  // But to make it reliable: we will store a lastSelected global whenever opening menus.
  if(window.lastSelected){
    let arr = objects();
    let idx = arr.indexOf(window.lastSelected);
    if(idx !== -1) arr.splice(idx,1);
    window.lastSelected = null;
  }
  closeAllMenus();
  drawAll();
}

function escapeHtml(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

/////////////////////////
// Track lastSelected for delete operations
/////////////////////////
function openShapeMenu(obj){
  window.lastSelected = obj;
  closeAllMenus();
  shapeMenu.style.left = (canvas.getBoundingClientRect().left + 20) + 'px';
  shapeMenu.style.top = (canvas.getBoundingClientRect().top + 20) + 'px';
  shapeMenu.innerHTML = `
    <h3>Shape Options</h3>
    <label>Color <input id="shapeColor" type="color" value="${obj.color || '#0000ff'}"></label>
    <label>Shape
      <select id="shapeType">
        <option value="square">Square</option>
        <option value="circle">Circle</option>
        <option value="triangle">Triangle</option>
        <option value="hexagon">Hexagon</option>
      </select>
    </label>
    <label>Import Image <input id="shapeImage" type="file" accept="image/*"></label>
    <div style="display:flex;gap:6px;margin-top:8px;">
      <button class="small" id="makePlayerBtn">${obj.player? 'Player ✓' : 'Make Player'}</button>
      <button class="small" id="makeCollideBtn">${obj.collide? 'Collide ✓' : 'Make Collideable'}</button>
      <button class="small" id="makeKillBtn">${obj.kill? 'Kill ✓' : 'Make Kill'}</button>
    </div>
    <label>Size <input id="shapeSize" type="range" min="20" max="300" value="${obj.size}"></label>
    <div style="display:flex;gap:6px;margin-top:8px;">
      <button onclick="deleteObject()" class="small">Delete</button>
      <button onclick="closeAllMenus()" class="small">Close</button>
    </div>
  `;
  shapeMenu.querySelector('#shapeType').value = obj.shape || 'square';
  shapeMenu.querySelector('#shapeColor').oninput = (e)=>{ obj.color = e.target.value; drawAll(); }
  shapeMenu.querySelector('#shapeType').onchange = (e)=>{ obj.shape = e.target.value; obj.image = null; drawAll(); }
  shapeMenu.querySelector('#shapeSize').oninput = (e)=>{ obj.size = parseInt(e.target.value); drawAll(); }
  shapeMenu.querySelector('#shapeImage').onchange = (ev)=>{
    let f = ev.target.files[0];
    let r = new FileReader();
    r.onload = ()=>{ obj.image = r.result; drawAll(); }
    r.readAsDataURL(f);
  }
  shapeMenu.querySelector('#makePlayerBtn').onclick = ()=>{
    obj.player = !obj.player;
    if(obj.player){ obj.collide = false; obj.kill = false; }
    openShapeMenu(obj); // refresh
  }
  shapeMenu.querySelector('#makeCollideBtn').onclick = ()=>{
    obj.collide = !obj.collide;
    if(obj.collide) obj.player = false;
    openShapeMenu(obj);
  }
  shapeMenu.querySelector('#makeKillBtn').onclick = ()=>{
    obj.kill = !obj.kill;
    if(obj.kill) obj.player = false;
    openShapeMenu(obj);
  }
  shapeMenu.style.display = 'block';
}

function openTextMenu(obj){
  window.lastSelected = obj;
  closeAllMenus();
  textMenu.style.left = (canvas.getBoundingClientRect().left + 40) + 'px';
  textMenu.style.top = (canvas.getBoundingClientRect().top + 40) + 'px';
  textMenu.innerHTML = `
    <h3>Text Options</h3>
    <label>Content <input id="textContent" type="text" value="${escapeHtml(obj.text || '')}"></label>
    <label>Color <input id="textColor" type="color" value="${obj.color || '#000000'}"></label>
    <label>Size <input id="textSize" type="range" min="8" max="120" value="${obj.size || 24}"></label>
    <div style="display:flex;gap:6px;margin-top:8px;">
      <button onclick="deleteObject()" class="small">Delete</button>
      <button onclick="closeAllMenus()" class="small">Close</button>
    </div>
  `;
  textMenu.querySelector('#textContent').oninput = (e)=>{ obj.text = e.target.value; drawAll(); }
  textMenu.querySelector('#textColor').oninput = (e)=>{ obj.color = e.target.value; drawAll(); }
  textMenu.querySelector('#textSize').oninput = (e)=>{ obj.size = parseInt(e.target.value); drawAll(); }
  textMenu.style.display = 'block';
}

/////////////////////////
// Player settings menu
/////////////////////////
function openPlayerMenu(){
  closeAllMenus();
  playerMenu.style.left = (canvas.getBoundingClientRect().left + 60) + 'px';
  playerMenu.style.top = (canvas.getBoundingClientRect().top + 60) + 'px';
  playerMenu.innerHTML = `
    <h3>Player Settings</h3>
    <label>How many players? <input id="playerCount" type="number" min="1" max="10" value="${playerSettings.count || 0}"></label>
    <label>Default player speed <input id="playerSpeed" type="number" value="${playerSettings.speed || 5}"></label>
    <div style="margin-top:6px;">Assign Controls (press a key after clicking action):</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;">
      <button class="tiny" onclick="assignControl('jump')">Jump</button>
      <button class="tiny" onclick="assignControl('noGravityJump')">NoGravityJump</button>
      <button class="tiny" onclick="assignControl('right')">Right</button>
      <button class="tiny" onclick="assignControl('left')">Left</button>
      <button class="tiny" onclick="assignControl('up')">Up</button>
      <button class="tiny" onclick="assignControl('down')">Down</button>
    </div>
    <div style="display:flex;gap:8px;margin-top:8px;">
      <button onclick="applyPlayerSettings()" class="small">Apply</button>
      <button onclick="closeAllMenus()" class="small">Close</button>
    </div>
    <div style="margin-top:8px;font-size:12px;color:#444">Current key bindings: <pre id="bindingsPre" style="display:inline-block;margin:0">${JSON.stringify(playerSettings.controls)}</pre></div>
  `;
  playerMenu.style.display = 'block';
}

function applyPlayerSettings(){
  const cnt = parseInt(playerMenu.querySelector('#playerCount').value) || 0;
  const spd = parseFloat(playerMenu.querySelector('#playerSpeed').value) || 5;
  playerSettings.count = clamp(cnt,1,10);
  playerSettings.speed = spd;
  // create that many player shapes if not present (simple approach: append new players)
  // first, remove existing player flags from shapes so duplicates aren't created automatically
  // We'll create N players placed at top-left spaced apart
  // Remove previous player shapes of the current window to avoid doubling
  // But user expects global number of players => create players in current window
  // For simplicity we will append players until count reached (per current window)
  let existingPlayers = objects().filter(o=>o.type==='shape' && o.player);
  if(existingPlayers.length < playerSettings.count){
    let toAdd = playerSettings.count - existingPlayers.length;
    for(let i=0;i<toAdd;i++){
      objects().push({type:'shape', x:20+80*i, y:20, size:60, color:'#ff4d4d', shape:'square', player:true, speed:playerSettings.speed, controls: {}});
    }
  } else if(existingPlayers.length > playerSettings.count){
    // turn extras into non-player shapes (or remove them). We'll simply set player=false on extras.
    let extras = existingPlayers.slice(playerSettings.count);
    for(let ex of extras) ex.player = false;
  }
  // apply speed to all players
  for(let o of objects()) if(o.player) o.speed = playerSettings.speed;
  closeAllMenus();
  drawAll();
}

function assignControl(action){
  closeAllMenus();
  playerMenu.style.display = 'block';
  playerMenu.querySelector('#bindingsPre').textContent = JSON.stringify(playerSettings.controls);
  alert("Press a key now to bind '"+action+"' (press Esc to cancel).");
  function handler(e){
    if(e.key === 'Escape'){ window.removeEventListener('keydown', handler); alert('Cancelled'); return; }
    playerSettings.controls[action] = e.key;
    window.removeEventListener('keydown', handler);
    playerMenu.querySelector('#bindingsPre').textContent = JSON.stringify(playerSettings.controls);
  }
  window.addEventListener('keydown', handler);
}

/////////////////////////
// Events: create zone, finalize (make invisible), assign event
/////////////////////////
function openEventMenu(){
  closeAllMenus();
  eventMenu.style.left = (canvas.getBoundingClientRect().left + 80) + 'px';
  eventMenu.style.top = (canvas.getBoundingClientRect().top + 80) + 'px';
  eventMenu.innerHTML = `
    <h3>Events</h3>
    <button onclick="createEventZone()" class="small">Select Event Activation (create zone)</button>
    <button onclick="toggleZonesVisible()" class="small">Show/Hide Zones</button>
    <button onclick="makeNewWindowFromMenu()" class="small">Make New Game Window</button>
    <button onclick="addShapeToInventoryFromMenu()" class="small">Add Selected Shape To Inventory</button>
    <div style="margin-top:8px;font-size:12px;color:#444">After creating a zone: drag to move, use corners to resize. Click zone to assign event. Finalize hides it (invisible).</div>
    <div style="display:flex;gap:8px;margin-top:8px;">
      <button onclick="closeAllMenus()" class="small">Close</button>
    </div>
  `;
  eventMenu.style.display = 'block';
}

function createEventZone(){
  // create an event zone object that is visible and editable
  let z = { type:'eventZone', x:250, y:200, w:160, h:120, visible:true, finalized:false, event: null };
  objects().push(z);
  drawAll();
  closeAllMenus();
  // zoneEditing will allow immediate resizing/moving by user because pointerdown logic handles it
}

function toggleZonesVisible(){
  for(let w of windows){
    for(let o of w) if(o.type === 'eventZone') o.visible = !o.visible;
  }
  drawAll();
}

function openZoneMenu(zone){
  closeAllMenus();
  shapeMenu.style.display = 'none';
  // reuse shapeMenu to show zone options for simplicity
  eventMenu.style.left = (canvas.getBoundingClientRect().left + 100) + 'px';
  eventMenu.style.top = (canvas.getBoundingClientRect().top + 100) + 'px';
  eventMenu.innerHTML = `
    <h3>Event Zone</h3>
    <label>Event:
      <select id="zoneEventType">
        <option value="">(none)</option>
        <option value="addShape">Add Shape</option>
        <option value="newWindow">Make New Window</option>
        <option value="addInventory">Add Shape To Inventory</option>
        <option value="addText">Add Text</option>
        <option value="removeText">Remove Text</option>
      </select>
    </label>
    <div id="zoneParams"></div>
    <div style="display:flex;gap:6px;margin-top:8px;">
      <button onclick="finalizeZone()" class="small">Finalize (make invisible)</button>
      <button onclick="deleteEventZone()" class="small">Delete Zone</button>
      <button onclick="closeAllMenus()" class="small">Close</button>
    </div>
  `;
  // set currently assigned event
  let sel = eventMenu.querySelector('#zoneEventType');
  sel.value = zone.event ? zone.event.type : '';
  sel.onchange = ()=>{ renderZoneParams(zone); }
  renderZoneParams(zone);
  eventMenu.style.display = 'block';
}

function renderZoneParams(zone){
  const paramsDiv = eventMenu.querySelector('#zoneParams');
  paramsDiv.innerHTML = '';
  const type = eventMenu.querySelector('#zoneEventType').value;
  if(type === 'addShape'){
    paramsDiv.innerHTML = `
      <label>Shape color <input id="zshapeColor" type="color" value="#00ff00"></label>
      <label>Shape size <input id="zshapeSize" type="number" value="50"></label>
      <label>How many to add? <input id="zshapeCount" type="number" value="1" min="1"></label>
      <button onclick="assignZoneAddShape()">Assign</button>
    `;
  } else if(type === 'newWindow'){
    paramsDiv.innerHTML = `<div style="font-size:13px">Creates a new game window and switches to it when event triggers.</div><button onclick="assignZoneNewWindow()">Assign</button>`;
  } else if(type === 'addInventory'){
    paramsDiv.innerHTML = `
      <label>Choose inventory item index <input id="zInvIdx" type="number" min="0" max="${Math.max(0,inventory.length-1)}" value="0"></label>
      <button onclick="assignZoneAddInventory()">Assign</button>
    `;
  } else if(type === 'addText'){
    paramsDiv.innerHTML = `
      <label>Text content <input id="zTextContent" type="text" value="Hello!"></label>
      <label>Color <input id="zTextColor" type="color" value="#000000"></label>
      <label>Size <input id="zTextSize" type="number" value="28"></label>
      <button onclick="assignZoneAddText()">Assign</button>
    `;
  } else if(type === 'removeText'){
    paramsDiv.innerHTML = `
      <label>Remove most recent text? (yes removes one)</label>
      <button onclick="assignZoneRemoveText()">Assign</button>
    `;
  } else {
    paramsDiv.innerHTML = `<div style="font-size:12px;color:#333">Choose an event to assign to this zone.</div>`;
    zone.event = null;
  }
}

function assignZoneAddShape(){
  let color = eventMenu.querySelector('#zshapeColor').value;
  let size = parseInt(eventMenu.querySelector('#zshapeSize').value) || 50;
  let count = parseInt(eventMenu.querySelector('#zshapeCount').value) || 1;
  window.lastZone.event = { type:'addShape', params:{ color, size, count } };
  alert('Zone assigned: addShape x'+count);
  closeAllMenus();
}

function assignZoneNewWindow(){
  window.lastZone.event = { type:'newWindow', params:{} };
  alert('Zone assigned: newWindow');
  closeAllMenus();
}

function assignZoneAddInventory(){
  let idx = parseInt(eventMenu.querySelector('#zInvIdx').value) || 0;
  if(!inventory[idx]) { alert('No inventory item at index '+idx); return; }
  window.lastZone.event = { type:'addInventory', params:{ index: idx } };
  alert('Zone assigned: add inventory item idx '+idx);
  closeAllMenus();
}

function assignZoneAddText(){
  let txt = eventMenu.querySelector('#zTextContent').value;
  let color = eventMenu.querySelector('#zTextColor').value;
  let size = parseInt(eventMenu.querySelector('#zTextSize').value) || 28;
  window.lastZone.event = { type:'addText', params:{ text:txt, color, size } };
  alert('Zone assigned: add text "'+txt+'"');
  closeAllMenus();
}

function assignZoneRemoveText(){
  window.lastZone.event = { type:'removeText', params:{} };
  alert('Zone assigned: remove text');
  closeAllMenus();
}

function finalizeZone(){
  // finalize by setting finalized true and visible false
  if(window.lastZone){
    window.lastZone.finalized = true;
    window.lastZone.visible = false;
    alert('Zone finalized (now invisible). You can still edit by using Events menu -> show zones -> click zone.');
    closeAllMenus();
    drawAll();
  }
}

function deleteEventZone(){
  if(window.lastZone){
    let arr = objects();
    let idx = arr.indexOf(window.lastZone);
    if(idx !== -1) arr.splice(idx,1);
    window.lastZone = null;
    closeAllMenus();
    drawAll();
  }
}

/////////////////////////
// Inventory
/////////////////////////
function openInventoryMenu(){
  closeAllMenus();
  inventoryMenu.style.left = (canvas.getBoundingClientRect().left + 120) + 'px';
  inventoryMenu.style.top = (canvas.getBoundingClientRect().top + 60) + 'px';
  let html = `<h3>Inventory</h3><div id="invList" style="max-height:240px;overflow:auto"></div>
  <div style="margin-top:8px;">
    <button onclick="captureSelectedToInventory()" class="small">Capture Selected Shape Into Inventory</button>
    <button onclick="closeAllMenus()" class="small">Close</button>
  </div>
  <div style="margin-top:6px;font-size:12px;color:#333">Assign a keyboard key or mobile tap to equip an inventory item.</div>`;
  inventoryMenu.innerHTML = html;
  const invList = inventoryMenu.querySelector('#invList');
  invList.innerHTML = '';
  inventory.forEach((it, idx)=>{
    const s = `<div class="invItem">
      <div style="width:40px;height:40px;display:flex;align-items:center;justify-content:center;background:#ddd;border-radius:4px;overflow:hidden;">
        ${it.image ? '<img src="'+it.image+'" style="width:100%;height:100%;object-fit:cover"/>' : renderMiniShape(it)}
      </div>
      <div style="display:flex;flex-direction:column;">
        <div>Idx ${idx}</div>
        <div style="display:flex;gap:6px;margin-top:4px;">
          <button onclick="editInventoryItem(${idx})" class="tiny">Edit</button>
          <button onclick="assignKeyToInventory(${idx})" class="tiny">Assign Key</button>
          <button onclick="assignTapToInventory(${idx})" class="tiny">Assign Tap</button>
          <button onclick="removeInventory(${idx})" class="tiny">Remove</button>
        </div>
        <div style="font-size:12px;color:#666;margin-top:4px">Key: ${it.keyBinding || '(none)'} Tap: ${it.tapBinding? 'yes' : 'no'}</div>
      </div>
    </div>`;
    invList.insertAdjacentHTML('beforeend', s);
  });
  inventoryMenu.style.display = 'block';
}

function renderMiniShape(it){
  // returns simple svg or char to represent shape
  if(it.shape === 'circle') return '<svg width="40" height="40"><circle cx="20" cy="20" r="12" fill="'+it.color+'"/></svg>';
  if(it.shape === 'triangle') return '<svg width="40" height="40"><polygon points="20,6 6,34 34,34" fill="'+it.color+'"/></svg>';
  if(it.shape === 'hexagon') return '<svg width="40" height="40"><polygon points="12,6 28,6 36,20 28,34 12,34 4,20" fill="'+it.color+'"/></svg>';
  return '<svg width="40" height="40"><rect x="8" y="8" width="24" height="24" fill="'+it.color+'"/></svg>';
}

function captureSelectedToInventory(){
  // capture lastSelected shape into inventory
  if(!window.lastSelected || window.lastSelected.type !== 'shape'){ alert('Select a shape first (click it)'); return; }
  let copy = JSON.parse(JSON.stringify(window.lastSelected));
  // trim runtime-only props
  delete copy.controls;
  inventory.push(copy);
  openInventoryMenu();
}

function editInventoryItem(idx){
  let it = inventory[idx];
  // open small edit popup inside inventoryMenu
  const html = `
    <div style="margin-top:8px;">
      <label>Color <input type="color" id="invColor" value="${it.color || '#00ff00'}"></label>
      <label>Size <input type="number" id="invSize" value="${it.size || 60}"></label>
      <label>Shape <select id="invShape">
        <option value="square">Square</option>
        <option value="circle">Circle</option>
        <option value="triangle">Triangle</option>
        <option value="hexagon">Hexagon</option>
      </select></label>
      <label>Import Image <input type="file" id="invImage" accept="image/*"></label>
      <div style="display:flex;gap:6px;margin-top:6px;">
        <button onclick="applyInventoryEdit(${idx})" class="small">Apply</button>
        <button onclick="openInventoryMenu()" class="small">Cancel</button>
      </div>
    </div>
  `;
  inventoryMenu.querySelector('#invList').insertAdjacentHTML('afterend', html);
  inventoryMenu.querySelector('#invShape').value = it.shape || 'square';
  inventoryMenu.querySelector('#invImage').onchange = (ev)=>{ let f = ev.target.files[0]; let r = new FileReader(); r.onload=()=>{ it.image = r.result; }; r.readAsDataURL(f); }
}

function applyInventoryEdit(idx){
  let it = inventory[idx];
  it.color = inventoryMenu.querySelector('#invColor').value;
  it.size = parseInt(inventoryMenu.querySelector('#invSize').value) || it.size;
  it.shape = inventoryMenu.querySelector('#invShape').value;
  openInventoryMenu();
}

function assignKeyToInventory(idx){
  alert('Press a key now to assign to inventory index '+idx+'. Press Escape to cancel.');
  function handler(e){
    if(e.key === 'Escape'){ window.removeEventListener('keydown', handler); alert('Cancelled'); return; }
    inventory[idx].keyBinding = e.key;
    window.removeEventListener('keydown', handler);
    openInventoryMenu();
  }
  window.addEventListener('keydown', handler);
}

function assignTapToInventory(idx){
  // assign the mobile tap to this index (only one tap button allowed)
  // toggle assignment
  if(mobileTapAssignedIndex === idx){
    mobileTapAssignedIndex = null;
    mobileTapButton.style.display = 'none';
    inventory[idx].tapBinding = false;
  } else {
    // clear previous
    if(mobileTapAssignedIndex !== null) inventory[mobileTapAssignedIndex].tapBinding = false;
    mobileTapAssignedIndex = idx;
    inventory[idx].tapBinding = true;
    mobileTapButton.style.display = 'inline-block';
    mobileTapButton.textContent = 'Tap (inv '+idx+')';
  }
  openInventoryMenu();
}

function removeInventory(idx){
  inventory.splice(idx,1);
  openInventoryMenu();
}

function mobileTapEquip(ev){
  ev.preventDefault();
  if(mobileTapAssignedIndex === null) return;
  let it = inventory[mobileTapAssignedIndex];
  if(!it) return;
  // equip it
  equipped = { item: JSON.parse(JSON.stringify(it)), previewPos: {x: canvas.width/2 - it.size/2, y: canvas.height/2 - it.size/2} };
  mobileTapButton.style.display = 'none';
  drawAll();
}

/////////////////////////
// Equip by key: when user presses a bound key assigned to inventory item, equip it
/////////////////////////
window.addEventListener('keydown', (e)=>{
  // check inventory key bindings
  for(let i=0;i<inventory.length;i++){
    if(inventory[i].keyBinding && e.key === inventory[i].keyBinding){
      equipped = { item: JSON.parse(JSON.stringify(inventory[i])), previewPos: {x: canvas.width/2 - inventory[i].size/2, y: canvas.height/2 - inventory[i].size/2} };
      drawAll();
      return;
    }
  }
  // other global shortcuts
  if(e.key === 's' && (e.ctrlKey || e.metaKey)){ e.preventDefault(); saveFile(); }
});

/////////////////////////
// Window management
/////////////////////////
function makeNewWindowFromMenu(){ windows.push([]); windowSlider.max = windows.length - 1; windowSlider.value = windows.length -1; switchWindow(windows.length-1); closeAllMenus(); }
function switchWindow(n){ currentWindow = parseInt(n); statusSpan.textContent = 'Window ' + currentWindow; drawAll(); }

/////////////////////////
// Add shape to inventory via Events menu: copies selected shape to inventory immediately
/////////////////////////
function addShapeToInventoryFromMenu(){
  if(!window.lastSelected || window.lastSelected.type !== 'shape'){ alert('Select a shape and click "Add Selected Shape To Inventory"'); return;}
  inventory.push(JSON.parse(JSON.stringify(window.lastSelected)));
  alert('Added to inventory (idx ' + (inventory.length-1) + ')');
  closeAllMenus();
}

/////////////////////////
// Save / Open .Hblock
/////////////////////////
function saveFile(){
  const payload = {
    windows: windows,
    inventory: inventory,
    playerSettings: playerSettings,
    mobileTapAssignedIndex: mobileTapAssignedIndex
  };
  fetch('/save', { method:'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) })
    .then(r=>r.blob())
    .then(blob=>{
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'project.Hblock';
      a.click();
    });
}

function openFile(){
  fileInput.click();
}
fileInput.addEventListener('change', (ev)=>{
  const f = ev.target.files[0];
  if(!f) return;
  const r = new FileReader();
  r.onload = (e)=>{
    try{
      const data = JSON.parse(e.target.result);
      windows = data.windows || [[]];
      inventory = data.inventory || [];
      playerSettings = data.playerSettings || {count:0, speed:5, controls:{}};
      mobileTapAssignedIndex = data.mobileTapAssignedIndex || null;
      windowSlider.max = windows.length - 1;
      windowSlider.value = 0;
      currentWindow = 0;
      statusSpan.textContent = 'Window ' + currentWindow;
      // mobile button
      if(mobileTapAssignedIndex !== null) { mobileTapButton.style.display = 'inline-block'; mobileTapButton.textContent = 'Tap (inv '+mobileTapAssignedIndex+')'; }
      drawAll();
      alert('Loaded .Hblock');
    }catch(err){
      alert('Failed to load file: ' + err);
    }
  }
  r.readAsText(f);
});

/////////////////////////
// Zone event trigger preview (simulate when clicking an invisible zone via a debug viewer)
// We'll provide a simple "test trigger" tool: when events menu open, show zones visible and clicking triggers their event logic (editor-simulated)
// For now, implement a simple function to trigger a zone manually (for debugging)
/////////////////////////
function triggerZone(zone){
  if(!zone.event) { alert('Zone has no event assigned'); return; }
  const ev = zone.event;
  if(ev.type === 'addShape'){
    const p = ev.params;
    for(let i=0;i<(p.count||1);i++){
      let s = { type:'shape', x: zone.x + 10 + i*10, y: zone.y + 10 + i*10, size: p.size || 50, color: p.color || '#00ff00', shape: 'square'};
      objects().push(s);
    }
    drawAll();
  } else if(ev.type === 'newWindow'){
    windows.push([]);
    windowSlider.max = windows.length-1;
    switchWindow(windows.length-1);
    drawAll();
  } else if(ev.type === 'addInventory'){
    const idx = ev.params.index;
    if(inventory[idx]) inventory.push(JSON.parse(JSON.stringify(inventory[idx])));
    drawAll();
  } else if(ev.type === 'addText'){
    const p = ev.params;
    objects().push({ type:'text', x: zone.x + 10, y: zone.y + 30, text: p.text, color: p.color, size: p.size });
    drawAll();
  } else if(ev.type === 'removeText'){
    // remove last text in this window
    for(let i = objects().length-1; i>=0; i--){
      if(objects()[i].type === 'text'){ objects().splice(i,1); break; }
    }
    drawAll();
  }
}

/////////////////////////
// UI helpers: open zone editor when clicking a zone (we do this by setting window.lastZone before opening)
/////////////////////////
canvas.addEventListener('click', (ev)=>{
  // find top object — if it's an eventZone (even if invisible and finalized) we should detect if the user had toggled zones visible
  const rect = canvas.getBoundingClientRect();
  const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
  let top = findTopObjectAt(x,y);
  if(top && top.type === 'eventZone'){
    window.lastZone = top;
    openZoneMenu(top);
  }
});

/////////////////////////
// Startup
/////////////////////////
window.addEventListener('load', ()=>{
  // friendly quick-start: add a blue square under Add Shape button description
  // (not necessary but nice)
  windowSlider.max = 0;
  windowSlider.value = 0;
  statusSpan.textContent = 'Window ' + currentWindow;
  drawAll();
});

</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/save", methods=["POST"])
def save():
    data = request.get_json()
    # ensure JSON bytes
    buf = io.BytesIO()
    buf.write(json.dumps(data).encode('utf-8'))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="project.Hblock", mimetype="application/octet-stream")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
