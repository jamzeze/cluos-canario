import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import canary

HOME = "https://casa-secreta.example.invalid/health"
U = "https://a.example/health"
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def run(state, down, urls=(U,), home=None):
    get = lambda u: (500 if u in down else 200)
    return canary.run_check(list(urls), get, state, NOW, home_url=home)


def test_single_failure_does_not_alert():
    st, msgs = run(canary.new_state(), {U})
    assert msgs == [] and st["failures"][U] == 1 and canary.active_alerts(st) == []


def test_two_failures_alert_once():
    st, _ = run(canary.new_state(), {U})
    st, msgs = run(st, {U})
    assert len(msgs) == 1 and U in msgs[0]
    st, msgs = run(st, {U})
    assert msgs == [] and canary.active_alerts(st) == [U]


def test_recovery_alerts_voltou():
    st, _ = run(canary.new_state(), {U})
    st, _ = run(st, {U})
    st, msgs = run(st, set())
    assert len(msgs) == 1 and "voltou" in msgs[0]
    assert canary.active_alerts(st) == [] and st["failures"].get(U, 0) == 0


def test_recovery_before_alert_is_silent():
    st, _ = run(canary.new_state(), {U})
    st, msgs = run(st, set())
    assert msgs == []


def test_exception_counts_as_down():
    def boom(u):
        raise OSError("x")
    r = canary.check([U], boom)
    assert not r[0].ok


def test_home_url_never_leaks():
    st, _ = run(canary.new_state(), {HOME}, urls=(), home=HOME)
    st, msgs = run(st, {HOME}, urls=(), home=HOME)
    assert msgs and "servidor de casa" in msgs[0]
    blob = json.dumps(st) + "".join(msgs)
    assert HOME not in blob and "casa-secreta" not in blob
    assert "home" in st["failures"]
    st, msgs = run(st, set(), urls=(), home=HOME)
    assert "servidor de casa" in msgs[0] and "casa-secreta" not in "".join(msgs)


def test_should_commit():
    prev = {"failures": {}, "alerted": [], "last_commit": NOW.isoformat()}
    same = dict(prev)
    assert not canary.should_commit(prev, same, NOW + timedelta(days=6))
    assert canary.should_commit(prev, same, NOW + timedelta(days=7))
    assert canary.should_commit(prev, {**prev, "failures": {U: 1}}, NOW)
    assert canary.should_commit(prev, {**prev, "alerted": [U]}, NOW)


def test_parse_urls():
    assert canary.parse_urls("# c\n\n" + U + "\n  \n") == [U]


def test_workflow():
    wf = yaml.safe_load(Path(".github/workflows/canary.yml").read_text())
    assert wf["permissions"]["contents"] == "write"
    on = wf.get(True, wf.get("on"))
    assert on["schedule"][0]["cron"] == "*/10 * * * *" and "workflow_dispatch" in on
    assert "concurrency" in wf
    steps = wf["jobs"]["canary"]["steps"]
    commit = [s for s in steps if "canary-state.json" in s.get("run", "") and "git commit" in s.get("run", "")]
    assert commit and "chore: canary state" in commit[0]["run"]
    assert "should_commit" in commit[0].get("if", "") or "commit" in commit[0].get("if", "")
