import os
import logging
import requests
import telebot
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import threading
from datetime import datetime
from collections import defaultdict
import statistics
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
───────────────────────────────────── החלף את 3 הערכים האלה בפרטים שלך ─── #
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "PUT_YOUR_TOKEN_HERE")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "PUT_YOUR_ODDS_KEY_HERE")
MY_CHAT_ID = os.getenv("MY_CHAT_ID", "PUT_YOUR_CHAT_ID_HERE")
# ──────────────────────────────────────────────────────────────────────────────
ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")
FOOTBALL_LEAGUES = {
,"ליגת פרמייר " :"epl_soccer "
"soccer_spain_la_liga": " ליגה לה",
"soccer_germany_bundesliga": " בונדסליגה",
"soccer_italy_serie_a": " א סריה",
"soccer_uefa_champs_league": " האלופות ליגת",
"soccer_israel_premier_league": " הישראלית העל ליגת",
}
BASKETBALL_LEAGUES = {
"basketball_nba": " NBA",
"basketball_euroleague": " יורוליג",
"basketball_israel_premier_league": " ליגת Winner",
}
VALUE_MIN = 1.55
VALUE_MAX = 2.15
ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports"
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

@bot.message_handler(func=lambda m: True)
def ignore_all(message):
if str(message.chat.id) != str(MY_CHAT_ID):
logger.warning(f"Blocked: {message.chat.id}")
return
(".הבוט פעיל. הדוח היומי נשלח אוטומטית ב10:00- " ,message(to_reply.bot
def fetch_odds_for_league(sport_key):
url = f"{ODDS_API_BASE}/{sport_key}/odds"
params = {"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"}
try:
resp = requests.get(url, params=params, timeout=15)
remaining = resp.headers.get("x-requests-remaining", "?")
if resp.status_code == 200:
return resp.json(), remaining
elif resp.status_code == 422:
logger.warning(f"{sport_key} פעילה אינה.("
else:
logger.error(f"API {resp.status_code} – {sport_key}: {resp.text}")
except requests.RequestException as e:
logger.error(f"רשת} – sport_key}: {e}")
return [], None
def extract_candidates(events, league_name):
candidates = []
for ev in events:
bookmakers = ev.get("bookmakers", [])
if not bookmakers:
continue
outcome_odds = defaultdict(list)
for bm in bookmakers:
for market in bm.get("markets", []):
if market.get("key") != "h2h":
continue
for outcome in market.get("outcomes", []):
outcome_odds[outcome["name"]].append(float(outcome["price"]))
home = ev.get("home_team", "?")
away = ev.get("away_team", "?")
try:
utc_dt = pytz.utc.localize(datetime.strptime(ev.get("commence_time",""), "%Y-%m-%dT%H:%M:%SZ"))
il_dt = utc_dt.astimezone(ISRAEL_TZ)
time_str = il_dt.strftime("%H:%M")
date_str = il_dt.strftime("%d/%m")
except Exception:
time_str = date_str = "--"

for team_name, odds_list in outcome_odds.items():
if len(odds_list) < 2:
continue
consensus = statistics.mean(odds_list)
if not (VALUE_MIN <= consensus <= VALUE_MAX):
continue
if team_name not in (home, away):
continue
candidates.append({
"home": home, "away": away,
"recommendation": f"נצחון} team_name}",
"odd": round(consensus, 2),
"volatility": round(statistics.stdev(odds_list), 4),
"time": time_str, "date": date_str,
"league": league_name,
"bookmaker_count": len(odds_list),
})
return candidates
def deduplicate_and_sort(candidates):
seen = {}
for c in candidates:
pair = (c["home"], c["away"])
if pair not in seen or c["volatility"] < seen[pair]["volatility"]:
seen[pair] = c
return sorted(seen.values(), key=lambda x: x["volatility"])
def format_section(top, sport_label):
lines = [f"\n{sport_label}"]
if not top:
("n\.לא נמצאו הזדמנויות היום ")append.lines
return lines, False
b = top[0]
lines += [
,"<b/<הבאנקר היומי<b " <
f" <b>{b['home']} נגד} b['away']}</b>",
f" {b['league']}",
f" המלצה:} b['recommendation']}",
f" יחס:> b>{b['odd']}</b>",
f" {b['date']} | {b['time']}",
f" {b['bookmaker_count']} תנודתיות | סוכנויות:} b['volatility']}",
"",
]
doubles = top[1:3]
if len(doubles) == 2:

combined = round(doubles[0]["odd"] * doubles[1]["odd"], 2)
lines += [f" <b>היומי הדאבל>/b>", f" משולב יחס:> b>{combined}</b>"]
if not (2.80 <= combined <= 3.80):
lines.append(" <i>(3.80–2.80) האידיאלי מהטווח חורג>/i>")
lines.append("")
for i, d in enumerate(doubles, 1):
lines += [
f" <b>משחק} i}:</b> {d['home']} נגד} d['away']}",
f" {d['league']}",
f" {d['recommendation']} | {d['odd']} | {d['date']} {d['time']}",
"",
]
else:
("n\.אין מספיק משחקים לדאבל היום ")append.lines
return lines, True
def build_report():
football_raw = []
basketball_raw = []
last_remaining = "?"
for key, name in FOOTBALL_LEAGUES.items():
evs, rem = fetch_odds_for_league(key)
if rem: last_remaining = rem
football_raw.extend(extract_candidates(evs, name))
for key, name in BASKETBALL_LEAGUES.items():
evs, rem = fetch_odds_for_league(key)
if rem: last_remaining = rem
basketball_raw.extend(extract_candidates(evs, name))
ft = deduplicate_and_sort(football_raw)
bt = deduplicate_and_sort(basketball_raw)
now_il = datetime.now(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M")
lines = [
,"<b/<דוח אנליסט יומי – מהנדס המערכת<b " <
f" <i>{now_il}</i>",
"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
]
football_lines, has_f = format_section(ft, " <b>כדורגל>/b>")
basketball_lines, has_b = format_section(bt, " <b>כדורסל>/b>")
lines += football_lines
lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
lines += basketball_lines

if not has_f and not has_b:
return (
"n\n>\b/<דוח אנליסט יומי – מהנדס המערכת<b " <
"n\n\.היום לא נמצאו הזדמנויות בעלות ערך גבוה במערכת "
"{remaining_last {:יתרת שאילתות לחודש זה "f
)
lines += [
"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
f" זה לחודש שאילתות יתרת:> b>{last_remaining}</b>",
,"<i/<.הדוח מיועד לצרכי מידע בלבד. הימור באחריותך <i "<
]
return "\n".join(lines)
def send_daily_report():
("...שולח דוח יומי ")info.logger
try:
report = build_report()
bot.send_message(MY_CHAT_ID, report)
logger.info(" נשלח.("
except Exception as e:
logger.error(f"שגיאה:} e}")
try:
bot.send_message(MY_CHAT_ID, f" הדוח בהפקת שגיאה:\n<code>{e}</code>")
except Exception:
pass
flask_app = Flask(__name__)
@flask_app.route("/")
def health():
return " Smart Analyst Bot – 200 ,"פעיל
def run_flask():
flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
if __name__ == "__main__":
scheduler = BackgroundScheduler(timezone=ISRAEL_TZ)
scheduler.add_job(
send_daily_report,
CronTrigger(hour=10, minute=0, timezone=ISRAEL_TZ),
id="daily_report", replace_existing=True,
)
scheduler.start()
(".פעיל – 10:00 שעון ישראל Scheduler(" info.logger

threading.Thread(target=run_flask, daemon=True).start()
logger.info(" להודעות מאזין Telegram...")
bot.infinity_polling(timeout=30, long_polling_timeout=20)
