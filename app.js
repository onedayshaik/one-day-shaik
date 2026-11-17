let allNews=[];let active="All";
const el=id=>document.getElementById(id);
function esc(s){return String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function niceDate(v){if(!v)return "Latest";let d=new Date(v);return isNaN(d)?"Latest":d.toLocaleString("en-IN",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"});}
function render(){
 const items=allNews.filter(x=>active==="All"||x.category===active);
 el("count").textContent=items.length+" headlines";
 el("section-title").textContent=active==="All"?"Aaj ki headlines":active+" updates";
 if(!items.length){el("news").innerHTML='<div class="empty">Abhi is category mein news nahi mili. Thodi der baad refresh karein.</div>';return;}
 el("news").innerHTML=items.map(x=>`<article class="story"><div class="story-top"><span class="tag">${esc(x.category)}</span><span class="date">${esc(niceDate(x.published))}</span></div><h3>${esc(x.hinglish_title||x.title)}</h3><p class="explain">${esc(x.explanation||"Is khabar ki simple explanation abhi available nahi hai. Original report padhne ke liye neeche diye link par click karein.")}</p><div class="source"><span>Source: <b>${esc(x.source)}</b></span><a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">Original news padhein ↗</a></div></article>`).join("");
}
async function load(){
 el("news").innerHTML='<div class="loading">Aaj ki news load ho rahi hai…</div>';
 try{const r=await fetch("data/news.json?ts="+Date.now(),{cache:"no-store"});if(!r.ok)throw new Error();
 const d=await r.json();allNews=d.items||[];
 el("updated").textContent="Aakhri update: "+(d.updated?new Date(d.updated).toLocaleString("en-IN"):"Abhi nahi")+" • Automatic updates";
 render();
 }catch(e){el("news").innerHTML='<div class="empty">Pehli automatic news update ka intezar hai. GitHub Actions mein workflow run karein.</div>';el("updated").textContent="News update ka intezar hai";}
}
document.querySelectorAll(".filter").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".filter").forEach(x=>x.classList.remove("active"));b.classList.add("active");active=b.dataset.cat;render();}));
el("refresh").addEventListener("click",load);load();setInterval(load,5*60*1000);