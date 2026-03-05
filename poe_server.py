"""
Path of Exile 1 - Stash JSON Web Server
NOTE: This product isn't affiliated with or endorsed by Grinding Gear Games in any way.
Usage: python poe_server.py  then open http://localhost:8742
"""

import http.server, json, os, glob, urllib.parse, re
from socketserver import ThreadingMixIn
from datetime import datetime

PORT     = 8742
DATA_DIR = "poe_stash_data"
HOST     = "localhost"

# ---------------------------------------------------------------------------
# Load all items at startup
# ---------------------------------------------------------------------------
def load_all_items(data_dir):
    pattern  = os.path.join(data_dir, "*.json")
    files    = sorted(glob.glob(pattern))
    combined = [f for f in files if os.path.basename(f).startswith("all_stashes_")]
    targets  = combined if combined else [
        f for f in files
        if not os.path.basename(f).startswith("summary_")
        and not os.path.basename(f).startswith("tab_list_")
    ]
    all_items, seen = [], set()
    for fp in targets:
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            print(f"  WARNING: skipping {fp}: {e}")
            continue
        fname = os.path.basename(fp)
        if "tabs" in data and isinstance(data["tabs"], list):
            for tab in data["tabs"]:
                name = tab.get("tab_name") or tab.get("n") or "?"
                for item in tab.get("items", []):
                    _add(item, name, fname, all_items, seen)
        elif "items" in data and isinstance(data["items"], list):
            name = data.get("tab_name", "?")
            for item in data["items"]:
                _add(item, name, fname, all_items, seen)
    return all_items

def _add(item, tab, fname, lst, seen):
    iid = item.get("id")
    if iid:
        if iid in seen: return
        seen.add(iid)
    item["_tab"]  = tab
    item["_file"] = fname
    lst.append(item)

# ---------------------------------------------------------------------------
# Build the HTML page (no inline event handlers - all wired in JS)
# ---------------------------------------------------------------------------
def build_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PoE Stash Browser</title>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@700;900&family=Crimson+Pro:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0804;--panel:#110e09;--border:#3a2e1e;
  --gold:#c8982a;--gold-dim:#7a5c18;--gold-pale:#e8c96a;
  --text:#d4c5a0;--text-dim:#7a6e58;
  --c0:#c8c8c8;--c1:#8888ff;--c2:#c8b428;--c3:#af6025;
  --c4:#1aa29b;--c5:#aa9e82;--c6:#d0d0d0;--red:#c43030;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-family:'Crimson Pro',serif;display:flex;flex-direction:column}
header{flex-shrink:0;padding:11px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;background:linear-gradient(180deg,#1c150a,transparent)}
h1{font-family:'Cinzel',serif;font-size:1.15rem;font-weight:900;color:var(--gold);letter-spacing:.1em;text-shadow:0 0 20px #c8982a44}
#hstat{font-size:.8rem;color:var(--text-dim)}
#hstat b{color:var(--gold-pale)}
.bar{flex-shrink:0;padding:8px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:#0d0b07}
.sw{position:relative;flex:1;min-width:160px;max-width:340px}
.sw input{width:100%;background:#1a150d;border:1px solid var(--border);color:var(--text);font-family:'Crimson Pro',serif;font-size:.95rem;padding:5px 10px 5px 28px;border-radius:2px;outline:none}
.sw input:focus{border-color:var(--gold-dim)}
.sw input::placeholder{color:var(--text-dim)}
.si{position:absolute;left:8px;top:50%;transform:translateY(-50%);color:var(--text-dim);pointer-events:none}
select{background:#1a150d;border:1px solid var(--border);color:var(--text);font-family:'Crimson Pro',serif;font-size:.85rem;padding:5px 8px;border-radius:2px;outline:none;cursor:pointer}
.tbtn{background:#1a150d;border:1px solid var(--border);color:var(--text);font-family:'Crimson Pro',serif;font-size:.85rem;padding:5px 10px;border-radius:2px;cursor:pointer}
.tbtn.on{border-color:var(--gold);color:var(--gold-pale);background:#c8982a12}
#rstat{margin-left:auto;font-size:.78rem;color:var(--text-dim);white-space:nowrap}
#rstat b{color:var(--gold)}
.content{flex:1;overflow-y:auto;padding:18px 22px}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:220px;color:var(--text-dim);gap:8px;font-size:.95rem}
/* scrollbar */
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* TABLE */
.itbl{width:100%;border-collapse:collapse;font-size:.86rem}
.itbl th{font-family:'Cinzel',serif;font-size:.62rem;letter-spacing:.12em;color:var(--gold-dim);text-transform:uppercase;text-align:left;padding:6px 10px;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap}
.itbl th:hover{color:var(--gold)}
.itbl th.sc{color:var(--gold)}
.itbl td{padding:5px 10px;border-bottom:1px solid #1c180e;vertical-align:top;line-height:1.4}
.itbl tr:hover td{background:#ffffff05}
.f0 .tn{color:var(--c0)}.f1 .tn{color:var(--c1)}.f2 .tn{color:var(--c2)}.f3 .tn{color:var(--c3)}.f4 .tn{color:var(--c4)}.f5 .tn{color:var(--c5)}.f6 .tn{color:var(--c6)}
.tn{font-weight:600}
.ttype{color:var(--text-dim);font-style:italic}
.tilvl,.tqty{text-align:center}
.tilvl{color:#8899aa}
.tqty{color:var(--gold);font-weight:600}
.ttab{color:var(--text-dim);font-size:.78rem}
.tmods{color:#8899cc;font-size:.78rem;max-width:260px}
.bdg{display:inline-block;font-size:.62rem;padding:1px 5px;border-radius:2px;font-family:'Cinzel',serif}
.bn{background:#222;color:var(--c0)}.bm{background:#1a1a3a;color:var(--c1)}.br{background:#2a2400;color:var(--c2)}
.bu{background:#2a1200;color:var(--c3)}.bg{background:#001a1a;color:var(--c4)}.bc{background:#1a1710;color:var(--c5)}.bd{background:#1e1e1e;color:var(--c6)}

/* TOOLTIP */
.tgrid{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start}
.ptip{width:300px;font-family:'Crimson Pro',serif}
.pi{background:rgba(0,0,0,.93);border:1px solid #3a3020;overflow:hidden}
.pf0 .pi{box-shadow:0 0 7px #88888830}.pf1 .pi{box-shadow:0 0 10px #8888ff35;border-color:#2a2a5a}
.pf2 .pi{box-shadow:0 0 10px #c8b42835;border-color:#3a3200}.pf3 .pi{box-shadow:0 0 14px #af602550;border-color:#5a3010}
.pf4 .pi{box-shadow:0 0 10px #1aa29b40;border-color:#1a4a48}.pf5 .pi{box-shadow:0 0 7px #aa9e8230}
.pf6 .pi{box-shadow:0 0 7px #ffffff25;border-color:#444}
.ph{padding:7px 12px 6px;text-align:center;border-bottom:1px solid #2e2618}
.pf0 .ph{background:linear-gradient(180deg,#1e1e1e,#141414)}.pf1 .ph{background:linear-gradient(180deg,#14143a,#0c0c24)}
.pf2 .ph{background:linear-gradient(180deg,#201c00,#161200)}.pf3 .ph{background:linear-gradient(180deg,#220f00,#160900)}
.pf4 .ph{background:linear-gradient(180deg,#001818,#001010)}.pf5 .ph{background:linear-gradient(180deg,#18150a,#100e06)}
.pf6 .ph{background:linear-gradient(180deg,#1c1c1c,#121212)}
.pname{font-size:.93rem;font-weight:700;letter-spacing:.03em;line-height:1.3}
.ptype{font-size:.8rem;margin-top:2px}
.pf0 .pname,.pf0 .ptype{color:var(--c0)}.pf1 .pname,.pf1 .ptype{color:var(--c1)}.pf2 .pname,.pf2 .ptype{color:var(--c2)}
.pf3 .pname,.pf3 .ptype{color:var(--c3)}.pf4 .pname,.pf4 .ptype{color:var(--c4)}.pf5 .pname,.pf5 .ptype{color:var(--c5)}
.pf6 .pname,.pf6 .ptype{color:var(--c6)}
.psep{height:6px;background:linear-gradient(90deg,transparent,#6a5020 20%,#c89830 50%,#6a5020 80%,transparent);opacity:.5}
.pbody{padding:4px 11px}
.prow{display:flex;justify-content:space-between;gap:8px;padding:1px 0;font-size:.79rem}
.pl{color:var(--text-dim);white-space:nowrap}.pv{color:var(--text);text-align:right}
.pv.aug{color:var(--c1)}
.pmods{padding:3px 11px 5px}
.pmod{font-size:.8rem;padding:1px 0;line-height:1.45}
.pmod.ex{color:#8888ff}.pmod.im{color:#8888ff}.pmod.cr{color:#60aaff}.pmod.en{color:#b060ff}.pmod.fr{color:#e8c060}
.pfl{padding:4px 11px 5px;font-size:.78rem;font-style:italic;color:#b06820;border-top:1px solid #241c0c}
.pdescr{padding:4px 11px 5px;font-size:.78rem;color:var(--text-dim)}
.pcorr{text-align:center;color:var(--red);font-size:.79rem;padding:3px 11px 5px;letter-spacing:.08em}
.ptab{font-size:.6rem;color:var(--text-dim);opacity:.45;text-align:right;padding:2px 7px 3px;border-top:1px solid #1a1610}
.qsummary{background:#1a140a;border:1px solid var(--gold-dim);border-radius:2px;padding:10px 18px;margin-bottom:16px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.qsummary .qtotal{font-family:'Cinzel',serif;font-size:1.1rem;color:var(--gold-pale);font-weight:700;letter-spacing:.04em}
.qsummary .qbreakdown{font-size:.82rem;color:var(--text-dim)}
.qsummary .qbreakdown span{color:var(--text)}
.btn-exact-on{border-color:var(--gold)!important;color:var(--gold-pale)!important;background:#c8982a12!important}
</style>
</head>
<body>
<header>
  <h1>&#9879; PoE Stash Browser</h1>
  <span id="hstat">Loading&hellip;</span>
</header>
<div class="bar">
  <div class="sw"><span class="si">&#8981;</span><input id="search" type="text" placeholder="Search name, type, mods, tab&hellip;"></div>
  <select id="ffilter">
    <option value="">All types</option>
    <option value="0">Normal</option>
    <option value="1">Magic</option>
    <option value="2">Rare</option>
    <option value="3">Unique</option>
    <option value="4">Gem</option>
    <option value="5">Currency</option>
    <option value="6">Divination Card</option>
  </select>
  <button class="tbtn" id="btn-tbl">&#9776; Table</button>
  <button class="tbtn on" id="btn-tip">&#9670; Item View</button>
  <button class="tbtn" id="btn-exact" title="Match name exactly (no partial matches)">&#9632; Exact</button>
  <span id="rstat"></span>
</div>
<div class="content" id="content">
  <div class="empty"><div>&#9879;</div><div>Connecting&hellip;</div></div>
</div>
<script>
var ALL=[], mode="tooltip", sortCol="name", sortAsc=true, searchTimer=null, exactMatch=false;
var FL={0:"Normal",1:"Magic",2:"Rare",3:"Unique",4:"Gem",5:"Currency",6:"Div Card"};
var BC={0:"bn",1:"bm",2:"br",3:"bu",4:"bg",5:"bc",6:"bd"};

function qty(i){return i.stackSize!=null?i.stackSize:1;}
function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

function setStatus(msg){document.getElementById("content").innerHTML='<div class="empty"><div>'+msg+'</div></div>';}

document.getElementById("search").addEventListener("input",function(){
  clearTimeout(searchTimer);
  searchTimer=setTimeout(doSearch,350);
});
document.getElementById("ffilter").addEventListener("change",doSearch);
document.getElementById("btn-tbl").addEventListener("click",function(){setMode("table");});
document.getElementById("btn-tip").addEventListener("click",function(){setMode("tooltip");});
document.getElementById("btn-exact").addEventListener("click",function(){
  exactMatch=!exactMatch;
  this.classList.toggle("btn-exact-on", exactMatch);
  this.title=exactMatch?"Exact match ON - click to disable":"Match name exactly (no partial matches)";
  doSearch();
});

async function init(){
  setStatus("Connecting to server&hellip;");
  try{
    var r=await fetch("/api/stats");
    if(!r.ok) throw new Error("HTTP "+r.status);
    var s=await r.json();
    document.getElementById("hstat").innerHTML="<b>"+s.stacks.toLocaleString()+"</b> stacks &middot; <b>"+s.qty.toLocaleString()+"</b> items";
  }catch(e){
    setStatus("Cannot reach server: "+e.message);
    return;
  }
  doSearch();
}

async function doSearch(){
  var q=document.getElementById("search").value.trim();
  var ft=document.getElementById("ffilter").value;
  document.getElementById("rstat").innerHTML="searching&hellip;";
  var url="/api/search?limit=200"+(q?"&q="+encodeURIComponent(q):"")+(ft?"&frame="+encodeURIComponent(ft):"")+(exactMatch?"&exact=1":"");
  try{
    var r=await fetch(url);
    if(!r.ok) throw new Error("HTTP "+r.status);
    var data=await r.json();
    ALL=data.items;
    showResults(data.total);
  }catch(e){
    setStatus("Search error: "+e.message);
  }
}

function setMode(m){
  mode=m;
  document.getElementById("btn-tbl").className="tbtn"+(m==="table"?" on":"");
  document.getElementById("btn-tip").className="tbtn"+(m==="tooltip"?" on":"");
  if(ALL.length) showResults(ALL.length);
}

function showResults(total){
  var tq=ALL.reduce(function(s,i){return s+qty(i);},0);
  var st="<b>"+ALL.length+"</b> stacks &middot; <b>"+tq.toLocaleString()+"</b> qty";
  if(total>ALL.length) st+=" (top "+ALL.length+" of "+total+")";
  document.getElementById("rstat").innerHTML=st;
  if(!ALL.length){setStatus("No items match");return;}

  // Build quantity summary banner when multiple stacks of the same name exist
  var nameGroups={};
  ALL.forEach(function(item){
    var key=item.name||item.typeLine||"Unknown";
    if(!nameGroups[key]) nameGroups[key]={total:0,stacks:[]};
    var q2=qty(item);
    nameGroups[key].total+=q2;
    nameGroups[key].stacks.push({tab:item._tab||"?", qty:q2});
  });
  var summaryHtml="";
  Object.keys(nameGroups).forEach(function(name){
    var g=nameGroups[name];
    if(g.stacks.length<2 && g.total<=1) return; // skip singles with no stacks
    var breakdown=g.stacks.map(function(s){
      return "<span>"+esc(s.tab)+":</span> "+s.qty.toLocaleString();
    }).join(" &nbsp;|&nbsp; ");
    summaryHtml+="<div class='qsummary'>";
    summaryHtml+="<div><div style='font-size:.72rem;color:var(--text-dim);font-family:Cinzel,serif;letter-spacing:.1em'>TOTAL "+esc(name.toUpperCase())+"</div>";
    summaryHtml+="<div class='qtotal'>"+g.total.toLocaleString()+"</div></div>";
    if(g.stacks.length>1) summaryHtml+="<div class='qbreakdown'>"+breakdown+"</div>";
    summaryHtml+="</div>";
  });

  var el=document.getElementById("content");
  el.innerHTML=summaryHtml;
  mode==="table"?renderTable():renderTooltips();
}

/* ---- TABLE ---- */
var COLS=[
  {k:"name",l:"Name"},{k:"typeLine",l:"Base Type"},{k:"rarity",l:"Rarity"},
  {k:"ilvl",l:"iLvl"},{k:"qty",l:"Qty"},{k:"_tab",l:"Tab"},{k:"mods",l:"Mods"}
];

function getSortVal(item,k){
  if(k==="qty") return qty(item);
  if(k==="rarity") return item.frameType||0;
  if(k==="mods") return (item.explicitMods||[]).join(" ");
  return item[k]||"";
}

function setSort(k){
  if(sortCol===k) sortAsc=!sortAsc; else{sortCol=k;sortAsc=true;}
  showResults(ALL.length);
}

function renderTable(){
  var sorted=ALL.slice().sort(function(a,b){
    var va=getSortVal(a,sortCol), vb=getSortVal(b,sortCol);
    return va<vb?(sortAsc?-1:1):va>vb?(sortAsc?1:-1):0;
  });
  var h="<table class='itbl'><thead><tr>";
  COLS.forEach(function(c){
    var sc=sortCol===c.k?" sc":"";
    var ar=sortCol===c.k?(sortAsc?" &#9650;":" &#9660;"):" &#9650;";
    h+="<th class='"+sc+"' data-k='"+c.k+"'>"+c.l+ar+"</th>";
  });
  h+="</tr></thead><tbody>";
  sorted.forEach(function(item){
    var f=item.frameType||0, q=qty(item);
    var nm=item.name||item.typeLine||"Unknown";
    var ty=item.name?(item.typeLine||""):"";
    var mods=(item.explicitMods||[]).concat(item.implicitMods||[]);
    h+="<tr class='f"+f+"'>";
    h+="<td class='tn'>"+esc(nm)+"</td>";
    h+="<td class='ttype'>"+esc(ty)+"</td>";
    h+="<td><span class='bdg "+(BC[f]||"bn")+"'>"+(FL[f]||"?")+"</span></td>";
    h+="<td class='tilvl'>"+(item.ilvl!=null?item.ilvl:"&mdash;")+"</td>";
    h+="<td class='tqty'>"+(q>1?"x"+q.toLocaleString():"1")+"</td>";
    h+="<td class='ttab'>"+esc(item._tab||"")+"</td>";
    h+="<td class='tmods'>"+mods.slice(0,3).map(esc).join("<br>")+(mods.length>3?"<br>...":"")+"</td>";
    h+="</tr>";
  });
  h+="</tbody></table>";
  var el=document.getElementById("content");
  el.insertAdjacentHTML("beforeend", h);
  el.querySelectorAll("th[data-k]").forEach(function(th){
    th.addEventListener("click",function(){setSort(th.getAttribute("data-k"));});
  });
}

/* ---- TOOLTIP ---- */
function renderTooltips(){
  var frag=document.createDocumentFragment();
  ALL.forEach(function(item){frag.appendChild(buildTip(item));});
  var grid=document.createElement("div");
  grid.className="tgrid";
  grid.appendChild(frag);
  document.getElementById("content").appendChild(grid);
}

function buildTip(item){
  var f=item.frameType||0;
  var wrap=document.createElement("div");
  wrap.className="ptip pf"+f;
  var inner=document.createElement("div");
  inner.className="pi";

  var name=item.name||item.typeLine||"Unknown";
  var type=item.name?(item.typeLine||""):"";
  var h="<div class='ph'><div class='pname'>"+esc(name)+"</div>";
  if(type) h+="<div class='ptype'>"+esc(type)+"</div>";
  h+="</div>";

  /* properties */
  var props=item.properties||[];
  if(props.length){
    h+="<div class='psep'></div><div class='pbody'>";
    props.forEach(function(p){
      var vals=(p.values||[]).map(function(v){return v[0];}).join(", ");
      var aug=(p.values||[]).some(function(v){return v[1]===1;});
      h+="<div class='prow'><span class='pl'>"+esc(p.name)+"</span><span class='pv"+(aug?" aug":"")+"'>"+esc(vals)+"</span></div>";
    });
    h+="</div>";
  }

  /* requirements */
  var reqs=item.requirements||[];
  if(reqs.length){
    h+="<div class='psep'></div><div class='pbody'><div class='prow'><span class='pl'>Requires</span><span class='pv'>";
    h+=reqs.map(function(r){return esc(r.name)+" "+esc(((r.values||[[""]])[0]||[""])[0]);}).join(", ");
    h+="</span></div></div>";
  }

  /* item level / stack */
  var meta=[];
  if(item.ilvl!=null) meta.push("Item Level: "+item.ilvl);
  if(item.stackSize!=null) meta.push("Stack Size: "+item.stackSize.toLocaleString()+" / "+(item.maxStackSize||item.stackSize).toLocaleString());
  if(meta.length){
    h+="<div class='psep'></div><div class='pbody'>";
    meta.forEach(function(m){h+="<div class='prow'><span class='pl'>"+m+"</span></div>";});
    h+="</div>";
  }

  /* implicit */
  var impl=item.implicitMods||[];
  if(impl.length){
    h+="<div class='psep'></div><div class='pmods'>";
    impl.forEach(function(m){h+="<div class='pmod im'>"+esc(m)+"</div>";});
    h+="</div>";
  }

  /* explicit / crafted / enchant / fractured */
  var expl=item.explicitMods||[], craf=item.craftedMods||[], ench=item.enchantMods||[], frac=item.fracturedMods||[];
  if(expl.length||craf.length||ench.length||frac.length){
    h+="<div class='psep'></div><div class='pmods'>";
    ench.forEach(function(m){h+="<div class='pmod en'>"+esc(m)+"</div>";});
    frac.forEach(function(m){h+="<div class='pmod fr'>"+esc(m)+"</div>";});
    expl.forEach(function(m){h+="<div class='pmod ex'>"+esc(m)+"</div>";});
    craf.forEach(function(m){h+="<div class='pmod cr'>"+esc(m)+"</div>";});
    h+="</div>";
  }

  /* flavour */
  var fl=item.flavourText||[];
  if(fl.length) h+="<div class='psep'></div><div class='pfl'>"+fl.map(esc).join("<br>")+"</div>";
  if(item.descrText) h+="<div class='psep'></div><div class='pdescr'>"+esc(item.descrText)+"</div>";
  if(item.corrupted) h+="<div class='psep'></div><div class='pcorr'>Corrupted</div>";
  h+="<div class='ptab'>"+esc(item._tab||"")+"</div>";

  inner.innerHTML=h;
  wrap.appendChild(inner);
  return wrap;
}

init();
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
class ThreadedServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class Handler(http.server.BaseHTTPRequestHandler):
    ITEMS     = []
    STATS_JSON= b""

    def log_message(self, fmt, *args):
        print("  [%s] %s %s" % (datetime.now().strftime("%H:%M:%S"), args[0], args[1]))

    def send_bytes(self, body, ctype, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        mv, chunk = memoryview(body), 65536
        for i in range(0, len(body), chunk):
            self.wfile.write(mv[i:i+chunk])

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self.send_bytes(build_html().encode(), "text/html; charset=utf-8")
            return

        if path == "/api/stats":
            self.send_bytes(Handler.STATS_JSON, "application/json; charset=utf-8")
            return

        if path == "/api/search":
            q     = params.get("q",     [""])[0].strip()
            frame = params.get("frame", [""])[0]
            exact = params.get("exact", ["0"])[0] == "1"
            limit = min(int(params.get("limit", ["200"])[0]), 1000)
            ql    = q.lower()
            results = []
            for item in Handler.ITEMS:
                if frame and str(item.get("frameType", 0)) != frame:
                    continue
                if q:
                    item_name = (item.get("name") or item.get("typeLine") or "").strip()
                    if exact:
                        # Exact match: name or typeLine must equal query (case-insensitive)
                        if item_name.lower() != ql:
                            continue
                    else:
                        hay = " ".join(filter(None,[
                            item.get("name",""), item.get("typeLine",""),
                            " ".join(item.get("explicitMods") or []),
                            " ".join(item.get("implicitMods") or []),
                            " ".join(item.get("craftedMods")  or []),
                            " ".join(item.get("enchantMods")  or []),
                            item.get("_tab",""),
                        ])).lower()
                        if ql not in hay:
                            continue
                results.append(item)
                if len(results) >= limit:
                    break
            total = len(results)
            body  = json.dumps({"total": total, "items": results}, ensure_ascii=False).encode()
            self.send_bytes(body, "application/json; charset=utf-8")
            return

        self.send_bytes(b'{"error":"not found"}', "application/json", 404)

def main():
    if not os.path.isdir(DATA_DIR):
        print(f"  WARNING: '{DATA_DIR}' not found - run poe_stash_downloader.py first")

    print(f"  Loading items from '{DATA_DIR}'...")
    Handler.ITEMS = load_all_items(DATA_DIR)
    total_qty = sum((i.get("stackSize") or 1) for i in Handler.ITEMS)
    print(f"  Loaded {len(Handler.ITEMS)} stacks ({total_qty:,} items)")

    stats = {"stacks": len(Handler.ITEMS), "qty": total_qty}
    Handler.STATS_JSON = json.dumps(stats).encode()

    print(f"\n  URL : http://{HOST}:{PORT}")
    print(f"  Stop: Ctrl+C\n")

    server = ThreadedServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()

if __name__ == "__main__":
    main()
