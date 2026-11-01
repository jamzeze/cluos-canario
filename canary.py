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
    return {"failures": {}, "alerted": [], "recovery_pending": [], "last_commit": None}


def parse_urls(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None  # 3xx vira HTTPError: redirecionamento (ex.: login Authelia) = fora


_opener = urllib.request.build_opener(_NoRedirect)


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cluos-canario"})
    try:
        with _opener.open(req, timeout=TIMEOUT) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def check(urls, get):
    results = []
    for u in urls:
        try:
            ok = 200 <= get(u) < 300
        except Exception:
            ok = False
        results.append(Result(u, ok))
    return results


def _label(key):
    return HOME_LABEL if key == HOME_KEY else key


def run_check(urls, get, state, now, home_url=None, send=None):
    """Executa um check; devolve (novo_estado, mensagens)."""
    targets = {u: u for u in urls}
    if home_url:
        targets[HOME_KEY] = home_url
    by_key = {r.url: r.ok for r in check(list(targets.values()), get)}
    failures = {}
    alerted = set(state.get("alerted", []))  # "fora" entregue e ainda fora
    pending = set(state.get("recovery_pending", []))  # "voltou" ainda nao entregue
    msgs = []
    for key, url in targets.items():
        if by_key[url]:
            if key in alerted or key in pending:
                msg = f"CluOS canario: {_label(key)} voltou"
                msgs.append(msg)
                alerted.discard(key)
                if send is None or send(msg):
                    pending.discard(key)
                else:
                    pending.add(key)  # repete no proximo run
        else:
            n = min(state.get("failures", {}).get(key, 0) + 1, 2)  # teto: estado estavel na queda longa
            failures[key] = n
            if n >= 2 and key not in alerted:
                pending.discard(key)  # nova queda: "fora" sai normalmente
                msg = f"CluOS canario: {_label(key)} fora do ar (2+ checks seguidos)"
                msgs.append(msg)
                if send is None or send(msg):
                    alerted.add(key)
    # alertas de alvos que sairam da lista nao ficam presos
    alerted &= set(targets)
    pending &= set(targets)
    new = {"failures": failures, "alerted": sorted(alerted),
           "recovery_pending": sorted(pending),
           "last_commit": state.get("last_commit")}
    return new, msgs


def active_alerts(state):
    """Alvos com 2+ falhas seguidas (notificadas ou nao). Recuperado = nao conta."""
    return sorted(k for k, n in state.get("failures", {}).items() if n >= 2)


def should_commit(prev, cur, now):
    for f in ("failures",):
        if prev.get(f) != cur.get(f):
            return True
    for f in ("alerted", "recovery_pending"):
        if sorted(prev.get(f, [])) != sorted(cur.get(f, [])):
            return True
    last = prev.get("last_commit")
    if not last:
        return True
    return now - datetime.fromisoformat(last) >= timedelta(days=7)


def send_telegram(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return True  # sem Telegram: o e-mail de falha do GitHub e o canal
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=TIMEOUT).close()
        return True
    except Exception:
        print("aviso: falha ao enviar Telegram")  # nunca imprimir a excecao (pode conter o token)
        return False


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
    cur, msgs = run_check(urls, http_get, prev, now, os.environ.get("CANARY_HOME_URL") or None, send=send_telegram)
    for m in msgs:
        print(m)
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
