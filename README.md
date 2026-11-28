# cluos-canario

Canario externo: verifica a cada 10 minutos os endpoints publicos do CluOS
(`urls.txt`) e o sinal de vida do Ryzen. Na 2a falha seguida o alvo entra em
`alertas_ativos` no `canary-state.json`, que a Soul le numa tarefa agendada do
ChatGPT e avisa o Rafael; o job tambem falha enquanto houver alerta ativo
(e-mail automatico do GitHub, como reserva). Sem Telegram e sem Hermes (27/11/2026). O estado fica em `canary-state.json`, commitado a cada
mudanca e ao menos semanalmente (evita a desativacao do cron apos 60 dias).

## Secrets (Settings > Secrets and variables > Actions)

- `CANARY_HOME_URL` (URL de saude do servidor de casa; nunca aparece em logs)

Variavel `RYZEN_BATIMENTO`: epoch gravado pelo Ryzen a cada 5 minutos.

## Testes

`pip install pytest pyyaml && python3 -m pytest -q`
