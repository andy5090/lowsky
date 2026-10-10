const DESKTOP_ACTIONS=['open_3d','close_3d','show_monitor','toggle_monitor_fullscreen'];

export function desktopCommand(status,action,{busy=false,connected=true}={}) {
  if(status?.available!==true || !connected || busy || status.pending || !DESKTOP_ACTIONS.includes(action))return null;
  if(action==='close_3d' && !status.three_d_open)return null;
  return {action};
}
export function desktopShortcut(key,status,{editing=false,modal=false,repeat=false,modifier=false,...options}={}) {
  if(editing || modal || repeat || modifier)return null;
  return desktopCommand(status,key==='F6'?'open_3d':key==='F11'?'toggle_monitor_fullscreen':'',options);
}
export function acceptDesktopState(current,incoming) {
  if(typeof incoming?.available!=='boolean')return current;
  if(incoming.available===false)return incoming;
  if(current?.available && Number.isFinite(current.revision) && Number.isFinite(incoming.revision)
      && incoming.revision<current.revision)return current;
  return incoming;
}
