def boot_html(display_url):
    # Page affichée par le kiosk au démarrage. Interroge l'agent (same-origin),
    # laisse 5 s pour aller à la config, sinon navigue vers le display distant.
    return """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ComRoster — Afficheur</title>
<style>
 body{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;
 justify-content:center;background:#0A1628;color:#eaf1f9;font-family:system-ui,sans-serif}
 .count{font-size:1rem;color:#8aa0b8;margin-top:1.5rem}
 a.btn{margin-top:2rem;padding:.8rem 1.6rem;background:#3AAFA9;color:#04121b;
 border-radius:10px;text-decoration:none;font-weight:700}
 .err{color:#ff9;margin-top:1rem}
</style></head><body>
<h1>🎧 ComRoster — Afficheur</h1>
<div id="msg">Recherche du serveur…</div>
<a class="btn" href="/config">⚙ Configurer</a>
<div class="count" id="count"></div>
<script>
let left=5;
const msg=document.getElementById("msg"), count=document.getElementById("count");
async function tick(){
  let st={reachable:false,display_url:null};
  try{ st=await fetch("/api/server-status").then(r=>r.json()); }catch(e){}
  if(left<=0){
    if(st.reachable && st.display_url){ location.href=st.display_url; return; }
    location.href="/config"; return;
  }
  msg.textContent = st.reachable ? "Serveur trouvé — démarrage de l'affichage…"
                                 : "Serveur introuvable — ouverture de la configuration…";
  count.textContent = "("+left+"…)";
  left--; setTimeout(tick,1000);
}
tick();
</script></body></html>"""


def config_html(viewer_cfg, net_cfg):
    ip = viewer_cfg.get("server_ip", "")
    mode = net_cfg.get("mode", "link-local")
    addr = net_cfg.get("address", "")
    prefix = net_cfg.get("prefix", 24)

    def sel(m):
        return " selected" if mode == m else ""

    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Configuration afficheur</title>
<style>
 body{{margin:0;min-height:100vh;background:#0A1628;color:#eaf1f9;
 font-family:system-ui,sans-serif;display:flex;justify-content:center}}
 form{{max-width:420px;width:100%;padding:2rem}}
 label{{display:block;margin:1rem 0 .3rem}}
 input,select{{width:100%;padding:.6rem;border-radius:8px;border:1px solid #2b3f57;
 background:#12203a;color:#eaf1f9;box-sizing:border-box}}
 button{{margin-top:1.5rem;width:100%;padding:.9rem;background:#3AAFA9;color:#04121b;
 border:none;border-radius:10px;font-weight:700;font-size:1rem}}
 .qr{{text-align:center;margin-bottom:1rem}}
 .ok{{color:#7CFFB2}}.err{{color:#ff9}}
</style></head><body><form method="POST" action="/config">
<h1>Configuration de l'afficheur</h1>
<div class="qr"><img src="/qr.svg" width="150" alt="QR config"></div>
<label>IP du serveur ComRoster</label>
<input name="server_ip" value="{ip}" placeholder="192.168.42.10" inputmode="decimal">
<label>Adresse réseau de cet afficheur</label>
<select name="network_mode" onchange="document.getElementById('st').hidden=this.value!=='static'">
 <option value="link-local"{sel('link-local')}>Automatique (link-local)</option>
 <option value="dhcp"{sel('dhcp')}>Automatique (DHCP)</option>
 <option value="static"{sel('static')}>IP fixe</option>
</select>
<div id="st" {'hidden' if mode != 'static' else ''}>
 <label>IP fixe de l'afficheur</label>
 <input name="network_address" value="{addr}" placeholder="192.168.42.50" inputmode="decimal">
 <label>Préfixe (CIDR)</label>
 <input name="network_prefix" type="number" min="1" max="32" value="{prefix}">
</div>
<button type="submit">Enregistrer et redémarrer</button>
</form></body></html>"""
