/* Render the current application document, including content below the fold. */
(function(){
  'use strict';
  let busy=false;
  async function capture(save,progress=()=>{}){
    if(busy)throw Error('An application screenshot is already running.');
    if(!window.html2canvas)throw Error('The bundled screenshot renderer is unavailable.');
    busy=true;
    try{
      progress('Rendering the full application page…');
      await document.fonts?.ready;
      const width=document.documentElement.clientWidth,height=Math.max(document.body.scrollHeight,document.documentElement.scrollHeight);
      const scale=Math.min(1,30000/Math.max(width,height),Math.sqrt(40000000/(width*height)));
      if(scale<.2)throw Error('This page is too large for a readable PNG. Collapse long sections or filter the log, then retry.');
      const canvas=await html2canvas(document.body,{width,height,scale,scrollX:0,scrollY:0,windowWidth:width,windowHeight:innerHeight,
        backgroundColor:getComputedStyle(document.body).backgroundColor,useCORS:true,allowTaint:false,logging:false,imageTimeout:10000,
        onclone:doc=>{
          doc.querySelectorAll('input[type=password]').forEach(e=>{e.value='';e.setAttribute('value','');});
          doc.querySelectorAll('.topbar,.cr-ruler,.cr-lane-name').forEach(e=>e.style.position='static');
        }});
      progress('Saving application PNG…');
      const result=await save({png:canvas.toDataURL('image/png')});
      progress('Application screenshot saved: '+result.file+(scale<1?' (scaled to fit PNG limits)':''));
      return result;
    }finally{busy=false;}
  }
  window.A2Screenshot={capture};
})();
