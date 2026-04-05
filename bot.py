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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "PUT_YOUR_TOKEN_HERE")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "PUT_YOUR_ODDS_KEY_HERE")
MY_CHAT_ID = os.getenv("MY_CHAT_ID", "PUT_YOUR_CHAT_ID_HERE")
ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")
FOOTBALL_LEAGUES = {
"soccer_epl": "\u05dc\u05d9\u05d2\u05ea \u05e4\u05e8\u05de\u05d9\u05d9\u05e8",
"soccer_spain_la_liga": "\u05dc\u05d4 \u05dc\u05d9\u05d2\u05d4",
"soccer_germany_bundesliga": "\u05d1\u05d5\u05e0\u05d3\u05e1\u05dc\u05d9\u05d2\u05d4",
"soccer_italy_serie_a": "\u05e1\u05e8\u05d9\u05d4 \u05d0",
"soccer_uefa_champs_league": "\u05dc\u05d9\u05d2\u05ea \u05d4\u05d0\u05dc\u05d5\u05e4\u05d5\u05ea",
"soccer_israel_premier_league": "\u05dc\u05d9\u05d2\u05ea \u05d4\u05e2\u05dc",
}
BASKETBALL_LEAGUES = {
"basketball_nba": "NBA",
"basketball_euroleague": "\u05d9\u05d5\u05e8\u05d5\u05dc\u05d9\u05d2",
"basketball_israel_premier_league": "\u05dc\u05d9\u05d2\u05ea Winner",
}
VALUE_MIN = 1.55
VALUE_MAX = 2.15
ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports"
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
@bot.message_handler(func=lambda m: True)

def ignore_all(message):
if str(message.chat.id) != str(MY_CHAT_ID):
return
bot.reply_to(message, "\u05d4\u05d1\u05d5\u05d8 \u05e4\u05e2\u05d9\u05dc. \u05d4\u05d3\u05d5\u05d7 \u05d9\u05d5\u05e9\u05dc\u05d7 \u05d1-10:00.")
def fetch_odds_for_league(sport_key):
url = ODDS_API_BASE + "/" + sport_key + "/odds"
params = {"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"}
try:
resp = requests.get(url, params=params, timeout=15)
remaining = resp.headers.get("x-requests-remaining", "?")
if resp.status_code == 200:
return resp.json(), remaining
elif resp.status_code == 422:
logger.warning(sport_key + " not active")
else:
logger.error("API " + str(resp.status_code) + " " + sport_key)
except requests.RequestException as e:
logger.error("Network error: " + str(e))
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
utc_dt = pytz.utc.localize(datetime.strptime(ev.get("commence_time", ""), "%Y-%m-%dT%H:%M:%SZ"))
il_dt = utc_dt.astimezone(ISRAEL_TZ)
time_str = il_dt.strftime("%H:%M")
date_str = il_dt.strftime("%d/%m")
except Exception:
time_str = "--"
date_str = "--"
for team_name, odds_list in outcome_odds.items():

if len(odds_list) < 2:
continue
consensus = statistics.mean(odds_list)
if not (VALUE_MIN <= consensus <= VALUE_MAX):
continue
if team_name not in (home, away):
continue
candidates.append({
"home": home,
"away": away,
"rec": team_name,
"odd": round(consensus, 2),
"vol": round(statistics.stdev(odds_list), 4),
"time": time_str,
"date": date_str,
"league": league_name,
"bk_count": len(odds_list),
})
return candidates
def deduplicate_and_sort(candidates):
seen = {}
for c in candidates:
pair = (c["home"], c["away"])
if pair not in seen or c["vol"] < seen[pair]["vol"]:
seen[pair] = c
return sorted(seen.values(), key=lambda x: x["vol"])
def format_section(top, label):
no_opps = "\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0\u05d5 \u05d4\u05d6\u05d3\u05de\u05e0\u05d5\u05d9\u05d5\u05ea \u05d4\u05d9\u05d5\u05dd."
banker_title = "\u05d4\u05d1\u05d0\u05e0\u05e7\u05e8 \u05d4\u05d9\u05d5\u05de\u05d9:"
double_title = "\u05d4\u05d3\u05d0\u05d1\u05dc \u05d4\u05d9\u05d5\u05de\u05d9:"
no_double = "\u05d0\u05d9\u05df \u05de\u05e1\u05e4\u05d9\u05e7 \u05de\u05e9\u05d7\u05e7\u05d9\u05dd \u05dc\u05d3\u05d0\u05d1\u05dc \u05d4\u05d9\u05d5\u05dd."
vs_word = " \u05e0\u05d2\u05d3 "
league_word = "\u05dc\u05d9\u05d2\u05d4: "
rec_word = "\u05d4\u05de\u05dc\u05e6\u05d4: \u05e0\u05e6\u05d7\u05d5\u05df "
odd_word = "\u05d9\u05d7\u05e1: "
time_word = "\u05e9\u05e2\u05d4: "
combined_word = "\u05d9\u05d7\u05e1 \u05de\u05e9\u05d5\u05dc\u05d1: "
match_word = "\u05de\u05e9\u05d7\u05e7 "
bk_word = "\u05e1\u05d5\u05db\u05e0\u05d5\u05d9\u05d5\u05ea: "
vol_word = " | \u05ea\u05e0\u05d5\u05d3\u05d5\u05ea\u05d9\u05d5\u05ea: "
lines = ["\n<b>" + label + "</b>"]
if not top:
lines.append(no_opps)
return lines, False

b = top[0]
lines += [
"<b>" + banker_title + "</b>",
"<b>" + b["home"] + vs_word + b["away"] + "</b>",
league_word + b["league"],
rec_word + b["rec"],
odd_word + "<b>" + str(b["odd"]) + "</b>",
time_word + b["date"] + " " + b["time"],
bk_word + str(b["bk_count"]) + vol_word + str(b["vol"]),
"",
]
doubles = top[1:3]
if len(doubles) == 2:
combined = round(doubles[0]["odd"] * doubles[1]["odd"], 2)
lines += [
"<b>" + double_title + "</b>",
combined_word + "<b>" + str(combined) + "</b>",
"",
]
for i, d in enumerate(doubles, 1):
lines += [
match_word + str(i) + ": " + d["home"] + vs_word + d["away"],
league_word + d["league"],
rec_word + d["rec"] + " | " + odd_word + str(d["odd"]) + " | " + time_word + d["date"] + " " + d["time"],
"",
]
else:
lines.append(no_double)
return lines, True
def build_report():
football_raw = []
basketball_raw = []
last_remaining = "?"
for key, name in FOOTBALL_LEAGUES.items():
evs, rem = fetch_odds_for_league(key)
if rem:
last_remaining = rem
football_raw.extend(extract_candidates(evs, name))
for key, name in BASKETBALL_LEAGUES.items():
evs, rem = fetch_odds_for_league(key)
if rem:
last_remaining = rem

basketball_raw.extend(extract_candidates(evs, name))
ft = deduplicate_and_sort(football_raw)
bt = deduplicate_and_sort(basketball_raw)
now_il = datetime.now(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M")
header = "\u05d3\u05d5\u05d7 \u05d0\u05e0\u05dc\u05d9\u05e1\u05d8 \u05d9\u05d5\u05de\u05d9"
date_word = "\u05ea\u05d0\u05e8\u05d9\u05da: "
no_opps_msg = "\u05d4\u05d9\u05d5\u05dd \u05dc\u05d0 \u05e0\u05de\u05e6\u05d0\u05d5 \u05d4\u05d6\u05d3\u05de\u05e0\u05d5\u05d9\u05d5\u05ea \u05d1\u05e2\u05dc\u05d5\u05ea \u05e2\u05e8\u05da \u05d2\u05d1\u05d5\u05d4."
credits_word = "\u05d9\u05ea\u05e8\u05ea \u05e9\u05d0\u05d9\u05dc\u05ea\u05d5\u05ea: "
disclaimer = "\u05d4\u05d3\u05d5\u05d7 \u05de\u05d9\u05d5\u05e2\u05d3 \u05dc\u05de\u05d9\u05d3\u05e2 \u05d1\u05dc\u05d1\u05d3. \u05d4\u05d9\u05de\u05d5\u05e8 \u05d1\u05d0\u05d7\u05e8\u05d9\u05d5\u05ea\u05da."
football_label = "\u05db\u05d3\u05d5\u05e8\u05d2\u05dc"
basketball_label = "\u05db\u05d3\u05d5\u05e8\u05e1\u05dc"
lines = [
"<b>" + header + "</b>",
date_word + now_il,
"---",
]
football_lines, has_f = format_section(ft, football_label)
basketball_lines, has_b = format_section(bt, basketball_label)
lines += football_lines
lines.append("---")
lines += basketball_lines
if not has_f and not has_b:
return "<b>" + header + "</b>\n\n" + no_opps_msg + "\n\n" + credits_word + last_remaining
lines += [
"---",
credits_word + "<b>" + last_remaining + "</b>",
"<i>" + disclaimer + "</i>",
]
return "\n".join(lines)
def send_daily_report():
logger.info("Sending daily report...")
try:
report = build_report()
bot.send_message(MY_CHAT_ID, report)
logger.info("Report sent.")
except Exception as e:
logger.error("Error: " + str(e))
try:

bot.send_message(MY_CHAT_ID, "Error: " + str(e))
except Exception:
pass
flask_app = Flask(__name__)
@flask_app.route("/")
def health():
return "Bot is running", 200
def run_flask():
flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
if __name__ == "__main__":
scheduler = BackgroundScheduler(timezone=ISRAEL_TZ)
scheduler.add_job(
send_daily_report,
CronTrigger(hour=10, minute=0, timezone=ISRAEL_TZ),
id="daily_report",
replace_existing=True,
)
scheduler.start()
logger.info("Scheduler started.")
threading.Thread(target=run_flask, daemon=True).start()
logger.info("Bot started.")
bot.infinity_polling(timeout=30, long_polling_timeout=20)
