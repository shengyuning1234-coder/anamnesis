// Exercise local palette extraction and asynchronous background changes without a CDN.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const properties=new Map(), images=[];let rgb=[210,30,20];
const root={style:{setProperty:(k,v)=>properties.set(k,v),removeProperty:k=>properties.delete(k),getPropertyValue:k=>properties.get(k)||''},dataset:{}};
const context=vm.createContext({console,Map,Image:class{constructor(){images.push(this)}},location:{origin:'http://localhost'},window:{addEventListener(){}},navigator:{onLine:true},localStorage:{setItem(){},removeItem(){}},appURL:p=>'/words'+p,document:{addEventListener(){},querySelector(){return null},documentElement:root,createElement:()=>({getContext:()=>({drawImage(){},getImageData:()=>({data:Array.from({length:64*64},()=>[...rgb,255]).flat()})})})}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/static/app.js'),'utf8'),context);
vm.runInContext("extractBgColors('/red.jpg')",context);images.at(-1).onload();
assert.equal(properties.get('--bg-mode'),'image');assert.notEqual(properties.get('--theme-p'),'91,74,224');assert.equal(root.dataset.backgroundTheme,'ready');
vm.runInContext("extractBgColors('/old.jpg');extractBgColors('/new.jpg')",context);
rgb=[10,80,180];images.at(-1).onload();const latest=properties.get('--theme-p');
rgb=[210,30,20];images.at(-2).onload();assert.equal(properties.get('--theme-p'),latest);
vm.runInContext("extractBgColors('/late.jpg');resetAccentColors()",context);images.at(-1).onload();
assert.equal(properties.get('--bg-mode'),'default');assert.equal(properties.has('--theme-p'),false);assert.equal(root.dataset.backgroundTheme,undefined);
// A single white color must still create a readable theme rather than retaining purple.
rgb=[255,255,255];vm.runInContext("extractBgColors('/white.jpg')",context);images.at(-1).onload();
const color=properties.get('--theme-p').split(',').map(Number),linear=color.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
assert.ok(1.05/(linear.reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0)+.05)>=4.5);
assert.equal(images.at(-1).src,'/words/white.jpg');
console.log('PASS: local extraction, solid images, white-label contrast, stale image cancellation, reset and URL prefix');
