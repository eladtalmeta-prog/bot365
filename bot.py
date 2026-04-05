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
"soccer_epl": "Premier League",
"soccer_spain_la_liga": "La Liga",
"soccer_germany_bundesliga": "Bundesliga",
"soccer_italy_serie_a": "Serie A",
"soccer_uefa_champs_league": "Champions League",
"soccer_israel_premier_league": "Israeli Premier League",
}
BASKETBALL_LEAGUES = {
"basketball_nba": "NBA",
"basketball_euroleague": "EuroLeague",
"basketball_israel_premier_league": "Winner League",
}
VALUE_MIN = 1.55
VALUE_MAX = 2.15
ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports"
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

@bot.message_handler(func=lambda m: True)
def ignore_all(message):
if str(message.chat.id) != str(MY_CHAT_ID):
return
bot.reply_to(message, "Bot active. Daily report sent at 10:00 AM Israel time.")

def fetch_odds_for_league(sport_key):
url = ODDS_API_BASE + "/" + sport_key + "/odds"
params = {
"apiKey": ODDS_API_KEY,
"regions": "eu",
"markets": "h2h",
"oddsFormat": "decimal",
}
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
lines = ["\n<b>" + label + "</b>"]
if not top:
lines.append("No opportunities found today.")
return lines, False
b = top[0]
lines += [
"<b>BANKER:</b>",
"<b>" + b["home"] + " vs " + b["away"] + "</b>",
"League: " + b["league"],
"Pick: Win " + b["rec"],

"Odd: <b>" + str(b["odd"]) + "</b>",
"Time: " + b["date"] + " " + b["time"],
"Bookmakers: " + str(b["bk_count"]) + " | Volatility: " + str(b["vol"]),
"",
]
doubles = top[1:3]
if len(doubles) == 2:
combined = round(doubles[0]["odd"] * doubles[1]["odd"], 2)
lines += [
"<b>DOUBLE:</b>",
"Combined odd: <b>" + str(combined) + "</b>",
"",
]
for i, d in enumerate(doubles, 1):
lines += [
"Match " + str(i) + ": " + d["home"] + " vs " + d["away"],
"League: " + d["league"],
"Pick: Win " + d["rec"] + " | Odd: " + str(d["odd"]) + " | Time: " + d["date"] + " " + d["time"],
"",
]
else:
lines.append("Not enough matches for a double today.")
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
lines = [

"<b>Daily Analyst Report</b>",
"Date: " + now_il,
"---",
]
football_lines, has_f = format_section(ft, "FOOTBALL")
basketball_lines, has_b = format_section(bt, "BASKETBALL")
lines += football_lines
lines.append("---")
lines += basketball_lines
if not has_f and not has_b:
return "<b>Daily Report</b>\n\nNo value opportunities found today.\n\nAPI credits remaining: " + last_remaining
lines += [
"---",
"API credits remaining: <b>" + last_remaining + "</b>",
"<i>For information only. Bet responsibly.</i>",
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
bot.send_message(MY_CHAT_ID, "Error generating report: " + str(e))
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
