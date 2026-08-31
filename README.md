# Valorant Performance Lab — Tracker + VLR

Projeto unificado com duas áreas no mesmo site:

- **Tracker.gg**: três contas, cada uma com Visão geral, Agentes e Mapas.
- **VLR.gg**: Mapas, Agentes, Top 5 e histórico de Partidas.

## Season do Tracker

`8102cd81-43a0-d0d7-bd59-47b8fe9bed1b`

Contas configuradas:

1. `elsewhere#999t`
2. `dead eyes#999t`
3. `taylorswiftfan13#lari`

## Estrutura

```text
site/                    # site estático publicado no GitHub Pages
  index.html
  assets/
  data/
    vlr.json
    tracker_accounts.json
    tracker/
      elsewhere.json
      dead-eyes.json
      taylorswiftfan13.json
scripts/
  atualizar_vlr.py       # coleta e recalcula o VLR
  puxar_tracker.py       # coletor Tracker parametrizado por conta/season
  analisar_tracker.py    # análise conservadora de agentes e mapas
  atualizar_tracker.py   # executa o Tracker para as três contas
  preparar_site.py       # sincroniza os JSONs para site/data
  atualizar_tudo.py      # executa todo o pipeline localmente
```

## Rodar o site localmente

No Windows, dê dois cliques em `iniciar.bat` ou use:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
python servidor.py
```

Abra `http://localhost:8000`.

## Atualizar os dados localmente

```powershell
python scripts/atualizar_tudo.py
```

Se o Tracker solicitar verificação humana, execute o coletor localmente com navegador visível. O workflow foi configurado para manter o último JSON válido caso uma conta falhe temporariamente.

## GitHub Pages

O workflow `.github/workflows/atualizar-site.yml`:

1. roda a cada 6 horas, em push para `main` ou manualmente;
2. atualiza o VLR;
3. coleta as três contas do Tracker;
4. gera os insights;
5. publica a pasta `site/` no GitHub Pages.

O front-end recarrega os JSONs a cada **300000 ms (5 minutos)** sem precisar recarregar a página manualmente.

## VLR com múltiplos perfis e carreira

A área VLR possui dois perfis independentes:

- `thommy` — VLR ID `51239`
- `fracarissa` — VLR ID `45269`

Cada perfil gera seu próprio arquivo em `data/vlr/<slug>.json`. Além das estatísticas por mapa/agente e partidas, o coletor lê do perfil VLR:

- total winnings / earnings;
- current teams e past teams;
- event placements, incluindo etapa, colocação, prêmio, time e ano quando disponíveis;
- lista de campeonatos derivados dos placements.

Para atualizar os dois perfis localmente:

```powershell
python scripts/atualizar_vlr.py
python scripts/preparar_site.py
python servidor.py
```

Depois abra `http://localhost:8000`, entre em **VLR** e alterne entre as abas **thommy** e **fracarissa**. A aba **Carreira** mostra os dados de earnings, times e campeonatos.

## Correção do histórico VLR (v3)
O coletor VLR agora busca o histórico completo em `/player/matches/<id>/<slug>` e percorre a paginação. Isso é necessário para perfis como `fracarissa`, em que a página principal mostra apenas os resultados recentes.

Para forçar a primeira coleta local das estatísticas VLR:

```powershell
.venv\Scripts\activate
python scripts\atualizar_vlr.py
python scripts\preparar_site.py
python servidor.py
```

Durante a coleta, o terminal deve mostrar `Página 1: ... partidas encontradas` e, para cada partida nova, `-> N mapa(s) lido(s)`. Depois confirme que `data/vlr/fracarissa.json` possui itens em `data`, `maps` e `agents`.

## VLR: coleta de partidas

O coletor VLR usa as linhas `.ovw-row` e os `divs` de estatísticas da página de cada partida, compatível com o layout atual do VLR.

Para atualizar somente fracarissa:

```powershell
python scripts\atualizar_vlr.py --player fracarissa
python scripts\preparar_site.py
python servidor.py
```

Para um teste rápido com apenas 2 partidas:

```powershell
python scripts\atualizar_vlr.py --player fracarissa --max-matches 2
```

Sem `--max-matches`, todo o histórico disponível em `/player/matches/...` é processado.
