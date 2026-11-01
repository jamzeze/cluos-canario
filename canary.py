"""Canario externo do CluOS: stdlib apenas, sem segredos no codigo."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

TIMEOUT = 10
STATE_FILE = "canary-state.json"
HOME_KEY = "home"
HOME_LABEL = "servidor de casa"
Result = namedtuple("Result", "url ok")


def new_state():
    return {"failures": {}, "alerted": [], "last_commit": None}


def parse_urls(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cluos-canario"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def check(urls, get):
    results = []
    for u in urls:
        try:
            ok = get(u) < 400
        except Exception:
            ok = False
        results.append(Result(u, ok))
    return results


def _label(key):
    return HOME_LABEL if key == HOME_KEY else key


def run_check(urls, get, state, now, home_url=None):
    """Executa um check; devolve (novo_estado, mensagens)."""
    targets = {u: u for u in urls}
    if home_url:
        targets[HOME_KEY] = home_url
    by_key = {r.url: r.ok for r in check(list(targets.values()), get)}
    failures = {}
    alerted = set(state.get("alerted", []))
    msgs = []
    for key, url in targets.items():
        if by_key[url]:
            if key in alerted:
                msgs.append(f"CluOS canario: {_label(key)} voltou")
                alerted.discard(key)
        else:
            n = state.get("failures", {}).get(key, 0) + 1
            failures[key] = n
            if n >= 2 and key not in alerted:
                alerted.add(key)
                msgs.append(f"CluOS canario: {_label(key)} fora do ar ({n} checks seguidos)")
    # alertas de alvos que sairam da lista nao ficam presos
    alerted &= set(targets)
    new = {"failures": failures, "alerted": sorted(alerted),
           "last_commit": state.get("last_commit")}
    return new, msgs


def active_alerts(state):
    return list(state.get("alerted", []))


def should_commit(prev, cur, now):
    if prev.get("failures") != cur.get("failures") or sorted(prev.get("alerted", [])) != sorted(cur.get("alerted", [])):
        return True
    last = prev.get("last_commit")
    if not last:
        return True
    return now - datetime.fromisoformat(last) >= timedelta(days=7)


def send_telegram(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=TIMEOUT).close()
    except Exception:
        print("aviso: falha ao enviar Telegram")  # nunca imprimir a excecao (pode conter o token)


def _output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{name}={value}\n")


def main():
    now = datetime.now(timezone.utc)
    urls = parse_urls(Path("urls.txt").read_text())
    sp = Path(STATE_FILE)
    prev = json.loads(sp.read_text()) if sp.exists() else new_state()
    cur, msgs = run_check(urls, http_get, prev, now, os.environ.get("CANARY_HOME_URL") or None)
    for m in msgs:
        print(m)
        send_telegram(m)
    commit = should_commit(prev, cur, now)
    if commit:
        cur["last_commit"] = now.isoformat()
    sp.write_text(json.dumps(cur, indent=2, sort_keys=True) + "\n")
    alerts = active_alerts(cur)
    print(f"checks: {len(urls)} urls, alertas ativos: {len(alerts)}")
    _output("commit", "true" if commit else "false")
    _output("alert", "true" if alerts else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
