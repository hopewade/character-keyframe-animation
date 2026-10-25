/* Whole-frame keyframe animation player. Inputs set targets; clicks do not. */
(() => {
  'use strict';
  const clamp = (v,a,b) => Math.min(b,Math.max(a,v));
  const initialize = async (root,options={}) => {
    const manifest=options.sequence||JSON.parse(root.querySelector('[data-character-sequence]').textContent);
    const positions=manifest.positions,front=manifest.frontFrame;
    if(positions.length<2||!positions.every(Number.isFinite)||positions.some((p,i)=>i&&p<=positions[i-1]))
      throw new Error('Character positions must be strictly increasing.');
    if(!Number.isInteger(front)||front<0||front>=positions.length)throw new Error('Invalid neutral frame.');
    const neutral=positions[front],control=root.querySelector('[data-character-control]')||root;
    const holder=root.querySelector('[data-character-frames]')||root;
    const scene=options.interactionTarget||root.closest('[data-character-scene]')||root;
    const poster=holder.querySelector('[data-character-poster]');
    const images=positions.map((_,i)=>holder.querySelector(`[data-character-frame="${i}"]`));
    if(images.some(image=>!image))throw new Error('Character frame is missing.');
    const reduced=matchMedia('(prefers-reduced-motion: reduce)');
    const fine=matchMedia('(hover: hover) and (pointer: fine)');
    root.dataset.ready='false';root.dataset.motionState='loading';
    const fallback=()=>{images.forEach((image,i)=>{image.hidden=poster?true:i!==front;});if(poster)poster.hidden=false;root.classList.remove('character-ready');root.dataset.motionState='fallback';root.dataset.ready='false';};
    let decodeIndex=0;
    try{
      await images[front].decode();
      await Promise.all(Array.from({length:4},async()=>{
        while(decodeIndex<images.length){const image=images[decodeIndex++];await image.decode();if(!image.naturalWidth)throw new Error('Empty character frame.');}
      }));
    }catch(error){fallback();throw error;}
    const canvas=document.createElement('canvas');canvas.className='character-canvas';canvas.setAttribute('aria-hidden','true');
    const ctx=canvas.getContext('2d',{alpha:true});
    if(!ctx){fallback();return {dispose(){}};}
    holder.append(canvas);images.forEach(image=>{image.hidden=true;});if(poster)poster.hidden=true;root.classList.add('character-ready');
    const omega=Number(options.damping)||17;
    let value=neutral,velocity=0,target=neutral,lastFrame=-1,raf=0,lastTime=null,disposed=false;
    let pointer=null,visible=true;
    const cleanups=[];
    function listen(object,name,fn,opts){object.addEventListener(name,fn,opts);cleanups.push(()=>object.removeEventListener(name,fn,opts));}
    function moving(){return Math.abs(value-target)>0.00012||Math.abs(velocity)>0.002;}
    function paused(){return disposed||reduced.matches||document.hidden||!visible||Boolean(document.querySelector('dialog[open]'))||Boolean(scene.closest('[data-character-paused="true"]'));}
    function display(){
      let a=0,b=positions.length-1;
      while(a+1<b){const i=(a+b)>>1;if(positions[i]<=value)a=i;else b=i;}
      const index=Math.abs(positions[a]-value)<=Math.abs(positions[b]-value)?a:b;
      if(index!==lastFrame){ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(images[index],0,0,canvas.width,canvas.height);lastFrame=index;}
      root.dataset.position=value.toFixed(5);root.dataset.frame=String(index);
    }
    function stop(){if(raf)cancelAnimationFrame(raf);raf=0;lastTime=null;}
    function schedule(){root.dataset.motionState=paused()?'paused':moving()?'following':'idle';if(!paused()&&!raf&&moving())raf=requestAnimationFrame(tick);}
    function tick(time){
      raf=0;if(paused()){refresh();return;}
      const dt=lastTime===null?0:Math.min(.05,Math.max(0,(time-lastTime)/1000));lastTime=time;
      if(dt){const offset=value-target,c=velocity+omega*offset,decay=Math.exp(-omega*dt);value=clamp(target+(offset+c*dt)*decay,positions[0],positions.at(-1));velocity=(velocity-omega*c*dt)*decay;
        if(!moving()){value=target;velocity=0;}display();}
      if(!moving())lastTime=null;schedule();
    }
    function aim(next){if(paused())return;target=clamp(next,positions[0],positions.at(-1));schedule();}
    function refresh(){stop();if(reduced.matches){value=target=neutral;velocity=0;display();}schedule();}
    function resize(){
      const rect=holder.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,1.5);
      const width=Math.max(1,Math.min(images[front].naturalWidth,Math.round(rect.width*dpr)));
      const height=Math.max(1,Math.round(width*images[front].naturalHeight/images[front].naturalWidth));
      if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;lastFrame=-1;display();}
    }
    listen(scene,'pointermove',event=>{
      if(event.pointerType!=='mouse'||!fine.matches||paused())return;
      if(pointer&&Math.hypot(event.clientX-pointer.x,event.clientY-pointer.y)<3)return;
      pointer={x:event.clientX,y:event.clientY};const bounds=scene.getBoundingClientRect(),portrait=holder.getBoundingClientRect();
      const center=portrait.left+portrait.width/2,distance=event.clientX-center;
      const reach=distance<0?Math.max(1,center-bounds.left):Math.max(1,bounds.right-center);
      const fraction=clamp(distance/reach,-1,1);
      aim(Math.abs(distance)<=3?neutral:neutral+fraction*(fraction<0?neutral-positions[0]:positions.at(-1)-neutral));
    },{passive:true});
    listen(scene,'pointerleave',event=>{if(event.pointerType&&event.pointerType!=='mouse')return;pointer=null;aim(neutral);},{passive:true});
    listen(control,'keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home'].includes(event.key))return;
      event.preventDefault();pointer=null;aim(event.key==='Home'?neutral:event.key==='ArrowLeft'?positions[0]:positions.at(-1));
    });
    listen(document,'visibilitychange',refresh);listen(reduced,'change',refresh);
    listen(fine,'change',()=>{pointer=null;if(!fine.matches)target=neutral;refresh();});
    const intersection=new IntersectionObserver(entries=>{visible=entries.some(entry=>entry.isIntersecting);refresh();});intersection.observe(scene);
    const resizer=new ResizeObserver(resize);resizer.observe(holder);
    const mutation=new MutationObserver(refresh);mutation.observe(document.body,{subtree:true,attributes:true,attributeFilter:['open','data-character-paused']});
    resize();display();root.dataset.ready='true';root.dataset.frameCount=String(images.length);schedule();
    const api={setTarget:aim,dispose(){disposed=true;stop();cleanups.forEach(fn=>fn());intersection.disconnect();resizer.disconnect();mutation.disconnect();canvas.remove();fallback();root.characterAnimation=null;root.characterAnimationTask=null;}};
    root.characterAnimation=api;return api;
  };
  window.mountKeyframeCharacter=(root,options={})=>{
    if(root.characterAnimationTask)return root.characterAnimationTask;
    const task=initialize(root,options);root.characterAnimationTask=task;
    task.catch(()=>{root.characterAnimationTask=null;});return task;
  };
  function mountAll(){
    for(const root of document.querySelectorAll('[data-keyframe-character]'))
      window.mountKeyframeCharacter(root).catch(error=>console.warn('Character stays at its neutral fallback.',error));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mountAll,{once:true});
  else mountAll();
})();
