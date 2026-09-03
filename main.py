import os
import requests
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

# --- UCRETSIZ WEB SUNUCU (Render'in kapanmamasi icin) ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot aktif ve calisiyor!")
        
    def log_message(self, format, *args):
        return

def run_web_server():
    try:
        server_address = ('0.0.0.0', 10000)
        httpd = HTTPServer(server_address, SimpleHandler)
        print("[+] Web sunucu basariyla baslatildi (Port: 10000)", flush=True)
        httpd.serve_forever()
    except Exception as e:
        print("Web sunucu hatasi:", e, flush=True)


# --- BOT AYARLARI ---
TELEGRAM_TOKEN = "8882670040:AAG5HXZqxga2Wy7X2sz6YLs3aJajhFo3rsQ"
TELEGRAM_CHAT_ID = "8023313276"

notified_matches = set()

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
}

def get_flag_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return "🌐"
    country_code = country_code.upper()
    return chr(ord(country_code[0]) + 127397) + chr(ord(country_code[1]) + 127397)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID, 
        'text': message, 
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram hatasi:", e, flush=True)

def fetch_data(target_url):
    # Cloudflare IP engeline takılmamak için ücretsiz proxy tüneli kullanıyoruz
    encoded_url = urllib.parse.quote(target_url, safe='')
    proxy_url = f"https://api.allorigins.win/raw?url={encoded_url}"
    try:
        res = requests.get(proxy_url, headers=REQUEST_HEADERS, timeout=15)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Proxy veri cekme hatasi: {e}", flush=True)
    return None

def get_match_stats(event_id, period='ALL'):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    home_data = {'shots': 0, 'on_target': 0, 'corners': 0}
    away_data = {'shots': 0, 'on_target': 0, 'corners': 0}
    
    data = fetch_data(url)
    if data:
        statistics = data.get('statistics', [])
        target_group = None
        for stat_period in statistics:
            if stat_period.get('period') == period:
                target_group = stat_period.get('groups', [])
                break
        if not target_group and statistics:
            target_group = statistics[0].get('groups', [])

        if target_group:
            for group in target_group:
                for item in group.get('statisticsItems', []):
                    name = item.get('name')
                    h_val = int(item.get('homeValue', 0) or 0)
                    a_val = int(item.get('awayValue', 0) or 0)
                    
                    if name in ['Total shots', 'Total Shots']:
                        home_data['shots'], away_data['shots'] = h_val, a_val
                    elif name in ['Shots on target', 'Shots on Goal']:
                        home_data['on_target'], away_data['on_target'] = h_val, a_val
                    elif name in ['Corner kicks', 'Corners']:
                        home_data['corners'], away_data['corners'] = h_val, a_val
    return home_data, away_data

def get_h2h_stats(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/h2h/events"
    ht_goals_count = 0
    over_25_count = 0
    total_h2h = 0
    
    data = fetch_data(url)
    if data:
        events = data.get('events', [])[:5]
        total_h2h = len(events)
        for ev in events:
            h_score = ev.get('homeScore', {}).get('current', 0) or 0
            a_score = ev.get('awayScore', {}).get('current', 0) or 0
            h_ht = ev.get('homeScore', {}).get('period1', 0) or 0
            a_ht = ev.get('awayScore', {}).get('period1', 0) or 0
            if (h_ht + a_ht) > 0:
                ht_goals_count += 1
            if (h_score + a_score) > 2.5:
                over_25_count += 1
                
    if total_h2h == 0:
        return "• H2H Verisi Bulunamadı"
        
    ht_pct = int((ht_goals_count / total_h2h) * 100)
    over_pct = int((over_25_count / total_h2h) * 100)
    return (f"📜 *H2H (Aralarındaki Son {total_h2h} Maç):*\n"
            f"• İY Gol Olma Oranı: *%{ht_pct} ({ht_goals_count}/{total_h2h})*\n"
            f"• 2.5 Üst Biten: *%{over_pct} ({over_25_count}/{total_h2h})*")

def check_live_matches():
    url = "https://api.sofascore.com/api/v1/sport/football/events/live"
    data = fetch_data(url)
    if not data:
        print("Baglanti bekleniyor, Veri alinamadi.", flush=True)
        return

    events = data.get('events', [])
    print(f"[+] Sofascore Canli Taramasi ({len(events)} mac aktif)...", flush=True)

    for event in events:
        fixture_id = event.get('id')
        slug = event.get('slug', '')
        status = event.get('status', {})
        description = status.get('description', '')
        
        if status.get('type') != 'inprogress' or description == 'Halftime':
            continue

        time_info = event.get('time', {})
        current_timestamp = int(time.time())
        period_start = time_info.get('currentPeriodStartTimestamp', current_timestamp)
        
        elapsed = (current_timestamp - period_start) // 60
        if description == '2nd half':
            elapsed += 45

        is_extreme_time = (1 <= elapsed <= 40 or 50 <= elapsed <= 80)
        is_s1_time = (1 <= elapsed <= 20)
        is_s1_late_time = (30 <= elapsed <= 40)
        is_s2_time = (15 <= elapsed <= 30)
        is_s3_time = (60 <= elapsed <= 70)
        is_s4_time = (75 <= elapsed <= 88)

        home = event.get('homeTeam', {}).get('name', 'Ev')
        away = event.get('awayTeam', {}).get('name', 'Dep')
        
        tournament_data = event.get('tournament', {})
        category_data = tournament_data.get('category', {})
        country_code = category_data.get('alpha2', '')
        flag = get_flag_emoji(country_code)
        
        league_name = tournament_data.get('name', 'Lig')
        country_name = category_data.get('name', '')
        full_league_info = f"{flag} {country_name} - {league_name}" if country_name else f"{flag} {league_name}"

        goals_home = int(event.get('homeScore', {}).get('current', 0) or 0)
        goals_away = int(event.get('awayScore', {}).get('current', 0) or 0)
        total_goals = goals_home + goals_away
        match_link = f"https://www.sofascore.com/{slug}/{fixture_id}"

        if is_extreme_time:
            key = f"{fixture_id}_S0"
            if key not in notified_matches:
                period_type = '2ND' if elapsed > 45 else '1ST'
                home_s, away_s = get_match_stats(fixture_id, period=period_type)
                tot_shots = home_s['shots'] + away_s['shots']
                tot_target = home_s['on_target'] + away_s['on_target']
                tot_corners = home_s['corners'] + away_s['corners']

                if tot_shots >= 7 and tot_target >= 3 and tot_corners >= 4:
                    h2h_info = get_h2h_stats(fixture_id)
                    period_str = "2. Yarı" if elapsed > 45 else "1. Yarı"
                    msg = (f"🚨 *[ASIRI BASKI]*\n🏆 *{full_league_info}*\n\n"
                           f"⚽ *{home}* {goals_home} - {goals_away} *{away}*\n"
                           f"⏱️ Dakika: *{elapsed}'*\n\n📊 *Istatistikler ({period_str}):*\n"
                           f"🏠 *{home}:* {home_s['shots']} Sut | {home_s['on_target']} Isabet | {home_s['corners']} Korner\n"
                           f"✈️ *{away}:* {away_s['shots']} Sut | {away_s['on_target']} Isabet | {away_s['corners']} Korner\n"
                           f"📈 *Toplam:* {tot_shots} Sut | {tot_target} Isabet | {tot_corners} Korner\n\n"
                           f"{h2h_info}\n\n💡 *BOT ONERISI:* 🎯 *SIRADAKI GOL / MAC USTU*\n🔗 [Maca Git]({match_link})")
                    print(f"-> Sinyal Gonderildi: {home} vs {away}", flush=True)
                    send_telegram_message(msg)
                    notified_matches.add(key)

        if is_s1_time and total_goals == 0:
            key = f"{fixture_id}_S1"
            if key not in notified_matches:
                home_s, away_s = get_match_stats(fixture_id, period='1ST')
                tot_shots = home_s['shots'] + away_s['shots']
                tot_target = home_s['on_target'] + away_s['on_target']
                tot_corners = home_s['corners'] + away_s['corners']
                if tot_shots >= 3 and tot_target >= 1 and tot_corners >= 1:
                    h2h_info = get_h2h_stats(fixture_id)
                    msg = (f"🔥 *[STRATEJI 1 - ERKEN IY GOL]*\n🏆 *{full_league_info}*\n\n"
                           f"⚽ *{home}* {goals_home} - {goals_away} *{away}*\n"
                           f"⏱️ Dakika: *{elapsed}'*\n\n📊 *Istatistikler (1. Yari):*\n"
                           f"🏠 *{home}:* {home_s['shots']} Sut | {home_s['on_target']} Isabet | {home_s['corners']} Korner\n"
                           f"✈️ *{away}:* {away_s['shots']} Sut | {away_s['on_target']} Isabet | {away_s['corners']} Korner\n"
                           f"📈 *Toplam:* {tot_shots} Sut | {tot_target} Isabet | {tot_corners} Korner\n\n"
                           f"{h2h_info}\n\n💡 *BOT ONERISI:* 🎯 *ILK YARI 0.5 UST*\n🔗 [Maca Git]({match_link})")
                    print(f"-> Sinyal Gonderildi: {home} vs {away}", flush=True)
                    send_telegram_message(msg)
                    notified_matches.add(key)

        if is_s1_late_time and total_goals == 0:
            key = f"{fixture_id}_S1_LATE"
            if key not in notified_matches:
                home_s, away_s = get_match_stats(fixture_id, period='1ST')
                tot_shots = home_s['shots'] + away_s['shots']
                tot_target = home_s['on_target'] + away_s['on_target']
                tot_corners = home_s['corners'] + away_s['corners']
                if tot_shots >= 4 and tot_target >= 2 and tot_corners >= 2:
                    h2h_info = get_h2h_stats(fixture_id)
                    msg = (f"🎯 *[IY KAPANIS BASKISI (30'+)]*\n🏆 *{full_league_info}*\n\n"
                           f"⚽ *{home}* {goals_home} - {goals_away} *{away}*\n"
                           f"⏱️ Dakika: *{elapsed}'*\n\n📊 *Istatistikler (1. Yari):*\n"
                           f"🏠 *{home}:* {home_s['shots']} Sut | {home_s['on_target']} Isabet | {home_s['corners']} Korner\n"
                           f"✈️ *{away}:* {away_s['shots']} Sut | {away_s['on_target']} Isabet | {away_s['corners']} Korner\n"
                           f"📈 *Toplam:* {tot_shots} Sut | {tot_target} Isabet | {tot_corners} Korner\n\n"
                           f"{h2h_info}\n\n💡 *BOT ONERISI:* 🎯 *ILK YARI 0.5 UST (YUKSEK ORAN)*\n🔗 [Maca Git]({match_link})")
                    print(f"-> Sinyal Gonderildi: {home} vs {away}", flush=True)
                    send_telegram_message(msg)
                    notified_matches.add(key)

        elif is_s2_time and total_goals > 0:
            key = f"{fixture_id}_S2"
            if key not in notified_matches:
                home_s, away_s = get_match_stats(fixture_id, period='1ST')
                tot_shots = home_s['shots'] + away_s['shots']
                tot_target = home_s['on_target'] + away_s['on_target']
                tot_corners = home_s['corners'] + away_s['corners']
                if tot_shots >= 3 and tot_target >= 1 and tot_corners >= 2:
                    h2h_info = get_h2h_stats(fixture_id)
                    msg = (f"⚡ *[STRATEJI 2]*\n🏆 *{full_league_info}*\n\n"
                           f"⚽ *{home}* {goals_home} - {goals_away} *{away}*\n"
                           f"⏱️ Dakika: *{elapsed}'*\n\n📊 *Istatistikler (1. Yari):*\n"
                           f"🏠 *{home}:* {home_s['shots']} Sut | {home_s['on_target']} Isabet | {home_s['corners']} Korner\n"
                           f"✈️ *{away}:* {away_s['shots']} Sut | {away_s['on_target']} Isabet | {away_s['corners']} Korner\n"
                           f"📈 *Toplam:* {tot_shots} Sut | {tot_target} Isabet | {tot_corners} Korner\n\n"
                           f"{h2h_info}\n\n💡 *BOT ONERISI:* 🎯 *ILK YARI 1.5 UST*\n🔗 [Maca Git]({match_link})")
                    print(f"-> Sinyal Gonderildi: {home} vs {away}", flush=True)
                    send_telegram_message(msg)
                    notified_matches.add(key)

        elif is_s3_time and total_goals == 2:
            key = f"{fixture_id}_S3"
            if key not in notified_matches:
                home_s, away_s = get_match_stats(fixture_id, period='2ND')
                tot_shots = home_s['shots'] + away_s['shots']
                tot_target = home_s['on_target'] + away_s['on_target']
                tot_corners = home_s['corners'] + away_s['corners']
                if tot_shots >= 5 and tot_target >= 2 and tot_corners >= 3:
                    h2h_info = get_h2h_stats(fixture_id)
                    msg = (f"🚀 *[STRATEJI 3]*\n🏆 *{full_league_info}*\n\n"
                           f"⚽ *{home}* {goals_home} - {goals_away} *{away}*\n"
                           f"⏱️ Dakika: *{elapsed}'*\n\n📊 *Istatistikler (2. Yari):*\n"
                           f"🏠 *{home}:* {home_s['shots']} Sut | {home_s['on_target']} Isabet | {home_s['corners']} Korner\n"
                           f"✈️ *{away}:* {away_s['shots']} Sut | {away_s['on_target']} Isabet | {away_s['corners']} Korner\n"
                           f"📈 *Toplam:* {tot_shots} Sut | {tot_target} Isabet | {tot_corners} Korner\n\n"
                           f"{h2h_info}\n\n💡 *BOT ONERISI:* 🎯 *2.5 UST*\n🔗 [Maca Git]({match_link})")
                    print(f"-> Sinyal Gonderildi: {home} vs {away}", flush=True)
                    send_telegram_message(msg)
                    notified_matches.add(key)

        elif is_s4_time and abs(goals_home - goals_away) <= 1:
            key = f"{fixture_id}_S4"
            if key not in notified_matches:
                home_s, away_s = get_match_stats(fixture_id, period='2ND')
                tot_shots = home_s['shots'] + away_s['shots']
                tot_target = home_s['on_target'] + away_s['on_target']
                tot_corners = home_s['corners'] + away_s['corners']
                if tot_shots >= 5 and tot_target >= 2 and tot_corners >= 3:
                    h2h_info = get_h2h_stats(fixture_id)
                    target_line = total_goals + 0.5
                    msg = (f"⏰ *[STRATEJI 4 - GEC GOL BASKISI]*\n🏆 *{full_league_info}*\n\n"
                           f"⚽ *{home}* {goals_home} - {goals_away} *{away}*\n"
                           f"⏱️ Dakika: *{elapsed}'*\n\n📊 *Istatistikler (2. Yari Tempo):*\n"
                           f"🏠 *{home}:* {home_s['shots']} Sut | {home_s['on_target']} Isabet | {home_s['corners']} Korner\n"
                           f"✈️ *{away}:* {away_s['shots']} Sut | {away_s['on_target']} Isabet | {away_s['corners']} Korner\n"
                           f"📈 *Toplam:* {tot_shots} Sut | {tot_target} Isabet | {tot_corners} Korner\n\n"
                           f"{h2h_info}\n\n💡 *BOT ONERISI:* 🎯 *SIRADAKI GOL / {target_line} UST*\n🔗 [Maca Git]({match_link})")
                    print(f"-> Sinyal Gonderildi: {home} vs {away}", flush=True)
                    send_telegram_message(msg)
                    notified_matches.add(key)

def run_bot_loop():
    print("="*40, flush=True)
    print(" CANLI BAHIS BOTU PROXY MODU AKTIF", flush=True)
    print("="*40, flush=True)
    try:
        send_telegram_message("🟢 *Bot Proxy Modunda Başlatıldı!* Canlı maçlar taranıyor...")
    except:
        pass
        
    while True:
        check_live_matches()
        time.sleep(120)

if __name__ == '__main__':
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()
    run_bot_loop()
                
