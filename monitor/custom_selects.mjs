// Native selects retain form values and events; all interaction uses an in-app combobox.
export function moveOption(options,index,direction) {
  const enabled=options.filter(option=>!option.disabled && !option.hidden);
  if(!enabled.length)return -1;
  if(direction==='first')return enabled[0].index;
  if(direction==='last')return enabled.at(-1).index;
  const position=enabled.findIndex(option=>option.index===index);
  if(position<0)return direction==='previous'?enabled.at(-1).index:enabled[0].index;
  return enabled[(position+(direction==='previous'?-1:1)+enabled.length)%enabled.length].index;
}
export function matchOption(options,index,query) {
  const enabled=options.filter(option=>!option.disabled && !option.hidden);
  const text=query.trim().toLocaleLowerCase();
  if(!text || !enabled.length)return index;
  const start=enabled.findIndex(option=>option.index===index);
  for(let step=1;step<=enabled.length;step++) {
    const option=enabled[(Math.max(-1,start)+step)%enabled.length];
    if(option.label.toLocaleLowerCase().startsWith(text))return option.index;
  }
  return index;
}
export function menuPlacement(rect,viewport,count,contentHeight=null) {
  const gap=4,margin=8;
  const below=Math.max(0,viewport.height-rect.bottom-gap-margin),above=Math.max(0,rect.top-gap-margin);
  const desired=Math.min(320,Math.max(44,contentHeight ?? count*36+8));
  const upward=below<desired && above>below;
  const height=Math.min(desired,upward?above:below);
  const width=Math.min(Math.max(rect.width,150),Math.max(0,viewport.width-margin*2));
  return {left:Math.max(margin,Math.min(rect.left,viewport.width-width-margin)),
    top:upward?rect.top-gap-height:rect.bottom+gap,width,maxHeight:height};
}
export function enhanceSelects(doc=document) {
  const win=doc.defaultView,entries=new Map();
  let opened=null,sequence=0;
  const readOptions=select=>Array.from(select.options).map((option,index)=>({index,value:option.value,
    label:option.label || option.textContent || '',hidden:option.hidden,
    disabled:option.disabled || (option.parentElement?.tagName==='OPTGROUP' && option.parentElement.disabled)}));
  function close() {
    if(!opened)return;
    const entry=opened;opened=null;
    entry.trigger.setAttribute('aria-expanded','false');entry.trigger.removeAttribute('aria-activedescendant');
    if(typeof entry.menu.hidePopover==='function' && entry.menu.matches(':popover-open'))entry.menu.hidePopover();
    entry.menu.remove();entry.search='';
  }
  function position(entry) {
    if(opened!==entry)return;
    const rect=entry.trigger.getBoundingClientRect();
    if(!rect.width || !rect.height || entry.trigger.closest('[hidden]') || !entry.trigger.isConnected){close();return;}
    const view=win.visualViewport;
    const viewport={width:view?.width || win.innerWidth,height:view?.height || win.innerHeight};
    const count=entry.options.filter(option=>!option.hidden).length;
    const estimate=menuPlacement(rect,viewport,count);
    // Measure at the final width: translated/wrapped labels can be taller than one row.
    entry.menu.style.width=`${estimate.width}px`;
    const contentHeight=entry.menu.scrollHeight+entry.menu.offsetHeight-entry.menu.clientHeight;
    const placement=menuPlacement(rect,viewport,count,contentHeight);
    Object.assign(entry.menu.style,{left:`${placement.left}px`,top:`${placement.top}px`,maxHeight:`${placement.maxHeight}px`});
  }
  function markActive(entry,scroll=false) {
    for(const row of entry.menu.querySelectorAll('[role="option"]')) {
      const index=Number(row.dataset.optionIndex);
      row.setAttribute('aria-selected',String(index===entry.select.selectedIndex));
      row.classList.toggle('is-active',index===entry.active);
    }
    const active=entry.menu.querySelector(`[data-option-index="${entry.active}"]`);
    if(active){entry.trigger.setAttribute('aria-activedescendant',active.id);if(scroll)active.scrollIntoView({block:'nearest'});}
    else entry.trigger.removeAttribute('aria-activedescendant');
  }
  function fillMenu(entry) {
    entry.menu.replaceChildren();
    for(const option of entry.options) {
      if(option.hidden)continue;
      const row=doc.createElement('div');row.id=`${entry.menu.id}-option-${option.index}`;
      row.className='custom-select-option';row.setAttribute('role','option');row.dataset.optionIndex=String(option.index);
      row.setAttribute('aria-disabled',String(Boolean(option.disabled)));row.textContent=option.label;
      row.addEventListener('pointerdown',event=>event.preventDefault());
      row.addEventListener('pointermove',()=>{if(!option.disabled){entry.active=option.index;markActive(entry);}});
      row.addEventListener('click',()=>{if(!option.disabled){entry.active=option.index;commit(entry);}});
      entry.menu.append(row);
    }
    markActive(entry);
  }
  function open(entry) {
    syncEntry(entry);
    if(entry.trigger.disabled)return false;
    close();opened=entry;
    entry.active=entry.options.some(option=>option.index===entry.select.selectedIndex && !option.disabled && !option.hidden)
      ? entry.select.selectedIndex : moveOption(entry.options,-1,'first');
    const host=entry.trigger.closest('dialog[open]') || doc.body;
    host.append(entry.menu);entry.trigger.setAttribute('aria-expanded','true');fillMenu(entry);
    if(typeof entry.menu.showPopover==='function')entry.menu.showPopover();
    position(entry);markActive(entry,true);return true;
  }
  function commit(entry) {
    // Options may change while a menu is open; validate against the live native source.
    const current=readOptions(entry.select).find(item=>item.index===entry.active);
    if(entry.select.disabled || !current || current.disabled || current.hidden){close();syncEntry(entry);return;}
    const changed=entry.select.selectedIndex!==entry.active;
    entry.select.selectedIndex=entry.active;entry.invalid=false;close();
    if(changed){entry.select.dispatchEvent(new win.Event('input',{bubbles:true}));entry.select.dispatchEvent(new win.Event('change',{bubbles:true}));}
    sync();entry.trigger.focus({preventScroll:true});
  }
  function syncEntry(entry) {
    const {select,trigger}=entry;
    const options=readOptions(select),signature=JSON.stringify(options);
    const previous=entry.options.find(option=>option.index===entry.active);
    const optionsChanged=signature!==entry.signature;
    entry.options=options;entry.signature=signature;
    const selected=options.find(option=>option.index===select.selectedIndex);
    entry.text.textContent=selected?.label || '\u2014';
    trigger.disabled=select.disabled || !options.some(option=>!option.disabled && !option.hidden);
    trigger.setAttribute('aria-required',String(select.required));
    trigger.setAttribute('aria-invalid',String(Boolean(entry.invalid && !select.validity.valid)));
    const label=select.getAttribute('aria-label');
    if(label){trigger.setAttribute('aria-label',label);trigger.removeAttribute('aria-labelledby');}
    else {
      const labels=Array.from(select.labels || []);
      for(const [index,item] of labels.entries())if(!item.id)item.id=`${entry.id}-label-${index}`;
      if(labels.length)trigger.setAttribute('aria-labelledby',labels.map(item=>item.id).join(' '));
    }
    const description=select.getAttribute('aria-describedby');
    if(description)trigger.setAttribute('aria-describedby',description);else trigger.removeAttribute('aria-describedby');
    if(opened===entry) {
      if(trigger.disabled || !trigger.isConnected || trigger.closest('[hidden]')){close();return;}
      if(optionsChanged){entry.active=options.find(option=>option.value===previous?.value && !option.disabled && !option.hidden)?.index ?? moveOption(options,select.selectedIndex,'first');fillMenu(entry);}
      else markActive(entry);
      position(entry);
    }
  }
  function mount(select) {
    const id=select.id || `custom-source-${++sequence}`;
    const wrapper=doc.createElement('span');wrapper.className='custom-select';wrapper.dataset.selectId=id;
    const trigger=doc.createElement('button');trigger.type='button';trigger.id=`${id}-combobox`;trigger.className='custom-select-trigger';
    trigger.setAttribute('role','combobox');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-controls',`${id}-listbox`);
    const text=doc.createElement('span');text.className='custom-select-text';trigger.append(text);
    const arrow=doc.createElement('span');arrow.className='custom-select-arrow';arrow.setAttribute('aria-hidden','true');arrow.textContent='⌄';trigger.append(arrow);
    wrapper.append(trigger);select.after(wrapper);
    const menu=doc.createElement('div');menu.id=`${id}-listbox`;menu.className='custom-select-menu';menu.setAttribute('role','listbox');menu.setAttribute('aria-labelledby',trigger.id);
    if(typeof menu.showPopover==='function')menu.setAttribute('popover','manual');
    const entry={id,select,wrapper,trigger,text,menu,options:[],signature:'',active:-1,search:'',searchAt:0,invalid:false,
      previousTabindex:select.getAttribute('tabindex'),previousAriaHidden:select.getAttribute('aria-hidden')};
    entries.set(select,entry);select.classList.add('custom-select-source');select.setAttribute('tabindex','-1');select.setAttribute('aria-hidden','true');
    const onFocus=()=>trigger.focus({preventScroll:true});
    const onInvalid=event=>{event.preventDefault();entry.invalid=true;syncEntry(entry);trigger.focus();};
    const onChange=()=>{entry.invalid=false;syncEntry(entry);};
    const onNativePointer=event=>{event.preventDefault();trigger.focus();};
    select.addEventListener('focus',onFocus);select.addEventListener('invalid',onInvalid);select.addEventListener('change',onChange);select.addEventListener('pointerdown',onNativePointer);select.addEventListener('click',onNativePointer);
    entry.cleanup=()=>{select.removeEventListener('focus',onFocus);select.removeEventListener('invalid',onInvalid);select.removeEventListener('change',onChange);select.removeEventListener('pointerdown',onNativePointer);select.removeEventListener('click',onNativePointer);};
    trigger.addEventListener('click',()=>{if(opened===entry)close();else open(entry);});
    trigger.addEventListener('keydown',event=>{
      const key=event.key,isOpen=opened===entry;
      if(key==='Escape' && isOpen){event.preventDefault();event.stopPropagation();close();return;}
      if(key==='Tab'){if(isOpen)commit(entry);return;}
      if(event.ctrlKey || event.metaKey || event.altKey)return;
      if(['ArrowDown','ArrowUp','Home','End'].includes(key)) {
        event.preventDefault();
        if(!isOpen){open(entry);if(['ArrowDown','ArrowUp'].includes(key))return;}
        entry.active=moveOption(entry.options,entry.active,{ArrowDown:'next',ArrowUp:'previous',Home:'first',End:'last'}[key]);markActive(entry,true);return;
      }
      if(key==='Enter' || key===' ') {event.preventDefault();if(isOpen)commit(entry);else open(entry);return;}
      if(key.length===1 && !event.isComposing) {
        event.preventDefault();if(!isOpen && !open(entry))return;
        const now=Date.now();entry.search=now-entry.searchAt>700?'':entry.search;entry.searchAt=now;
        entry.search+=key;
        const query=Array.from(entry.search).every(character=>character===entry.search[0])?entry.search[0]:entry.search;
        entry.active=matchOption(entry.options,entry.active,query);markActive(entry,true);
      }
    });
    menu.addEventListener('toggle',event=>{if(event.newState==='closed' && opened===entry)close();});
    syncEntry(entry);
  }
  function sync() {
    for(const select of doc.querySelectorAll('select'))if(!entries.has(select))mount(select);
    for(const [select,entry] of entries) {
      if(!select.isConnected){if(opened===entry)close();entry.cleanup();entry.wrapper.remove();entries.delete(select);}
      else syncEntry(entry);
    }
  }
  const outside=event=>{if(opened && !opened.wrapper.contains(event.target) && !opened.menu.contains(event.target))close();};
  const focus=event=>{if(opened && !opened.wrapper.contains(event.target) && !opened.menu.contains(event.target))close();};
  const reposition=()=>{if(opened)position(opened);};
  const reset=()=>win.setTimeout(()=>{for(const entry of entries.values())entry.invalid=false;sync();},0);
  doc.addEventListener('pointerdown',outside,true);doc.addEventListener('focusin',focus);doc.addEventListener('scroll',reposition,true);doc.addEventListener('reset',reset,true);
  win.addEventListener('resize',reposition);win.visualViewport?.addEventListener('resize',reposition);
  sync();
  return {sync,close,destroy(){close();for(const entry of entries.values()) {
    entry.cleanup();entry.wrapper.remove();entry.select.classList.remove('custom-select-source');
    for(const [attribute,value] of [['tabindex',entry.previousTabindex],['aria-hidden',entry.previousAriaHidden]]){if(value===null)entry.select.removeAttribute(attribute);else entry.select.setAttribute(attribute,value);}
  }entries.clear();doc.removeEventListener('pointerdown',outside,true);doc.removeEventListener('focusin',focus);doc.removeEventListener('scroll',reposition,true);doc.removeEventListener('reset',reset,true);win.removeEventListener('resize',reposition);win.visualViewport?.removeEventListener('resize',reposition);}};
}
