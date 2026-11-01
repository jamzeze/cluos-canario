# cluos-canario

Canario externo: verifica a cada 10 minutos os endpoints publicos do CluOS
(`urls.txt`) e o servidor de casa. Alerta no Telegram na 2a falha seguida e no
retorno; o job falha enquanto houver alerta ativo (e-mail automatico do GitHub).
Nao depende do Hermes. O estado fica em `canary-state.json`, commitado a cada
mudanca e ao menos semanalmente (evita a desativacao do cron apos 60 dias).

## Secrets (Settings > Secrets and variables > Actions)

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `CANARY_HOME_URL` (URL de saude do servidor de casa; nunca aparece em logs)

Sem os secrets do Telegram, so o e-mail de falha do GitHub avisa.

## Testes

`pip install pytest pyyaml && python3 -m pytest -q`
