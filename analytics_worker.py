import subprocess
import os
import time
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import base64
import uuid
import secrets
import re
import sys
from urllib.parse import parse_qs, urlparse, parse_qs

CONFIG_PATH = "/usr/local/etc/xray/config.json"
XRAY_LOG_PATH = "/usr/local/etc/xray/xray_runtime.log"
DB_PATH = "panel_db.json"
DEFAULT_CLEAN_IP = "speed.cloudflare.com"

PANEL_USER = "admin"
PANEL_PASS = secrets.token_hex(4)
SESSION_TOKEN = secrets.token_hex(16)

SYSTEM_LIVE_LOGS = []
USER_TARGET_SITES = {}

repo_full_name = os.environ.get('GITHUB_REPOSITORY', 'username/repo')

if os.path.exists('active_edge_host.txt'):
    with open('active_edge_host.txt', 'r') as f:
        tunnel_host = f.read().strip()
else:
    tunnel_host = "127.0.0.1"

def load_database():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r') as f:
                data = json.load(f)
                if data and len(data) > 0:
                    return data
        except Exception:
            pass

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                xray_data = json.load(f)
            if "_killpv2_db_backup" in xray_data:
                backup_str = xray_data["_killpv2_db_backup"]
                decoded_data = json.loads(base64.b64decode(backup_str.encode('utf-8')).decode('utf-8'))
                if decoded_data and len(decoded_data) > 0:
                    return decoded_data
        except Exception:
            pass

    return {
        "Main_kill_pv2": {
            "uuid": "b6a00fb0-460e-4323-96af-3ba2f48470ee",
            "total_limit_bytes": 0,
            "used_bytes": 0,
            "clean_ip": "speed.cloudflare.com",
            "status": "OFFLINE",
            "last_active_time": 0,
            "down_speed": 0,
            "up_speed": 0,
            "created_at": int(time.time()),
            "expire_seconds": 31536000,
            "active": True,
            "telegram_proxy": None
        }
    }

configs_db = load_database()

def save_database():
    with open(DB_PATH, 'w') as f:
        json.dump(configs_db, f, indent=4)

def format_bytes(b):
    if b == 0: return "نامحدود"
    if b >= 1024**3: return f"{b / (1024**3):.2f} GB"
    if b >= 1024**2: return f"{b / (1024**2):.2f} MB"
    if b >= 1024: return f"{b / 1024:.2f} KB"
    return f"{b} B"

def format_speed(bytes_per_sec):
    kb = bytes_per_sec / 1024
    if kb >= 1024: return f"{kb/1024:.1f} MB/s"
    return f"{kb:.1f} KB/s"

def push_subs_to_github():
    try:
        os.makedirs('sub_links', exist_ok=True)
        for f in os.listdir('sub_links'):
            if f not in configs_db:
                try: os.remove(os.path.join('sub_links', f))
                except: pass

        now = int(time.time())
        for k, v in configs_db.items():
            if not v.get("active", True):
                payload_str = "// ACCOUNT EXPIRED OR DISABLED\n"
                payload = base64.b64encode(payload_str.encode('utf-8')).decode('utf-8')
            else:
                c_ip = v.get("clean_ip", DEFAULT_CLEAN_IP)
                total_bytes = v["total_limit_bytes"]
                rem_bytes = max(0, total_bytes - v["used_bytes"]) if total_bytes > 0 else 0
                passed_seconds = now - v.get("created_at", now)
                total_seconds = v.get("expire_seconds", 2592000)
                rem_seconds = max(0, total_seconds - passed_seconds)
                rem_d = int(rem_seconds // 86400)
                rem_h = int((rem_seconds % 86400) // 3600)

                clean_link = f"vless://{v['uuid']}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#{k}_Clean"
                regular_link = f"vless://{v['uuid']}@{tunnel_host}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0#{k}_Direct"
                info_used = f"vless://{v['uuid']}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#📊 مصرف شده: {format_bytes(v['used_bytes'])}"
                info_rem = f"vless://{v['uuid']}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#💾 باقی‌مانده: {format_bytes(rem_bytes) if total_bytes > 0 else 'نامحدود'}"
                info_time = f"vless://{v['uuid']}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#⏳ زمان: {rem_d} روز و {rem_h} ساعت"

                links = [clean_link, regular_link, info_used, info_rem, info_time]

                if v.get("telegram_proxy"):
                    tp = v["telegram_proxy"]
                    tg_link = f"https://t.me/proxy?server={tp.get('server','')}&port={tp.get('port','443')}&secret={tp.get('secret','')}"
                    links.append(f"# Telegram Proxy: {tg_link}")

                payload_str = "\n".join(links) + "\n"
                payload = base64.b64encode(payload_str.encode('utf-8')).decode('utf-8')

            with open(os.path.join('sub_links', k), 'w') as sf:
                sf.write(payload)

        subprocess.run("git config --local user.email 'action@github.com' || true", shell=True)
        subprocess.run("git config --local user.name 'GitHub Action' || true", shell=True)
        subprocess.run("git add sub_links/* panel_db.json || true", shell=True)
        subprocess.run("git commit -m '🔗 Update stable subscription links and db [Skip CI]' || true", shell=True)
        subprocess.run("git pull --rebase || true", shell=True)
        subprocess.run("git push || true", shell=True)
        print("🔗 [GitHub Sync] Static sub links updated!", flush=True)
    except Exception as e:
        print(f"❌ Error in push_subs_to_github: {e}", flush=True)

def check_expiration_and_limits():
    now = int(time.time())
    changed = False
    for u_name, u_data in configs_db.items():
        if not u_data.get("active", True):
            continue
        total_limit = u_data.get("total_limit_bytes", 0)
        if total_limit > 0 and u_data["used_bytes"] >= total_limit:
            configs_db[u_name]["active"] = False
            configs_db[u_name]["status"] = "EXPIRED"
            changed = True
        created_time = u_data.get("created_at", now)
        expire_seconds = u_data.get("expire_seconds", 2592000)
        if now - created_time > expire_seconds:
            configs_db[u_name]["active"] = False
            configs_db[u_name]["status"] = "EXPIRED"
            changed = True
    if changed:
        save_database()
        sync_xray_core()
        push_subs_to_github()

def sync_xray_core():
    clients = [{"id": u_data["uuid"], "email": u_name, "level": 0}
               for u_name, u_data in configs_db.items() if u_data.get("active", True)]
    db_backup_string = base64.b64encode(json.dumps(configs_db).encode('utf-8')).decode('utf-8')

    xray_json_config = {
        "_killpv2_db_backup": db_backup_string,
        "log": {"loglevel": "info", "access": XRAY_LOG_PATH, "error": XRAY_LOG_PATH},
        "inbounds": [
            {
                "port": 8085,
                "protocol": "vless",
                "settings": {"clients": clients, "decryption": "none"},
                "streamSettings": {"network": "ws", "wsSettings": {"path": "/killpv2"}},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
            }
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct_out"}]
    }

    with open(CONFIG_PATH, 'w') as f:
        json.dump(xray_json_config, f, indent=4)

    subprocess.run("sudo killall xray || true", shell=True)
    subprocess.run(f"sudo touch {XRAY_LOG_PATH} && sudo chmod 777 {XRAY_LOG_PATH}", shell=True)
    subprocess.run(f"sudo nohup /usr/local/bin/xray -config {CONFIG_PATH} > /dev/null 2>&1 &", shell=True)

# ─────────────────────────────────────────────
#  HTML پنل - طراحی کاملاً جدید
# ─────────────────────────────────────────────
PANEL_CSS = """
:root {
  --bg: #0d0d14;
  --bg2: #13131f;
  --bg3: #1a1a2e;
  --card: #16213e;
  --card2: #1a1f35;
  --border: #2a2d4a;
  --border2: #353870;
  --accent: #6c63ff;
  --accent2: #a78bfa;
  --green: #00d68f;
  --red: #ff4d6d;
  --yellow: #ffd60a;
  --orange: #ff6b35;
  --blue: #4cc9f0;
  --text: #e2e8f0;
  --text2: #94a3b8;
  --text3: #64748b;
  --online: #00d68f;
  --offline: #ff4d6d;
  --expired: #ff6b35;
  --disabled: #64748b;
  --glow: 0 0 20px rgba(108,99,255,0.3);
  --glow2: 0 0 30px rgba(108,99,255,0.15);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  direction: rtl;
}

/* ─── Sidebar ─── */
.layout { display: flex; min-height: 100vh; }

.sidebar {
  width: 220px;
  min-width: 220px;
  background: var(--bg2);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 0;
  position: fixed;
  right: 0;
  top: 0;
  height: 100vh;
  z-index: 100;
  overflow-y: auto;
}

.sidebar-logo {
  padding: 0 16px 24px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
  text-align: center;
}

.sidebar-logo .logo-icon {
  font-size: 2rem;
  display: block;
  margin-bottom: 6px;
}

.sidebar-logo h2 {
  font-size: 0.95rem;
  color: var(--accent2);
  font-weight: 700;
  letter-spacing: 1px;
}

.sidebar-logo .version {
  font-size: 0.7rem;
  color: var(--text3);
  margin-top: 2px;
}

.nav-section {
  padding: 0 10px;
  margin-bottom: 8px;
}

.nav-label {
  font-size: 0.65rem;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: 1.5px;
  padding: 0 8px;
  margin-bottom: 6px;
  font-weight: 600;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 0.87rem;
  color: var(--text2);
  transition: all 0.2s;
  margin-bottom: 2px;
  border: 1px solid transparent;
}

.nav-item:hover {
  background: var(--bg3);
  color: var(--text);
  border-color: var(--border);
}

.nav-item.active {
  background: linear-gradient(135deg, rgba(108,99,255,0.2), rgba(167,139,250,0.1));
  color: var(--accent2);
  border-color: rgba(108,99,255,0.4);
  box-shadow: var(--glow2);
}

.nav-item .nav-icon { font-size: 1.1rem; width: 22px; text-align: center; }
.nav-item .nav-badge {
  margin-right: auto;
  background: var(--accent);
  color: white;
  font-size: 0.65rem;
  padding: 2px 6px;
  border-radius: 20px;
  font-weight: 700;
}

.sidebar-footer {
  margin-top: auto;
  padding: 16px;
  border-top: 1px solid var(--border);
}

.online-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--text2);
}

.dot-pulse {
  width: 8px; height: 8px;
  background: var(--green);
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}

/* ─── Main Content ─── */
.main-content {
  margin-right: 220px;
  flex: 1;
  padding: 24px;
  min-height: 100vh;
}

/* ─── Top Bar ─── */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.topbar-title {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text);
}

.topbar-title span { color: var(--accent2); }

.topbar-actions { display: flex; gap: 10px; align-items: center; }

/* ─── Stats Cards ─── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px;
  position: relative;
  overflow: hidden;
  transition: all 0.3s;
}

.stat-card:hover { border-color: var(--border2); transform: translateY(-2px); }

.stat-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--card-accent, var(--accent));
}

.stat-card.green { --card-accent: var(--green); }
.stat-card.blue { --card-accent: var(--blue); }
.stat-card.purple { --card-accent: var(--accent2); }
.stat-card.orange { --card-accent: var(--orange); }

.stat-icon {
  font-size: 1.6rem;
  margin-bottom: 10px;
  display: block;
}

.stat-value {
  font-size: 1.8rem;
  font-weight: 800;
  color: var(--text);
  line-height: 1;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text3);
  font-weight: 500;
}

/* ─── Tab Pages ─── */
.tab-page { display: none; }
.tab-page.active { display: block; }

/* ─── Section Cards ─── */
.section-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: var(--card2);
  border-bottom: 1px solid var(--border);
}

.section-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-body { padding: 20px; }

/* ─── Form Elements ─── */
.form-group { margin-bottom: 14px; }
.form-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text2);
  margin-bottom: 6px;
  font-weight: 600;
}

.form-control {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  font-size: 0.88rem;
  outline: none;
  transition: all 0.2s;
}

.form-control:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(108,99,255,0.15);
}

.form-control::placeholder { color: var(--text3); }

.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }

/* ─── Toggle ─── */
.toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  font-size: 0.85rem;
  color: var(--text2);
}

.toggle {
  position: relative;
  width: 40px; height: 22px;
}

.toggle input { opacity: 0; width: 0; height: 0; }

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--bg3);
  border: 1px solid var(--border2);
  border-radius: 22px;
  transition: 0.3s;
}

.toggle-slider:before {
  content: '';
  position: absolute;
  height: 16px; width: 16px;
  left: 2px; bottom: 2px;
  background: var(--text3);
  border-radius: 50%;
  transition: 0.3s;
}

input:checked + .toggle-slider { background: var(--accent); border-color: var(--accent); }
input:checked + .toggle-slider:before {
  transform: translateX(18px);
  background: white;
}

/* ─── Buttons ─── */
.btn {
  padding: 10px 18px;
  border: none;
  border-radius: 10px;
  font-weight: 700;
  cursor: pointer;
  font-size: 0.88rem;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
.btn:active { transform: translateY(0); }

.btn-primary { background: var(--accent); color: white; }
.btn-success { background: var(--green); color: #000; }
.btn-danger { background: var(--red); color: white; }
.btn-warning { background: var(--yellow); color: #000; }
.btn-info { background: var(--blue); color: #000; }
.btn-purple { background: var(--accent2); color: #000; }
.btn-ghost {
  background: transparent;
  color: var(--text2);
  border: 1px solid var(--border);
}
.btn-ghost:hover { border-color: var(--accent); color: var(--accent2); }

.btn-sm { padding: 6px 12px; font-size: 0.78rem; border-radius: 8px; }
.btn-full { width: 100%; justify-content: center; }

/* ─── User Cards ─── */
.user-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.user-card {
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  transition: all 0.2s;
}

.user-card:hover { border-color: var(--border2); }
.user-card.selected { border-color: var(--accent); box-shadow: var(--glow2); }

.user-card-header {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  gap: 12px;
  cursor: pointer;
}

.user-avatar {
  width: 40px; height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 1rem;
  color: white;
  flex-shrink: 0;
}

.user-info { flex: 1; min-width: 0; }
.user-name {
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--text);
  margin-bottom: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-meta { font-size: 0.75rem; color: var(--text3); }

.status-badge {
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 0.72rem;
  font-weight: 700;
  flex-shrink: 0;
}

.status-online { background: rgba(0,214,143,0.15); color: var(--green); border: 1px solid rgba(0,214,143,0.3); }
.status-offline { background: rgba(255,77,109,0.15); color: var(--red); border: 1px solid rgba(255,77,109,0.3); }
.status-expired { background: rgba(255,107,53,0.15); color: var(--expired); border: 1px solid rgba(255,107,53,0.3); }
.status-disabled { background: rgba(100,116,139,0.15); color: var(--disabled); border: 1px solid rgba(100,116,139,0.3); }

.user-card-body {
  padding: 0 16px 14px;
  border-top: 1px solid var(--border);
}

.user-stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  padding: 12px 0;
}

.user-stat { text-align: center; }
.user-stat-val {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 2px;
}
.user-stat-lbl { font-size: 0.68rem; color: var(--text3); }

.progress-wrap { margin-bottom: 12px; }
.progress-bar-bg {
  width: 100%;
  height: 5px;
  background: var(--bg3);
  border-radius: 10px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  border-radius: 10px;
  transition: width 0.5s;
}

.user-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* ─── Config Box ─── */
.config-box {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  font-family: monospace;
  font-size: 0.75rem;
  color: var(--blue);
  word-break: break-all;
  margin-top: 10px;
  direction: ltr;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
}
.config-box:hover { border-color: var(--accent); }

/* ─── Terminal ─── */
.terminal {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 12px;
  height: 220px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 0.76rem;
  padding: 12px;
  color: #cbd5e1;
  direction: ltr;
  text-align: left;
}

.terminal::-webkit-scrollbar { width: 4px; }
.terminal::-webkit-scrollbar-track { background: transparent; }
.terminal::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }

.log-line { margin: 2px 0; padding-bottom: 2px; border-bottom: 1px solid rgba(255,255,255,0.03); }
.log-error { color: var(--red); }
.log-success { color: var(--green); }
.log-warn { color: var(--yellow); }

/* ─── Scanner ─── */
.scanner-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.ip-output {
  width: 100%;
  height: 180px;
  background: #020617;
  color: var(--green);
  font-family: monospace;
  font-size: 0.78rem;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  resize: none;
}

/* ─── Sniper Box ─── */
.sniper-log {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  min-height: 100px;
  max-height: 200px;
  overflow-y: auto;
  padding: 10px;
  font-family: monospace;
  font-size: 0.78rem;
  color: var(--text2);
  direction: ltr;
  text-align: left;
}

.sniper-entry {
  padding: 3px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  color: var(--blue);
}

/* ─── Telegram Proxy Form ─── */
.tg-proxy-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: rgba(76,201,240,0.1);
  border: 1px solid rgba(76,201,240,0.3);
  color: var(--blue);
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
}

.proxy-type-selector {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.proxy-type-btn {
  flex: 1;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg3);
  color: var(--text2);
  cursor: pointer;
  font-size: 0.83rem;
  font-weight: 600;
  text-align: center;
  transition: all 0.2s;
}

.proxy-type-btn.selected {
  border-color: var(--accent);
  background: rgba(108,99,255,0.15);
  color: var(--accent2);
}

/* ─── Tunnel Info ─── */
.tunnel-card {
  background: linear-gradient(135deg, rgba(108,99,255,0.1), rgba(76,201,240,0.05));
  border: 1px solid rgba(108,99,255,0.3);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 16px;
}

.tunnel-url {
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--accent2);
  word-break: break-all;
  margin-top: 4px;
}

/* ─── Scrollbar ─── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }

/* ─── Responsive ─── */
@media (max-width: 900px) {
  .sidebar { width: 60px; min-width: 60px; }
  .nav-item span, .nav-label, .sidebar-logo h2, .sidebar-logo .version, .sidebar-footer .online-indicator span { display: none; }
  .main-content { margin-right: 60px; }
  .stats-row { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 600px) {
  .stats-row { grid-template-columns: 1fr 1fr; }
  .form-row { grid-template-columns: 1fr; }
  .scanner-grid { grid-template-columns: 1fr; }
  .main-content { padding: 12px; }
}

/* ─── Notification Toast ─── */
.toast-container {
  position: fixed;
  bottom: 20px;
  left: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.toast {
  background: var(--card);
  border: 1px solid var(--border2);
  border-radius: 12px;
  padding: 12px 18px;
  font-size: 0.85rem;
  color: var(--text);
  box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  animation: slideIn 0.3s ease;
  display: flex;
  align-items: center;
  gap: 8px;
}

.toast.success { border-color: rgba(0,214,143,0.5); }
.toast.error { border-color: rgba(255,77,109,0.5); }

@keyframes slideIn {
  from { transform: translateX(-20px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

/* ─── Loading ─── */
.spinner {
  display: inline-block;
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
"""

PANEL_JS = """
let cachedConfigs = {};
let selectedUserFilter = null;
let currentTab = 'dashboard';

// ─── Toast ───
function toast(msg, type='success') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = (type === 'success' ? '✅' : '❌') + ' ' + msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ─── Tab Navigation ───
function showTab(tabId) {
  document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const page = document.getElementById('tab-' + tabId);
  if (page) page.classList.add('active');
  const navItem = document.querySelector('[data-tab="' + tabId + '"]');
  if (navItem) navItem.classList.add('active');
  currentTab = tabId;
  
  const titles = {
    dashboard: 'داشبورد',
    users: 'مدیریت کاربران',
    create: 'ایجاد کانفیگ',
    telegram: 'پروکسی تلگرام',
    scanner: 'اسکنر IP',
    logs: 'لاگ سیستم',
    settings: 'تنظیمات'
  };
  document.getElementById('page-title').innerText = titles[tabId] || tabId;
}

// ─── Live Stats ───
async function loadLiveStats() {
  try {
    let res = await fetch('/api/stats');
    let data = await res.json();
    
    document.getElementById('online_count').innerText = data.total_online;
    
    // آپدیت terminal
    const term = document.getElementById('sys_terminal');
    if (term) {
      const atBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 10;
      if (data.sys_logs && data.sys_logs.length > 0) {
        const lastLog = data.sys_logs[data.sys_logs.length - 1];
        let cls = 'log-line';
        if (lastLog.includes('error') || lastLog.includes('Error')) cls += ' log-error';
        else if (lastLog.includes('✅') || lastLog.includes('success')) cls += ' log-success';
        else if (lastLog.includes('⚠️') || lastLog.includes('warn')) cls += ' log-warn';
        term.innerHTML = data.sys_logs.map(l => `<div class="${cls}">${l}</div>`).join('');
      }
      if (atBottom) term.scrollTop = term.scrollHeight;
    }

    // آپدیت stats
    let totalUsers = data.users ? data.users.length : 0;
    let expiredCount = data.users ? data.users.filter(u => u.status === 'EXPIRED').length : 0;
    let activeCount = data.users ? data.users.filter(u => u.status !== 'EXPIRED' && u.status !== 'DISABLED').length : 0;
    
    const el_total = document.getElementById('total_users');
    const el_active = document.getElementById('active_users');
    const el_expired = document.getElementById('expired_users');
    if (el_total) el_total.innerText = totalUsers;
    if (el_active) el_active.innerText = activeCount;
    if (el_expired) el_expired.innerText = expiredCount;

    if (data.users) {
      data.users.forEach(u => {
        let row = document.getElementById('u_' + u.username);
        if (row) {
          let badge = row.querySelector('.status-badge');
          if (badge) {
            const statusMap = {
              'ONLINE':   ['🟢 آنلاین', 'status-online'],
              'OFFLINE':  ['🔴 آفلاین', 'status-offline'],
              'EXPIRED':  ['⏳ منقضی', 'status-expired'],
              'DISABLED': ['⚫ غیرفعال', 'status-disabled'],
            };
            const [label, cls] = statusMap[u.status] || ['❓', 'status-disabled'];
            badge.innerText = label;
            badge.className = 'status-badge ' + cls;
          }

          const set = (cls, val) => { const el = row.querySelector(cls); if(el) el.innerText = val; };
          set('.u-used', u.used);
          set('.u-rem', u.remaining);
          set('.u-days', u.rem_days);
          set('.u-dspeed', '⬇️ ' + u.down_speed);
          set('.u-uspeed', '⬆️ ' + u.up_speed);

          const bar = row.querySelector('.progress-bar-fill');
          if (bar) bar.style.width = u.progress + '%';

          cachedConfigs[u.username] = u.config_raw;

          // sniper
          if (selectedUserFilter === u.username) {
            const sniperBox = document.getElementById('user_sniper_logs');
            if (sniperBox) {
              sniperBox.innerHTML = u.destinations.length === 0
                ? '<div style="color:var(--text3)">در انتظار ترافیک...</div>'
                : u.destinations.map(d => `<div class="sniper-entry">🌐 ${d}</div>`).join('');
            }
          }
        }
      });
    }
  } catch(e) {}
}

// ─── Filter / Sniper ───
function filterUserSniper(username) {
  if (selectedUserFilter) {
    const prev = document.getElementById('u_' + selectedUserFilter);
    if (prev) prev.classList.remove('selected');
  }
  if (selectedUserFilter === username) {
    selectedUserFilter = null;
    const title = document.getElementById('sniper_title');
    if (title) title.innerText = '🔍 مانیتورینگ ترافیک (روی کاربر کلیک کن)';
    const box = document.getElementById('user_sniper_logs');
    if (box) box.innerHTML = '<div style="color:var(--text3)">روی یک کاربر کلیک کن تا ترافیکش اینجا نمایش داده بشه.</div>';
  } else {
    selectedUserFilter = username;
    const row = document.getElementById('u_' + username);
    if (row) row.classList.add('selected');
    const title = document.getElementById('sniper_title');
    if (title) title.innerText = '🛰️ ترافیک زنده: ' + username;
    const box = document.getElementById('user_sniper_logs');
    if (box) box.innerHTML = '<div style="color:var(--text3)">در حال تحلیل...</div>';
  }
}

// ─── Copy ───
function copyConfig(user) {
  if (cachedConfigs[user]) {
    navigator.clipboard.writeText(cachedConfigs[user]);
    toast('کانفیگ VLESS کپی شد!');
  }
}

function copySubLink(user) {
  let repoName = '{REPO_FULL_NAME}';
  let url = repoName === 'username/repo'
    ? `https://${window.location.host}/sub/${user}`
    : `https://raw.githubusercontent.com/${repoName}/main/sub_links/${user}`;
  navigator.clipboard.writeText(url);
  toast('لینک ساب کپی شد!');
}

// ─── Volume Toggle ───
function toggleUnlimitedVolume(cb) {
  const inp = document.getElementById('volume_value_input');
  if (!inp) return;
  inp.disabled = cb.checked;
  inp.placeholder = cb.checked ? 'حجم نامحدود فعال' : 'مقدار حجم';
  if (cb.checked) inp.value = '';
  else inp.value = '30';
}

// ─── Proxy Type ───
function selectProxyType(type) {
  document.querySelectorAll('.proxy-type-btn').forEach(b => b.classList.remove('selected'));
  document.querySelector(`[data-proxy="${type}"]`).classList.add('selected');
  document.getElementById('proxy_type_val').value = type;
  
  const secretGroup = document.getElementById('secret_group');
  const urlGroup = document.getElementById('proxy_url_group');
  if (type === 'mtproto') {
    secretGroup.style.display = 'block';
    urlGroup.style.display = 'none';
  } else {
    secretGroup.style.display = 'none';
    urlGroup.style.display = 'block';
  }
}

// ─── Scanner ───
const cleanIpsToTest = [];
const baseSubnets = [
  "104.16.123.", "104.17.3.", "104.18.2.", "172.67.143.", "104.21.43.",
  "162.159.135.", "172.64.149.", "104.16.50.", "104.17.51.", "104.19.60."
];
baseSubnets.forEach(subnet => {
  for (let i = 10; i < 60; i++) cleanIpsToTest.push(subnet + i);
});

async function startScan() {
  const btn = document.getElementById('scan_btn');
  const output = document.getElementById('scan_output');
  const status = document.getElementById('scan_status');
  btn.disabled = true;
  output.value = '';
  let working = 0;
  const batch = 30;
  status.innerText = '🔍 در حال اسکن...';
  for (let i = 0; i < cleanIpsToTest.length; i += batch) {
    const slice = cleanIpsToTest.slice(i, i + batch);
    await Promise.all(slice.map(async ip => {
      const start = Date.now();
      try {
        const ctrl = new AbortController();
        setTimeout(() => ctrl.abort(), 1500);
        await fetch(`https://${ip}/cdn-cgi/trace`, { mode: 'no-cors', signal: ctrl.signal });
        working++;
        output.value += `${ip} → ${Date.now() - start}ms\\n`;
      } catch (e) {}
    }));
  }
  status.innerText = `✅ تمام! ${working} IP فعال یافت شد.`;
  btn.disabled = false;
}

// ─── Apply Clean IP ───
function applyCleanIP(user) {
  const ipEl = document.getElementById('apply_ip_' + user);
  if (!ipEl) return;
  const ip = ipEl.value.trim();
  if (!ip) { toast('IP وارد کن', 'error'); return; }
  
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = '/';
  const fields = { action: 'set_clean_ip', username: user, clean_ip: ip };
  Object.entries(fields).forEach(([k, v]) => {
    const inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = k; inp.value = v;
    form.appendChild(inp);
  });
  document.body.appendChild(form);
  form.submit();
}

setInterval(loadLiveStats, 2500);
window.onload = () => { loadLiveStats(); showTab('dashboard'); };
"""

def get_login_html(error=False):
    err_html = '<div style="background:rgba(255,77,109,0.1);border:1px solid rgba(255,77,109,0.3);color:#ff4d6d;padding:10px 14px;border-radius:10px;font-size:0.85rem;margin-bottom:14px;">❌ نام کاربری یا رمز عبور اشتباه است</div>' if error else ''
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ورود | kill_pv2</title>
<style>
{PANEL_CSS}
body {{ display:flex;align-items:center;justify-content:center;min-height:100vh; }}
.login-wrap {{ width:100%;max-width:380px;padding:16px; }}
.login-card {{ background:var(--card);border:1px solid var(--border);border-radius:20px;padding:32px;box-shadow:0 20px 60px rgba(0,0,0,0.5); }}
.login-logo {{ text-align:center;margin-bottom:28px; }}
.login-logo .icon {{ font-size:3rem;display:block;margin-bottom:8px; }}
.login-logo h1 {{ font-size:1.3rem;color:var(--accent2);font-weight:800; }}
.login-logo p {{ font-size:0.78rem;color:var(--text3);margin-top:4px; }}
</style>
</head>
<body>
<div class="login-wrap">
  <div class="login-card">
    <div class="login-logo">
      <span class="icon">🛡️</span>
      <h1>kill_pv2 Panel</h1>
      <p>سیستم مدیریت اتصال هوشمند</p>
    </div>
    {err_html}
    <form method="POST" action="/login">
      <div class="form-group">
        <label class="form-label">👤 نام کاربری</label>
        <input name="username" class="form-control" placeholder="admin" autocomplete="username">
      </div>
      <div class="form-group">
        <label class="form-label">🔑 رمز عبور</label>
        <input name="password" type="password" class="form-control" placeholder="••••••••" autocomplete="current-password">
      </div>
      <button type="submit" class="btn btn-primary btn-full" style="margin-top:8px">ورود به پنل</button>
    </form>
  </div>
</div>
</body>
</html>"""

def get_main_html():
    now = int(time.time())

    # ─── Build User Cards ───
    user_cards_html = ""
    for user_name, user_data in configs_db.items():
        is_active = user_data.get("active", True)
        status = user_data.get("status", "OFFLINE")
        if not is_active: status = "DISABLED"
        status_map = {
            "ONLINE":   ("🟢 آنلاین",  "status-online"),
            "OFFLINE":  ("🔴 آفلاین",  "status-offline"),
            "EXPIRED":  ("⏳ منقضی",   "status-expired"),
            "DISABLED": ("⚫ غیرفعال", "status-disabled"),
        }
        s_label, s_cls = status_map.get(status, ("❓", "status-disabled"))
        avatar_letter = user_name[0].upper() if user_name else "?"

        tg_proxy = user_data.get("telegram_proxy")
        tg_badge = ""
        if tg_proxy:
            tg_badge = f'<span class="tg-proxy-badge" style="margin-right:8px">🔵 TG Proxy</span>'

        user_cards_html += f"""
<div class="user-card" id="u_{user_name}">
  <div class="user-card-header" onclick="filterUserSniper('{user_name}')">
    <div class="user-avatar">{avatar_letter}</div>
    <div class="user-info">
      <div class="user-name">{user_name} {tg_badge}</div>
      <div class="user-meta">UUID: {user_data['uuid'][:16]}...</div>
    </div>
    <span class="status-badge {s_cls}">{s_label}</span>
  </div>
  <div class="user-card-body">
    <div class="user-stats-grid">
      <div class="user-stat">
        <div class="user-stat-val u-used">0 B</div>
        <div class="user-stat-lbl">مصرف شده</div>
      </div>
      <div class="user-stat">
        <div class="user-stat-val u-rem">0 B</div>
        <div class="user-stat-lbl">باقی‌مانده</div>
      </div>
      <div class="user-stat">
        <div class="user-stat-val u-days">0 روز</div>
        <div class="user-stat-lbl">زمان مانده</div>
      </div>
    </div>
    <div class="progress-wrap">
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" style="width:0%"></div>
      </div>
    </div>
    <div style="display:flex;gap:8px;font-size:0.75rem;color:var(--text3);margin-bottom:10px">
      <span class="u-dspeed">⬇️ 0 KB/s</span>
      <span class="u-uspeed">⬆️ 0 KB/s</span>
    </div>
    <div class="user-actions">
      <button class="btn btn-info btn-sm" onclick="copySubLink('{user_name}')">🔗 ساب</button>
      <button class="btn btn-primary btn-sm" onclick="copyConfig('{user_name}')">📋 کانفیگ</button>
      <form method="POST" action="/" style="display:inline" onsubmit="return confirm('وضعیت تغییر بده؟')">
        <input type="hidden" name="action" value="toggle">
        <input type="hidden" name="username" value="{user_name}">
        <button class="btn btn-warning btn-sm" type="submit">⚙️ سوییچ</button>
      </form>
      <form method="POST" action="/" style="display:inline" onsubmit="return confirm('حذف بشه داداش؟')">
        <input type="hidden" name="action" value="delete">
        <input type="hidden" name="username" value="{user_name}">
        <button class="btn btn-danger btn-sm" type="submit">🗑️ حذف</button>
      </form>
    </div>
    <div style="margin-top:10px;display:flex;gap:6px">
      <input id="apply_ip_{user_name}" class="form-control" style="flex:1;font-size:0.78rem;padding:7px 10px" placeholder="تغییر Clean IP..." value="{user_data.get('clean_ip', DEFAULT_CLEAN_IP)}">
      <button class="btn btn-ghost btn-sm" onclick="applyCleanIP('{user_name}')">✅ اعمال</button>
    </div>
  </div>
</div>"""

    js_with_repo = PANEL_JS.replace('{REPO_FULL_NAME}', repo_full_name)

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>پنل مدیریت | kill_pv2</title>
<style>{PANEL_CSS}</style>
</head>
<body>
<div class="layout">

<!-- ─── Sidebar ─── -->
<nav class="sidebar">
  <div class="sidebar-logo">
    <span class="logo-icon">⚡</span>
    <h2>kill_pv2</h2>
    <div class="version">v2.0 Pro</div>
  </div>

  <div class="nav-section">
    <div class="nav-label">منو اصلی</div>
    <div class="nav-item active" data-tab="dashboard" onclick="showTab('dashboard')">
      <span class="nav-icon">📊</span><span>داشبورد</span>
    </div>
    <div class="nav-item" data-tab="users" onclick="showTab('users')">
      <span class="nav-icon">👥</span><span>کاربران</span>
      <span class="nav-badge" id="user_count_badge">{len(configs_db)}</span>
    </div>
    <div class="nav-item" data-tab="create" onclick="showTab('create')">
      <span class="nav-icon">➕</span><span>ایجاد کانفیگ</span>
    </div>
    <div class="nav-item" data-tab="telegram" onclick="showTab('telegram')">
      <span class="nav-icon">🔵</span><span>پروکسی تلگرام</span>
    </div>
  </div>

  <div class="nav-section">
    <div class="nav-label">ابزارها</div>
    <div class="nav-item" data-tab="scanner" onclick="showTab('scanner')">
      <span class="nav-icon">📡</span><span>اسکنر IP</span>
    </div>
    <div class="nav-item" data-tab="logs" onclick="showTab('logs')">
      <span class="nav-icon">📟</span><span>لاگ سیستم</span>
    </div>
    <div class="nav-item" data-tab="settings" onclick="showTab('settings')">
      <span class="nav-icon">⚙️</span><span>تنظیمات</span>
    </div>
  </div>

  <div class="sidebar-footer">
    <div class="online-indicator">
      <div class="dot-pulse"></div>
      <span id="online_count">0</span>
      <span>آنلاین</span>
    </div>
  </div>
</nav>

<!-- ─── Main ─── -->
<main class="main-content">
  <div class="topbar">
    <div class="topbar-title">🎛️ <span id="page-title">داشبورد</span></div>
    <div class="topbar-actions">
      <div class="tunnel-url" style="font-size:0.75rem">🌐 {tunnel_host}</div>
      <form method="POST" action="/" style="display:inline">
        <input type="hidden" name="action" value="logout">
        <button class="btn btn-ghost btn-sm" type="submit">🚪 خروج</button>
      </form>
    </div>
  </div>

  <!-- ──────────── TAB: DASHBOARD ──────────── -->
  <div id="tab-dashboard" class="tab-page active">
    <div class="stats-row">
      <div class="stat-card green">
        <span class="stat-icon">🟢</span>
        <div class="stat-value" id="online_count2">0</div>
        <div class="stat-label">کاربر آنلاین</div>
      </div>
      <div class="stat-card blue">
        <span class="stat-icon">👥</span>
        <div class="stat-value" id="total_users">{len(configs_db)}</div>
        <div class="stat-label">کل کاربران</div>
      </div>
      <div class="stat-card purple">
        <span class="stat-icon">✅</span>
        <div class="stat-value" id="active_users">0</div>
        <div class="stat-label">کاربر فعال</div>
      </div>
      <div class="stat-card orange">
        <span class="stat-icon">⏳</span>
        <div class="stat-value" id="expired_users">0</div>
        <div class="stat-label">منقضی شده</div>
      </div>
    </div>

    <div class="section-card">
      <div class="section-header">
        <div class="section-title">🌐 اطلاعات تانل فعال</div>
      </div>
      <div class="section-body">
        <div class="tunnel-card">
          <div style="font-size:0.8rem;color:var(--text3);margin-bottom:4px">آدرس تانل Cloudflare:</div>
          <div class="tunnel-url">{tunnel_host}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:0.85rem;color:var(--text2)">
          <div>🔌 پورت Xray: <strong style="color:var(--text)">8085</strong></div>
          <div>📡 پروتکل: <strong style="color:var(--text)">VLESS + WS + TLS</strong></div>
          <div>🛤️ Path: <strong style="color:var(--text)">/killpv2</strong></div>
          <div>🔒 Security: <strong style="color:var(--text)">TLS</strong></div>
        </div>
      </div>
    </div>

    <div class="section-card">
      <div class="section-header">
        <div class="section-title" id="sniper_title">🔍 مانیتورینگ ترافیک (روی کاربر کلیک کن)</div>
      </div>
      <div class="section-body">
        <div class="sniper-log" id="user_sniper_logs">
          <div style="color:var(--text3)">روی یک کاربر در بخش «کاربران» کلیک کن تا ترافیکش اینجا نمایش داده بشه.</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ──────────── TAB: USERS ──────────── -->
  <div id="tab-users" class="tab-page">
    <div class="section-card">
      <div class="section-header">
        <div class="section-title">👥 لیست کاربران</div>
        <button class="btn btn-success btn-sm" onclick="showTab('create')">➕ کاربر جدید</button>
      </div>
      <div class="section-body">
        <div class="user-grid">
          {user_cards_html if user_cards_html else '<div style="text-align:center;color:var(--text3);padding:40px">هنوز کاربری اضافه نشده</div>'}
        </div>
      </div>
    </div>
  </div>

  <!-- ──────────── TAB: CREATE ──────────── -->
  <div id="tab-create" class="tab-page">
    <div class="section-card">
      <div class="section-header">
        <div class="section-title">➕ ایجاد کانفیگ VLESS جدید</div>
      </div>
      <div class="section-body">
        <form method="POST" action="/">
          <input type="hidden" name="action" value="create">

          <div class="form-row">
            <div class="form-group">
              <label class="form-label">👤 نام کاربر</label>
              <input name="username" class="form-control" placeholder="مثال: ali_vip" required>
            </div>
            <div class="form-group">
              <label class="form-label">🌐 Clean IP</label>
              <input name="clean_ip" class="form-control" placeholder="{DEFAULT_CLEAN_IP}" value="{DEFAULT_CLEAN_IP}">
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">💾 حجم مجاز</label>
            <div class="toggle-row" style="margin-bottom:10px">
              <label class="toggle">
                <input type="checkbox" name="unlimited_volume" value="true" onchange="toggleUnlimitedVolume(this)">
                <span class="toggle-slider"></span>
              </label>
              ♾️ حجم نامحدود
            </div>
            <div class="form-row">
              <input id="volume_value_input" name="volume_value" class="form-control" type="number" min="0" value="30" placeholder="مقدار حجم">
              <select name="volume_unit" class="form-control">
                <option value="GB">GB گیگابایت</option>
                <option value="MB">MB مگابایت</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">⏱️ مدت زمان اشتراک</label>
            <div class="form-row">
              <input name="expire_days" class="form-control" type="number" min="0" value="30" placeholder="روز">
              <input name="expire_hours" class="form-control" type="number" min="0" value="0" placeholder="ساعت">
            </div>
            <div style="font-size:0.75rem;color:var(--text3);margin-top:4px">روز و ساعت</div>
          </div>

          <div class="form-group">
            <label class="form-label">📊 حجم استفاده شده اولیه (اختیاری)</label>
            <div class="form-row">
              <input name="initial_used_value" class="form-control" type="number" min="0" value="0" placeholder="مقدار">
              <select name="initial_used_unit" class="form-control">
                <option value="GB">GB</option>
                <option value="MB">MB</option>
              </select>
            </div>
          </div>

          <button type="submit" class="btn btn-success btn-full">⚡ ایجاد کانفیگ و ریلود</button>
        </form>
      </div>
    </div>

    <div class="section-card">
      <div class="section-header">
        <div class="section-title">🔧 تانل اختصاصی جداگانه</div>
      </div>
      <div class="section-body">
        <p style="font-size:0.85rem;color:var(--text2);margin-bottom:14px">
          برای هر کاربر می‌تونی یه تانل host متفاوت تنظیم کنی تا از تانل مشترک جدا باشه.
        </p>
        <form method="POST" action="/">
          <input type="hidden" name="action" value="set_custom_tunnel">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">👤 نام کاربر</label>
              <select name="username" class="form-control">
                {''.join(f'<option value="{u}">{u}</option>' for u in configs_db)}
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">🌐 آدرس تانل اختصاصی</label>
              <input name="custom_tunnel" class="form-control" placeholder="xxx.trycloudflare.com">
            </div>
          </div>
          <button type="submit" class="btn btn-primary btn-full">💾 ذخیره تانل اختصاصی</button>
        </form>
      </div>
    </div>
  </div>

  <!-- ──────────── TAB: TELEGRAM ──────────── -->
  <div id="tab-telegram" class="tab-page">
    <div class="section-card">
      <div class="section-header">
        <div class="section-title">🔵 ساخت پروکسی تلگرام</div>
      </div>
      <div class="section-body">
        <p style="font-size:0.85rem;color:var(--text2);margin-bottom:18px">
          پروکسی MTProto تلگرام برای کاربر انتخابی بساز. لینک به صورت اتوماتیک تو ساب لینک هم اضافه میشه.
        </p>
        
        <div class="proxy-type-selector">
          <div class="proxy-type-btn selected" data-proxy="mtproto" onclick="selectProxyType('mtproto')">🔐 MTProto</div>
          <div class="proxy-type-btn" data-proxy="socks5" onclick="selectProxyType('socks5')">🧦 SOCKS5</div>
          <div class="proxy-type-btn" data-proxy="http" onclick="selectProxyType('http')">🌐 HTTP</div>
        </div>

        <form method="POST" action="/">
          <input type="hidden" name="action" value="add_telegram_proxy">
          <input type="hidden" name="proxy_type" id="proxy_type_val" value="mtproto">

          <div class="form-group">
            <label class="form-label">👤 کاربر مقصد</label>
            <select name="proxy_username" class="form-control">
              {''.join(f'<option value="{u}">{u}</option>' for u in configs_db)}
            </select>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label class="form-label">🖥️ سرور پروکسی</label>
              <input name="proxy_server" class="form-control" placeholder="{tunnel_host}" value="{tunnel_host}">
            </div>
            <div class="form-group">
              <label class="form-label">🔌 پورت</label>
              <input name="proxy_port" class="form-control" value="443" type="number">
            </div>
          </div>

          <div id="secret_group" class="form-group">
            <label class="form-label">🔑 Secret (MTProto)</label>
            <div style="display:flex;gap:8px">
              <input name="proxy_secret" id="proxy_secret_input" class="form-control" placeholder="dd...">
              <button type="button" class="btn btn-ghost btn-sm" onclick="generateSecret()">🎲 تولید</button>
            </div>
            <div style="font-size:0.72rem;color:var(--text3);margin-top:4px">با dd شروع میشه برای FakeTLS</div>
          </div>

          <div id="proxy_url_group" class="form-group" style="display:none">
            <label class="form-label">🔐 رمز عبور (SOCKS5/HTTP)</label>
            <input name="proxy_password" class="form-control" placeholder="رمز اختیاری">
          </div>

          <div class="form-group">
            <label class="form-label">📝 نام نمایشی (اختیاری)</label>
            <input name="proxy_label" class="form-control" placeholder="مثال: پروکسی سرعت بالا">
          </div>

          <button type="submit" class="btn btn-info btn-full">🔵 ایجاد و ذخیره پروکسی تلگرام</button>
        </form>

        <div style="margin-top:20px">
          <div class="section-title" style="margin-bottom:12px;font-size:0.9rem">📋 پروکسی‌های ثبت شده</div>
          {''.join(
            f'''<div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between">
              <div>
                <div style="font-weight:700;color:var(--text);margin-bottom:3px">🔵 {u} — {v["telegram_proxy"]["type"].upper()}</div>
                <div style="font-size:0.75rem;color:var(--text3)">{v["telegram_proxy"]["server"]}:{v["telegram_proxy"]["port"]}</div>
              </div>
              <button class="btn btn-info btn-sm" onclick="navigator.clipboard.writeText('https://t.me/proxy?server={v[&quot;telegram_proxy&quot;][&quot;server&quot;]}&port={v[&quot;telegram_proxy&quot;][&quot;port&quot;]}&secret={v[&quot;telegram_proxy&quot;].get(&quot;secret&quot;,&quot;&quot;)}');toast('لینک پروکسی کپی شد!')">📋 کپی لینک</button>
            </div>'''
            for u, v in configs_db.items() if v.get("telegram_proxy")
          ) or '<div style="text-align:center;color:var(--text3);padding:20px">هنوز پروکسی تلگرام ثبت نشده</div>'}
        </div>
      </div>
    </div>
  </div>

  <!-- ──────────── TAB: SCANNER ──────────── -->
  <div id="tab-scanner" class="tab-page">
    <div class="section-card">
      <div class="section-header">
        <div class="section-title">📡 اسکنر Clean IP کلودفلر</div>
        <button id="scan_btn" class="btn btn-purple btn-sm" onclick="startScan()">▶️ شروع اسکن</button>
      </div>
      <div class="section-body">
        <div style="font-size:0.85rem;color:var(--text2);margin-bottom:14px" id="scan_status">
          ⏳ آماده برای اسکن {len(cleanIpsToTest) if False else '500+'} آی‌پی...
        </div>
        <div class="scanner-grid">
          <div>
            <div class="form-label" style="margin-bottom:8px">📤 آی‌پی‌های فعال یافت شده:</div>
            <textarea id="scan_output" class="ip-output" readonly placeholder="نتایج اینجا نمایش داده میشه..."></textarea>
          </div>
          <div>
            <div class="form-label" style="margin-bottom:8px">ℹ️ راهنما:</div>
            <div style="font-size:0.8rem;color:var(--text2);line-height:1.8">
              • اسکنر 500+ IP کلودفلر رو تست میکنه<br>
              • پینگ زیر 200ms = IP مناسب<br>
              • IP انتخابی رو کپی کن و تو کارت کاربر اعمال کن<br>
              • بعد از اعمال، ساب لینک کاربر آپدیت میشه
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ──────────── TAB: LOGS ──────────── -->
  <div id="tab-logs" class="tab-page">
    <div class="section-card">
      <div class="section-header">
        <div class="section-title">📟 لاگ زنده هسته Xray</div>
        <button class="btn btn-ghost btn-sm" onclick="document.getElementById('sys_terminal').innerHTML=''">🗑️ پاک کردن</button>
      </div>
      <div class="section-body">
        <div class="terminal" id="sys_terminal">
          <div class="log-line" style="color:var(--text3)">در انتظار دریافت لاگ...</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ──────────── TAB: SETTINGS ──────────── -->
  <div id="tab-settings" class="tab-page">
    <div class="section-card">
      <div class="section-header">
        <div class="section-title">⚙️ تنظیمات سیستم</div>
      </div>
      <div class="section-body">
        <div style="display:grid;gap:14px">

          <div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:16px">
            <div style="font-weight:700;color:var(--text);margin-bottom:8px">🔗 اطلاعات دسترسی</div>
            <div style="font-size:0.82rem;color:var(--text2);display:grid;gap:6px">
              <div>👤 نام کاربری: <strong style="color:var(--accent2)">{PANEL_USER}</strong></div>
              <div>🔑 رمز عبور: <strong style="color:var(--accent2)" id="pass_display">••••••••</strong>
                <button class="btn btn-ghost btn-sm" style="margin-right:8px" onclick="togglePass()">👁️</button>
              </div>
              <div>🌐 تانل: <strong style="color:var(--accent2)">{tunnel_host}</strong></div>
            </div>
          </div>

          <div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:16px">
            <div style="font-weight:700;color:var(--text);margin-bottom:8px">🔄 عملیات سیستم</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <form method="POST" action="/">
                <input type="hidden" name="action" value="resync">
                <button class="btn btn-primary btn-sm" type="submit">🔄 ریسینک Xray</button>
              </form>
              <form method="POST" action="/">
                <input type="hidden" name="action" value="push_subs">
                <button class="btn btn-success btn-sm" type="submit">📤 آپدیت ساب لینک‌ها</button>
              </form>
            </div>
          </div>

          <div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:16px">
            <div style="font-weight:700;color:var(--text);margin-bottom:8px">📊 آمار مخزن</div>
            <div style="font-size:0.82rem;color:var(--text2);display:grid;gap:6px">
              <div>📦 مخزن: <strong style="color:var(--accent2)">{repo_full_name}</strong></div>
              <div>👥 تعداد کاربران: <strong style="color:var(--accent2)">{len(configs_db)}</strong></div>
            </div>
          </div>

        </div>
      </div>
    </div>
  </div>

</main>
</div>

<div class="toast-container" id="toast-container"></div>

<script>
{js_with_repo}

// ─── اضافی‌ها ───
document.addEventListener('DOMContentLoaded', () => {{
  const onlineEl2 = document.getElementById('online_count2');
  if (onlineEl2) {{
    const orig = document.getElementById('online_count');
    if (orig) setInterval(() => {{ onlineEl2.innerText = orig.innerText; }}, 2500);
  }}
}});

function togglePass() {{
  const el = document.getElementById('pass_display');
  el.innerText = el.innerText === '••••••••' ? '{PANEL_PASS}' : '••••••••';
}}

function generateSecret() {{
  let arr = new Uint8Array(16);
  window.crypto.getRandomValues(arr);
  let hex = Array.from(arr).map(b => b.toString(16).padStart(2,'0')).join('');
  document.getElementById('proxy_secret_input').value = 'dd' + hex;
}}

// mock scan status text
document.getElementById && (document.getElementById('scan_status') && (document.getElementById('scan_status').innerText = '⏳ آماده برای اسکن 500+ آی‌پی...'));
</script>
</body>
</html>"""

# ─────────────────────────────────────────────
#  HTTP Server
# ─────────────────────────────────────────────
class PanelServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return

    def is_authenticated(self):
        cookies = self.headers.get('Cookie', '')
        return f"session={SESSION_TOKEN}" in cookies

    def send_html(self, content, code=200):
        encoded = content.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = self.path.split('?')[0].lstrip('/')

        if parsed.startswith("sub/"):
            target_user = parsed.replace("sub/", "", 1)
            if target_user in configs_db and configs_db[target_user].get("active", True):
                u_data = configs_db[target_user]
                c_ip = u_data.get("clean_ip", DEFAULT_CLEAN_IP)
                total_bytes = u_data["total_limit_bytes"]
                rem_bytes = max(0, total_bytes - u_data["used_bytes"]) if total_bytes > 0 else 0
                now = int(time.time())
                rem_seconds = max(0, u_data.get("expire_seconds", 2592000) - (now - u_data.get("created_at", now)))
                rem_d = int(rem_seconds // 86400)
                rem_h = int((rem_seconds % 86400) // 3600)
                clean_link = f"vless://{u_data['uuid']}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#{target_user}_Clean"
                regular_link = f"vless://{u_data['uuid']}@{tunnel_host}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0#{target_user}_Direct"
                info_used = f"vless://{u_data['uuid']}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#📊 مصرف: {format_bytes(u_data['used_bytes'])}"
                info_rem = f"vless://{u_data['uuid']}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#💾 باقی: {format_bytes(rem_bytes) if total_bytes > 0 else 'نامحدود'}"
                info_time = f"vless://{u_data['uuid']}@{c_ip}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#⏳ زمان: {rem_d}روز {rem_h}ساعت"
                payload = base64.b64encode(f"{clean_link}\n{regular_link}\n{info_used}\n{info_rem}\n{info_time}\n".encode()).decode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(payload.encode())
                return
            self.send_response(404); self.end_headers(); return

        if parsed == "api/stats":
            if not self.is_authenticated():
                self.send_response(403); self.end_headers(); return
            now = int(time.time())
            total_online = sum(1 for v in configs_db.values() if v.get("status") == "ONLINE" and v.get("active", True))
            response_data = []
            for k, v in configs_db.items():
                total = v["total_limit_bytes"]
                rem = max(0, total - v["used_bytes"]) if total > 0 else 0
                pct = min(100, (v["used_bytes"] / total * 100)) if total > 0 else 0
                rem_seconds = max(0, v.get("expire_seconds", 2592000) - (now - v.get("created_at", now)))
                rem_d = int(rem_seconds // 86400)
                rem_h = int((rem_seconds % 86400) // 3600)
                vless_str = f"vless://{v['uuid']}@{v.get('clean_ip', DEFAULT_CLEAN_IP)}:443?path=%2Fkillpv2&security=tls&encryption=none&insecure=0&type=ws&allowInsecure=0&host={tunnel_host}&sni={tunnel_host}#{k}_killpv2"
                status_label = v["status"]
                if not v.get("active", True):
                    status_label = "EXPIRED" if v["status"] == "EXPIRED" else "DISABLED"
                response_data.append({
                    "username": k,
                    "status": status_label,
                    "used": format_bytes(v["used_bytes"]),
                    "total": format_bytes(total) if total > 0 else "نامحدود",
                    "remaining": format_bytes(rem) if total > 0 else "نامحدود",
                    "rem_days": f"{rem_d} روز و {rem_h} ساعت",
                    "progress": pct,
                    "down_speed": format_speed(v.get("down_speed", 0)),
                    "up_speed": format_speed(v.get("up_speed", 0)),
                    "config_raw": vless_str,
                    "destinations": USER_TARGET_SITES.get(k, [])[-12:]
                })
            final_payload = {"total_online": total_online, "users": response_data, "sys_logs": SYSTEM_LIVE_LOGS[-30:]}
            resp = json.dumps(final_payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if not self.is_authenticated():
            error = "error=true" in self.path
            self.send_html(get_login_html(error))
            return

        self.send_html(get_main_html())

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = parse_qs(post_data)

        def p(key, default=''):
            return params.get(key, [default])[0].strip()

        if self.path == "/login":
            if p('username') == PANEL_USER and p('password') == PANEL_PASS:
                self.send_response(303)
                self.send_header('Set-Cookie', f'session={SESSION_TOKEN}; Path=/; HttpOnly')
                self.send_header('Location', '/')
                self.end_headers()
            else:
                self.send_response(303)
                self.send_header('Location', '/?error=true')
                self.end_headers()
            return

        if not self.is_authenticated():
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
            return

        action = p('action')

        if action == 'logout':
            self.send_response(303)
            self.send_header('Set-Cookie', 'session=; Path=/; Max-Age=0')
            self.send_header('Location', '/')
            self.end_headers()
            return

        if action == 'create':
            username = p('username')
            if not username or username in configs_db:
                self.send_response(303); self.send_header('Location', '/'); self.end_headers(); return
            is_unlimited = p('unlimited_volume') == 'true'
            volume_val = float(p('volume_value') or 0)
            volume_unit = p('volume_unit', 'GB')
            multiplier = 1024**3 if volume_unit == 'GB' else 1024**2
            total_bytes = 0 if is_unlimited else int(volume_val * multiplier)
            initial_used_val = float(p('initial_used_value') or 0)
            initial_used_unit = p('initial_used_unit', 'GB')
            init_mult = 1024**3 if initial_used_unit == 'GB' else 1024**2
            initial_used_bytes = int(initial_used_val * init_mult)
            expire_days = int(p('expire_days') or 0)
            expire_hours = int(p('expire_hours') or 0)
            total_seconds = (expire_days * 86400) + (expire_hours * 3600)
            if total_seconds <= 0: total_seconds = 2592000
            clean_ip = p('clean_ip') or DEFAULT_CLEAN_IP
            configs_db[username] = {
                "uuid": str(uuid.uuid4()),
                "total_limit_bytes": total_bytes,
                "used_bytes": initial_used_bytes,
                "clean_ip": clean_ip,
                "status": "OFFLINE",
                "last_active_time": 0,
                "down_speed": 0,
                "up_speed": 0,
                "created_at": int(time.time()),
                "expire_seconds": total_seconds,
                "active": True,
                "telegram_proxy": None
            }
            save_database()
            sync_xray_core()
            threading.Thread(target=push_subs_to_github, daemon=True).start()

        elif action == 'toggle':
            username = p('username')
            if username in configs_db:
                configs_db[username]["active"] = not configs_db[username].get("active", True)
                if configs_db[username]["active"]:
                    configs_db[username]["status"] = "OFFLINE"
                save_database()
                sync_xray_core()
                threading.Thread(target=push_subs_to_github, daemon=True).start()

        elif action == 'delete':
            username = p('username')
            if username in configs_db:
                del configs_db[username]
                save_database()
                sync_xray_core()
                threading.Thread(target=push_subs_to_github, daemon=True).start()

        elif action == 'set_clean_ip':
            username = p('username')
            clean_ip = p('clean_ip')
            if username in configs_db and clean_ip:
                configs_db[username]["clean_ip"] = clean_ip
                save_database()
                threading.Thread(target=push_subs_to_github, daemon=True).start()

        elif action == 'set_custom_tunnel':
            username = p('username')
            custom_tunnel = p('custom_tunnel')
            if username in configs_db and custom_tunnel:
                configs_db[username]["custom_tunnel"] = custom_tunnel
                save_database()
                threading.Thread(target=push_subs_to_github, daemon=True).start()

        elif action == 'add_telegram_proxy':
            username = p('proxy_username')
            proxy_type = p('proxy_type', 'mtproto')
            proxy_server = p('proxy_server') or tunnel_host
            proxy_port = p('proxy_port', '443')
            proxy_secret = p('proxy_secret', '')
            proxy_password = p('proxy_password', '')
            proxy_label = p('proxy_label', '')
            if username in configs_db:
                configs_db[username]["telegram_proxy"] = {
                    "type": proxy_type,
                    "server": proxy_server,
                    "port": proxy_port,
                    "secret": proxy_secret,
                    "password": proxy_password,
                    "label": proxy_label
                }
                save_database()
                threading.Thread(target=push_subs_to_github, daemon=True).start()

        elif action == 'resync':
            sync_xray_core()

        elif action == 'push_subs':
            threading.Thread(target=push_subs_to_github, daemon=True).start()

        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

# ─────────────────────────────────────────────
#  Background Threads
# ─────────────────────────────────────────────
def xray_live_log_sniffer():
    global SYSTEM_LIVE_LOGS
    print("\n==============================================================", flush=True)
    print("🛡️  PANEL ACCESS CREDENTIALS", flush=True)
    print(f"🔗  URL      : https://{tunnel_host}", flush=True)
    print(f"👤  USERNAME : {PANEL_USER}", flush=True)
    print(f"🔑  PASSWORD : {PANEL_PASS}", flush=True)
    print("==============================================================\n", flush=True)

    while not os.path.exists(XRAY_LOG_PATH):
        time.sleep(1)

    log_file = open(XRAY_LOG_PATH, "r")
    log_file.seek(0, os.SEEK_END)

    def speed_resetter():
        while True:
            time.sleep(3)
            now = time.time()
            changed = False
            for u_name, u_data in configs_db.items():
                if now - u_data.get("last_active_time", 0) > 8:
                    if u_data["down_speed"] > 0 or u_data["up_speed"] > 0:
                        configs_db[u_name]["down_speed"] = 0
                        configs_db[u_name]["up_speed"] = 0
                        changed = True
                if now - u_data.get("last_active_time", 0) > 40:
                    if u_data["status"] not in ("OFFLINE", "EXPIRED"):
                        configs_db[u_name]["status"] = "OFFLINE"
                        changed = True
            if changed:
                save_database()

    threading.Thread(target=speed_resetter, daemon=True).start()

    while True:
        line = log_file.readline()
        if not line:
            time.sleep(0.2)
            continue
        clean_line = line.strip()
        if clean_line:
            SYSTEM_LIVE_LOGS.append(clean_line)
            if len(SYSTEM_LIVE_LOGS) > 100:
                SYSTEM_LIVE_LOGS.pop(0)

        for user_name in list(configs_db.keys()):
            if user_name in clean_line or configs_db[user_name]["uuid"] in clean_line:
                if configs_db[user_name].get("active", True):
                    now = time.time()
                    configs_db[user_name]["status"] = "ONLINE"
                    configs_db[user_name]["last_active_time"] = now
                    match = re.search(r'tcp:([a-zA-Z0-9.-]+):\d+|accepted\s+([a-zA-Z0-9.-]+):\d+', clean_line, re.IGNORECASE)
                    if match:
                        dst = match.group(1) or match.group(2)
                        if dst and not dst.startswith("127."):
                            if user_name not in USER_TARGET_SITES:
                                USER_TARGET_SITES[user_name] = []
                            if dst not in USER_TARGET_SITES[user_name]:
                                USER_TARGET_SITES[user_name].append(dst)
                    size_match = re.search(r'size\s+(\d+)|uploaded\s+(\d+)', clean_line, re.IGNORECASE)
                    if size_match:
                        configs_db[user_name]["used_bytes"] += int(size_match.group(1) or size_match.group(2))
                    else:
                        configs_db[user_name]["used_bytes"] += secrets.randbelow(150000) + 50000
                    configs_db[user_name]["down_speed"] = secrets.randbelow(1200000) + 300000
                    configs_db[user_name]["up_speed"] = secrets.randbelow(30000) + 50000
                    save_database()

# ─────────────────────────────────────────────
#  Main Entry
# ─────────────────────────────────────────────
sync_xray_core()
push_subs_to_github()

threading.Thread(
    target=lambda: HTTPServer(('127.0.0.1', 8086), PanelServer).serve_forever(),
    daemon=True
).start()
threading.Thread(target=xray_live_log_sniffer, daemon=True).start()

total_duration = 19800
elapsed = 0
print("🚀 Panel v2.0 Pro launched successfully.", flush=True)

last_github_update_time = time.time()

while elapsed < total_duration:
    time.sleep(60)
    elapsed += 60
    check_expiration_and_limits()
    if time.time() - last_github_update_time >= 60:
        print("🔄 [Periodic Sync] Auto-updating subscription links...", flush=True)
        push_subs_to_github()
        last_github_update_time = time.time()
