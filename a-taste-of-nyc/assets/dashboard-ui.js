/* Shared presentation only: hover values come from the Python chart payloads. */
(() => {
  let pointer={x:32,y:32};
  document.addEventListener('pointermove',e=>{pointer={x:e.clientX,y:e.clientY};},true);
  document.addEventListener('keydown',e=>{
    const modal=document.getElementById('chart-modal');
    if(!modal||getComputedStyle(modal).display==='none')return;
    if(e.key==='Escape'){e.preventDefault();document.getElementById('close-expanded')?.click();}
    if(e.key==='Tab'){
      const controls=[...modal.querySelectorAll('button,[tabindex="0"]')].filter(x=>x.offsetParent!==null);
      if(!controls.length)return;
      const first=controls[0],last=controls[controls.length-1];
      if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
    }
  });
  const no=()=>window.dash_clientside.no_update;
  const trigger=()=> (window.dash_clientside.callback_context.triggered[0]?.prop_id||'').split('.')[0];
  const node=(type,children,className)=>({namespace:'dash_html_components',type,props:{children,className}});
  const num=v=>v==null?'—':Number(v).toLocaleString('en-US');
  const pct=v=>v==null?'—':(100*Number(v)).toFixed(1)+'%';
  window.dash_clientside=Object.assign({},window.dash_clientside,{nyc_ui:{
    modalState:function(sc,bc,mc,close,back,reset,view,kind){
      const t=trigger(),n=no();
      if(['close-expanded','modal-backdrop','reset'].includes(t)){
        document.body.classList.remove('modal-open');
        const backId=t==='reset'?'reset':{scatter:'expand-scatter',bar:'expand-bar',map:'expand-borough',heatmap:'expand-borough'}[kind];
        setTimeout(()=>document.getElementById(backId)?.focus(),0);
        return [{display:'none'},null];
      }
      if(t==='expand-scatter')kind='scatter';
      else if(t==='expand-bar')kind='bar';
      else if(t==='expand-borough')kind=view==='map'?'map':'heatmap';
      else return [n,n];
      document.body.classList.add('modal-open');
      setTimeout(()=>document.getElementById('close-expanded')?.focus(),0);
      return [{display:'grid'},kind];
    },
    renderExpanded:function(kind,s,b,h,m,selection){
      const n=no();
      if(!kind)return [n,n,n,n];
      const original={scatter:s,bar:b,heatmap:h,map:m}[kind];
      if(!original?.layout)return [n,n,n,n];
      const figure=structuredClone(original);
      delete figure.layout.width;delete figure.layout.height;
      figure.layout.autosize=true;
      if(figure.layout.xaxis)figure.layout.xaxis.fixedrange=false;
      if(figure.layout.yaxis)figure.layout.yaxis.fixedrange=false;
      figure.layout.dragmode='zoom';
      figure.layout.font=Object.assign({},figure.layout.font,{size:15});
      if(kind==='scatter')figure.layout.margin={l:76,r:30,t:18,b:60};
      if(kind==='bar')figure.layout.margin={l:220,r:100,t:12,b:60};
      if(kind==='heatmap')figure.layout.margin={l:160,r:30,t:15,b:155};
      if(kind==='map'){
        figure.layout.margin={l:80,r:50,t:26,b:68};
        figure.layout.dragmode='pan';figure.layout.uirevision='expanded-map';
        (figure.layout.annotations||[]).forEach(a=>{if(a.xref!=='paper')a.font=Object.assign({},a.font,{size:14});});
        figure.layout.xaxis.fixedrange=false;figure.layout.yaxis.fixedrange=false;
      }
      const titles={scatter:'Cuisine size & inspection grades',bar:'Most common cuisines',heatmap:'Cuisine share · Heatmap',map:'Cuisine share · Map'};
      return [figure,titles[kind],selection||'Current dashboard selection','modal-card modal-'+kind];
    },
    forwardClick:function(click,kind){
      const n=no(),out=[n,n,n,n,n];
      if(!click?.points?.length||!kind)return out;
      const i={scatter:0,bar:1,heatmap:2,map:3}[kind];
      if(i!==undefined)out[i]=click;
      out[4]=null;return out;
    },
    tooltip:function(s,b,h,m,e,kind,view,mapFigure,expandedFigure){
      const id=trigger(),n=no();
      const data={scatter:s,bar:b,heatmap:h,'borough-map':m,'expanded-graph':e}[id];
      const p=data?.points?.[0];
      if(!p)return [{display:'none'},n];
      const type=id==='expanded-graph'?kind:({'borough-map':'map'}[id]||id);
      const c=p.customdata||[];
      let title='',scope='',rows=[],foot='';
      if(type==='scatter'){
        if(!c.length)return [{display:'none'},n];
        title=c[0];scope=c[5];rows=[['Restaurants',num(c[1])],['Graded (A/B/C)',num(c[2])],['Grade A restaurants',num(c[3])],['Grade A rate',pct(p.y)]];
        foot=c[2]<10?'Small graded sample · fewer than 10 restaurants':c[4];
      }else if(type==='bar'){
        title=c[0];scope=c[3];rows=[['Restaurants',num(c[1])],['Share of all restaurants',pct(c[2])],['Cuisine rank','#'+num(c[4])]];
      }else if(type==='heatmap'){
        title=c[1];scope=c[0];rows=[['Restaurants',num(c[2])],['Share of borough',pct(p.z)],['All borough restaurants',num(c[3])]];
      }else if(type==='map'){
        const figure=id==='expanded-graph'?expandedFigure:mapFigure;
        const meta=figure?.layout?.meta,row=meta?.boroughs?.[p.curveNumber];
        if(!row)return [{display:'none'},n];
        title=meta.cuisine||'Choose a cuisine';scope=row.borough;
        rows=meta.cuisine?[['Restaurants',num(row.restaurants)],['Share of borough',pct(row.share)],['All borough restaurants',num(row.total)]]:[['All borough restaurants',num(row.total)]];
        if(!meta.cuisine)foot='Choose a cuisine in Filters to compare borough shares.';
      }else return [{display:'none'},n];
      const children=[node('Div',title,'tooltip-title'),node('Div',scope,'tooltip-scope'),
        node('Div',rows.map(([label,value])=>node('Div',[node('Span',label,'tooltip-label'),node('Strong',value,'tooltip-value')],'tooltip-row')),'tooltip-rows')];
      if(foot)children.push(node('Div',foot,'tooltip-foot'));
      const width=Math.min(310,innerWidth-28),height=96+rows.length*28+(foot?36:0);
      const left=pointer.x+width+18>innerWidth?pointer.x-width-14:pointer.x+14;
      const top=Math.max(12,Math.min(pointer.y+14,innerHeight-height-12));
      return [{display:'block',position:'fixed',left:Math.max(12,left)+'px',top:top+'px',width:width+'px'},children];
    }
  }});
})();
