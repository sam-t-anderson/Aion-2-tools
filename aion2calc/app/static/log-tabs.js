/* Shared combat-log list navigation; hides panels without resetting queues. */
window.A2LogTabs={mount(root,initial='community',onChange=()=>{}){
  const buttons=[...root.querySelectorAll('[data-log-tab]')],panels=[...root.querySelectorAll('[data-log-panel]')];
  function select(value){if(!buttons.some(b=>b.dataset.logTab===value))value='community';
    for(const b of buttons){const active=b.dataset.logTab===value;b.classList.toggle('primary',active);b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;}
    for(const p of panels)p.hidden=p.dataset.logPanel!==value;
    onChange(value);
  }
  buttons.forEach((b,i)=>{b.onclick=()=>select(b.dataset.logTab);b.onkeydown=e=>{let next;if(e.key==='ArrowRight')next=(i+1)%buttons.length;else if(e.key==='ArrowLeft')next=(i+buttons.length-1)%buttons.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=buttons.length-1;else return;e.preventDefault();select(buttons[next].dataset.logTab);buttons[next].focus();};});select(initial);return {select};
}};
