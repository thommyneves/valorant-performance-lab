const REFRESH_MS = 300000;
const SEASON_ID = "8102cd81-43a0-d0d7-bd59-47b8fe9bed1b";

const FALLBACK_ACCOUNTS = [
  {slug:"elsewhere", riot_id:"elsewhere#999t", label:"elsewhere", profile_url:`https://tracker.gg/valorant/profile/riot/elsewhere%23999t/overview?platform=pc&playlist=competitive&season=${SEASON_ID}`, data_file:"tracker/elsewhere.json"},
  {slug:"dead-eyes", riot_id:"dead eyes#999t", label:"dead eyes", profile_url:`https://tracker.gg/valorant/profile/riot/dead%20eyes%23999t/overview?playlist=competitive&platform=pc&season=${SEASON_ID}`, data_file:"tracker/dead-eyes.json"},
  {slug:"taylorswiftfan13", riot_id:"taylorswiftfan13#lari", label:"taylorswiftfan13", profile_url:`https://tracker.gg/valorant/profile/riot/taylorswiftfan13%23lari/overview?playlist=competitive&platform=pc&season=${SEASON_ID}`, data_file:"tracker/taylorswiftfan13.json"},
];

const FALLBACK_VLR_PLAYERS = [
  {slug:"thommy", player_id:"51239", label:"thommy", profile_url:"https://www.vlr.gg/player/51239/thommy/?timespan=all", data_file:"vlr/thommy.json"},
  {slug:"fracarissa", player_id:"45269", label:"fracarissa", profile_url:"https://www.vlr.gg/player/45269/fracarissa/?timespan=all", data_file:"vlr/fracarissa.json"},
];

const state = {
  source: "tracker",
  trackerAccount: "elsewhere",
  trackerView: "overview",
  vlrPlayer: "thommy",
  vlrView: "career",
  accounts: FALLBACK_ACCOUNTS,
  tracker: {},
  vlrPlayers: FALLBACK_VLR_PLAYERS,
  vlr: {},
  vlrSearch: "",
  vlrMap: "",
  agentSearch: "",
};

const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const num = (v, d=1) => Number(v ?? 0).toLocaleString("pt-BR", {minimumFractionDigits:d, maximumFractionDigits:d});
const pct = (v, d=1) => `${num(Number(v ?? 0) * (Number(v ?? 0) <= 1 ? 100 : 1), d)}%`;
const dateText = (v) => {
  if (!v) return "aguardando coleta";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString("pt-BR", {day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"});
};
const safeUrl = (v) => /^https?:\/\//i.test(String(v ?? "")) ? String(v) : "#";

async function getJson(path) {
  const join = path.includes("?") ? "&" : "?";
  const response = await fetch(`${path}${join}t=${Date.now()}`, {cache:"no-store"});
  if (!response.ok) throw new Error(`${response.status} ${path}`);
  return response.json();
}

async function loadAll(showPulse=true) {
  const pill = $("#syncPill");
  if (showPulse) pill.className = "sync-pill loading";
  try {
    let manifest;
    try { manifest = await getJson("data/tracker_accounts.json"); }
    catch { manifest = {accounts:FALLBACK_ACCOUNTS}; }
    state.accounts = (manifest.accounts?.length ? manifest.accounts : FALLBACK_ACCOUNTS).map((a, i) => ({...FALLBACK_ACCOUNTS[i], ...a, profile_url:a.profile_url || FALLBACK_ACCOUNTS[i]?.profile_url}));

    const trackerPairs = await Promise.all(state.accounts.map(async account => {
      const file = account.data_file || `tracker/${account.slug}.json`;
      try { return [account.slug, await getJson(`data/${file}`)]; }
      catch (error) { return [account.slug, {status:"error", error:String(error), metadata:{jogador:account.riot_id, season_id:SEASON_ID}, agentes:{top_5:[],ranking_completo:[]}, mapas:{ranking:[]}, resumo:{}}]; }
    }));
    state.tracker = Object.fromEntries(trackerPairs);

    let vlrManifest;
    try { vlrManifest = await getJson("data/vlr_players.json"); }
    catch { vlrManifest = {players:FALLBACK_VLR_PLAYERS}; }
    state.vlrPlayers = (vlrManifest.players?.length ? vlrManifest.players : FALLBACK_VLR_PLAYERS).map((p, i) => ({...FALLBACK_VLR_PLAYERS[i], ...p, profile_url:p.profile_url || FALLBACK_VLR_PLAYERS[i]?.profile_url}));
    const vlrPairs = await Promise.all(state.vlrPlayers.map(async player => {
      const file = player.data_file || `vlr/${player.slug}.json`;
      try { return [player.slug, await getJson(`data/${file}`)]; }
      catch (error) { return [player.slug, {status:"error", error:String(error), maps:[],agents:[],top5:[],data:[],career:{totalWinnings:"$0",currentTeams:[],pastTeams:[],placements:[],eventsPlayed:[]},profile:{name:player.label,profile_url:player.profile_url},meta:{player:player.label,playerId:player.player_id,profileUrl:player.profile_url}}]; }
    }));
    state.vlr = Object.fromEntries(vlrPairs);

    $("#lastSync").textContent = new Date().toLocaleTimeString("pt-BR", {hour:"2-digit", minute:"2-digit"});
    pill.className = "sync-pill";
    render();
  } catch (error) {
    console.error(error);
    pill.className = "sync-pill error";
    pill.querySelector("span").textContent = "Erro de sync";
  }
}

function render() {
  $("#trackerSection").classList.toggle("active", state.source === "tracker");
  $("#vlrSection").classList.toggle("active", state.source === "vlr");
  $$(".source-btn").forEach(btn => btn.classList.toggle("active", btn.dataset.source === state.source));
  if (state.source === "tracker") renderTracker();
  else renderVlr();
}

function renderTracker() {
  renderAccountTabs();
  const account = state.accounts.find(a => a.slug === state.trackerAccount) || state.accounts[0];
  if (!account) return;
  const data = state.tracker[account.slug] || {};
  const agents = data.agentes?.ranking_completo || [];
  const maps = data.mapas?.ranking || [];
  const hasData = agents.length > 0 || maps.length > 0;

  $("#trackerPlayer").textContent = data.metadata?.jogador || account.riot_id;
  $("#trackerUpdated").textContent = dateText(data.metadata?.gerado_em);
  $("#trackerProfileLink").href = safeUrl(data.profile_url || account.profile_url);
  $("#trackerStatusText").textContent = hasData
    ? `${agents.length} agentes · ${maps.length} mapas · season atual`
    : data.status === "error" ? "A última coleta não conseguiu obter dados desta conta." : "Aguardando a primeira coleta desta season.";

  $$("#trackerSubnav button").forEach(btn => btn.classList.toggle("active", btn.dataset.trackerView === state.trackerView));
  const content = $("#trackerContent");
  if (!hasData) {
    content.innerHTML = pendingTracker(account, data);
    return;
  }
  if (state.trackerView === "agents") content.innerHTML = trackerAgents(data);
  else if (state.trackerView === "maps") content.innerHTML = trackerMaps(data);
  else content.innerHTML = trackerOverview(data);
  bindTrackerDynamic();
}

function renderAccountTabs() {
  $("#accountTabs").innerHTML = state.accounts.map(a => {
    const data = state.tracker[a.slug];
    const ready = (data?.agentes?.ranking_completo?.length || data?.mapas?.ranking?.length);
    return `<button class="account-tab ${state.trackerAccount===a.slug?"active":""}" data-account="${esc(a.slug)}"><i style="${ready?"":"opacity:.45"}"></i>${esc(a.label)}</button>`;
  }).join("");
  $$("[data-account]").forEach(btn => btn.onclick = () => { state.trackerAccount = btn.dataset.account; state.trackerView = "overview"; renderTracker(); });
}

function pendingTracker(account, data) {
  const reason = data.status === "error" && data.error ? `<br><small>Detalhe técnico: ${esc(data.error)}</small>` : "";
  return `<section class="pending"><div class="pending-icon">⌁</div><h3>Dados ainda não coletados para ${esc(account.riot_id)}</h3><p>O projeto já está configurado para a season <code>${SEASON_ID}</code>. O workflow executa o coletor desta conta e, assim que o Tracker responder, esta aba será preenchida automaticamente.${reason}</p></section>`;
}

function trackerOverview(data) {
  const top = data.agentes?.top_5 || [];
  const agents = data.agentes?.ranking_completo || [];
  const maps = data.mapas?.ranking || [];
  const best = top[0] || agents[0];
  const totalMapMatches = maps.reduce((s,m)=>s+Number(m.partidas||0),0);
  const bestMap = maps[0];
  const worstMap = maps[maps.length-1];
  return `
    <section class="metrics">
      ${metric("Agente principal", data.resumo?.melhor_agente_geral || best?.nome || "—", `${best?.partidas||0} partidas analisadas`)}
      ${metric("Melhor mapa", data.resumo?.melhor_mapa || bestMap?.mapa || "—", bestMap ? `${num(bestMap.score,0)}/100 performance score` : "sem dados")}
      ${metric("Amostra do map pool", totalMapMatches, `${maps.length} mapas no recorte`)}
      ${metric("Zona de atenção", data.resumo?.pior_mapa || worstMap?.mapa || "—", worstMap ? `${pct(worstMap.win_rate_real)} win rate` : "sem dados", true)}
    </section>
    <section class="grid-2">
      <article class="panel"><div class="panel-head"><div><p class="eyebrow">RANKING AJUSTADO</p><h3>Top 5 agentes</h3></div><span>amostra conservadora</span></div><div class="panel-body">${top.slice(0,5).map((a,i)=>agentListRow(a,i)).join("") || empty("Sem agentes elegíveis")}</div></article>
      <article class="panel"><div class="panel-head"><div><p class="eyebrow">MAP POOL</p><h3>Território de vantagem</h3></div><span>score ponderado</span></div><div class="panel-body">${maps.slice(0,6).map((m,i)=>trackerMapMini(m,i)).join("") || empty("Sem mapas")}</div></article>
    </section>
    ${best ? `<section class="insight-banner"><div class="insight-icon">✦</div><div><span>INSIGHT CENTRAL</span><h3>${esc(best.nome)} é a escolha com maior sustentação estatística.</h3><p>${esc(best.analise || "A combinação de volume e performance ajustada coloca este agente no topo do recorte.")}</p></div><div class="score-orb" style="--v:${Math.max(0,Math.min(100,Number(best.score||0)))}%">${num(best.score,0)}</div></section>` : ""}
  `;
}

function trackerAgents(data) {
  const agents = data.agentes?.ranking_completo || [];
  const q = state.agentSearch.toLowerCase();
  const filtered = agents.filter(a => `${a.nome} ${a.funcao||""}`.toLowerCase().includes(q));
  return `<div class="toolbar"><input id="trackerAgentSearch" class="search" placeholder="Buscar agente..." value="${esc(state.agentSearch)}"><div class="season-card compact" style="min-width:180px;padding:10px 14px"><span>AGENTES</span><strong style="font-size:22px">${filtered.length}</strong></div></div>
    <section class="cards-grid">${filtered.map((a,i)=>trackerAgentCard(a,i)).join("") || empty("Nenhum agente encontrado")}</section>`;
}

function trackerMaps(data) {
  const maps = data.mapas?.ranking || [];
  return `<section class="cards-grid">${maps.map((m,i)=>trackerMapCard(m,i)).join("") || empty("Sem mapas para esta conta")}</section>`;
}

function metric(label,value,note,danger=false){return `<article class="metric-card ${danger?"danger":""}"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></article>`}
function agentListRow(a,i){return `<div class="agent-list-row"><div class="rank-num">${String(i+1).padStart(2,"0")}</div><div class="name-wrap"><strong>${esc(a.nome)}</strong><small>${esc(a.funcao||a.confianca||"")}</small></div><div class="bar"><i style="width:${Math.max(2,Math.min(100,Number(a.score||0)))}%"></i></div><div class="score-wrap"><strong>${num(a.score,1)}</strong><small>${esc(a.partidas)} partidas</small></div></div>`}
function trackerMapMini(m,i){return `<div class="map-mini-row"><div><strong>${String(i+1).padStart(2,"0")} · ${esc(m.mapa)}</strong><small>${esc(m.melhor_agente_estimado?.agente||"pick indisponível")} · ${m.partidas||0} partidas</small></div><div class="wr-pill">${pct(m.win_rate_real)}</div><div class="map-score">${num(m.score,0)}</div></div>`}
function trackerAgentCard(a,i){const s=a.stats_reais||{};return `<article class="data-card"><div class="card-kicker"><span>#${String(i+1).padStart(2,"0")} · ${esc(a.funcao||"AGENT")}</span><span>${esc(a.confianca||"")} conf.</span></div><h3>${esc(a.nome)}</h3><p>${a.partidas||0} partidas · ranking ajustado por amostra</p><div class="stat-grid"><div class="stat"><b>${pct(s.win_rate)}</b><span>WIN RATE</span></div><div class="stat"><b>${num(s.kd,2)}</b><span>K/D</span></div><div class="stat"><b>${num(s.acs,0)}</b><span>ACS</span></div><div class="stat"><b>${num(s.adr,0)}</b><span>ADR</span></div><div class="stat"><b>${pct(s.kast)}</b><span>KAST</span></div><div class="stat"><b>${num(a.fator_confiabilidade,2)}</b><span>CONF. FACTOR</span></div></div><div class="card-score"><small>PERFORMANCE SCORE</small><strong>${num(a.score,1)}</strong></div></article>`}
function trackerMapCard(m,i){return `<article class="data-card"><div class="card-kicker"><span>#${String(i+1).padStart(2,"0")} · MAP</span><span>${esc(m.confianca||"")} conf.</span></div><h3>${esc(m.mapa)}</h3><p>${m.vitorias||0}V · ${m.derrotas||0}D · ${m.partidas||0} partidas</p><div class="stat-grid"><div class="stat"><b>${pct(m.win_rate_real)}</b><span>WIN RATE</span></div><div class="stat"><b>${num(m.stats_ajustados?.kd,2)}</b><span>K/D AJUST.</span></div><div class="stat"><b>${num(m.stats_ajustados?.acs,0)}</b><span>ACS AJUST.</span></div></div><div class="card-score"><div><small>MELHOR PICK ESTIMADO</small><b style="display:block;margin-top:4px">${esc(m.melhor_agente_estimado?.agente||"—")}</b></div><strong>${num(m.score,0)}</strong></div></article>`}

function bindTrackerDynamic(){
  const input = $("#trackerAgentSearch");
  if (input) input.oninput = e => { state.agentSearch = e.target.value; const pos=e.target.selectionStart; renderTracker(); const n=$("#trackerAgentSearch"); if(n){n.focus();n.setSelectionRange(pos,pos);} };
}

function renderVlrPlayerTabs() {
  $("#vlrPlayerTabs").innerHTML = state.vlrPlayers.map(player => {
    const db = state.vlr[player.slug];
    const ready = (db?.data?.length || db?.career?.placements?.length || db?.profile?.current_teams?.length);
    return `<button class="account-tab ${state.vlrPlayer===player.slug?"active":""}" data-vlr-player="${esc(player.slug)}"><i style="${ready?"":"opacity:.45"}"></i>${esc(player.label)}</button>`;
  }).join("");
  $$('[data-vlr-player]').forEach(btn => btn.onclick = () => {
    state.vlrPlayer = btn.dataset.vlrPlayer;
    state.vlrView = "career";
    state.vlrSearch = "";
    state.vlrMap = "";
    state.agentSearch = "";
    renderVlr();
  });
}

function renderVlr() {
  renderVlrPlayerTabs();
  const player = state.vlrPlayers.find(p => p.slug === state.vlrPlayer) || state.vlrPlayers[0];
  if (!player) return;
  const db = state.vlr[player.slug] || {maps:[],agents:[],top5:[],data:[],career:{},profile:{},meta:{}};
  const profile = db.profile || {};
  const career = db.career || {};

  $("#vlrPlayer").textContent = profile.name || db.meta?.player || player.label;
  $("#vlrUpdated").textContent = dateText(db.meta?.updatedAt);
  const mirror = $("#vlrUpdatedMirror"); if (mirror) mirror.textContent = dateText(db.meta?.updatedAt);
  $("#vlrProfileName").textContent = profile.name || player.label;
  $("#vlrProfileMeta").textContent = [profile.real_name, profile.country, `${career.totalWinnings || profile.total_winnings || "$0"} winnings`].filter(Boolean).join(" · ");
  $("#vlrProfileLink").href = safeUrl(profile.profile_url || db.meta?.profileUrl || player.profile_url);
  $$("#vlrSubnav button").forEach(btn => btn.classList.toggle("active", btn.dataset.vlrView === state.vlrView));

  const content = $("#vlrContent");
  if (state.vlrView === "career") content.innerHTML = vlrCareer(db);
  else if (state.vlrView === "agents") content.innerHTML = vlrAgents(db);
  else if (state.vlrView === "top") content.innerHTML = vlrTop(db);
  else if (state.vlrView === "data") content.innerHTML = vlrData(db);
  else content.innerHTML = vlrMaps(db);
  bindVlrDynamic(db);
}

function vlrCareer(db){
  const profile=db.profile||{}, career=db.career||{};
  const current=career.currentTeams||profile.current_teams||[];
  const past=career.pastTeams||profile.past_teams||[];
  const placements=career.placements||profile.event_placements||[];
  const events=career.eventsPlayed||[...new Set(placements.map(p=>p.event).filter(Boolean))];
  const prizePlacements=placements.filter(p=>p.prize);
  const bestPlacement=placements.find(p=>/^1st$/i.test(p.placement||"")) || placements[0];
  return `
    <section class="metrics career-metrics">
      ${metric("Total winnings",career.totalWinnings||profile.total_winnings||"$0",`${prizePlacements.length} colocações com prêmio`)}
      ${metric("Campeonatos",events.length,`${placements.length} resultados de placement`)}
      ${metric("Times atuais",current.length,current.map(t=>t.name).filter(Boolean).join(" · ")||"sem time listado")}
      ${metric("Melhor colocação",bestPlacement?.placement||"—",bestPlacement?`${bestPlacement.event}${bestPlacement.series?` · ${bestPlacement.series}`:""}`:"sem placement")}
    </section>
    <section class="career-grid">
      <article class="panel career-panel">
        <div class="panel-head"><div><p class="eyebrow">TEAM HISTORY</p><h3>Times</h3></div><span>${current.length+past.length} organizações</span></div>
        <div class="panel-body team-groups">
          <div class="career-group"><div class="career-group-title"><span>ATUAIS</span><b>${current.length}</b></div>${current.map(teamCard).join("")||empty("Nenhum time atual listado")}</div>
          <div class="career-group"><div class="career-group-title"><span>ANTERIORES</span><b>${past.length}</b></div>${past.map(teamCard).join("")||empty("Nenhum time anterior listado")}</div>
        </div>
      </article>
      <article class="panel career-panel placements-panel">
        <div class="panel-head"><div><p class="eyebrow">EVENT PLACEMENTS</p><h3>Campeonatos e colocações</h3></div><span>${placements.length} registros</span></div>
        <div class="placement-list">${placements.map(placementCard).join("")||empty("Nenhuma colocação encontrada")}</div>
      </article>
    </section>`;
}

function teamCard(team){
  const logo = safeUrl(team.logo||"");
  const image = logo !== "#" ? `<img src="${esc(logo)}" alt="" loading="lazy">` : `<span class="team-avatar">V</span>`;
  const meta=[team.status,team.dates].filter(Boolean).join(" · ");
  const content=`${image}<div><strong>${esc(team.name||"Time")}</strong>${meta?`<small>${esc(meta)}</small>`:""}</div>`;
  return safeUrl(team.url)!=="#" ? `<a class="team-row" href="${safeUrl(team.url)}" target="_blank" rel="noopener">${content}<span>↗</span></a>` : `<div class="team-row">${content}<span></span></div>`;
}

function placementCard(p){
  const details=[p.series,p.team].filter(Boolean).join(" · ");
  const prize=p.prize?`<b class="placement-prize">${esc(p.prize)}</b>`:"";
  const inner=`<div class="placement-main"><span class="placement-position">${esc(p.placement||"—")}</span><div><strong>${esc(p.event||"Evento")}</strong><small>${esc(details||"VLR event placement")}</small></div></div><div class="placement-side">${prize}<span>${esc(p.year||"")}</span></div>`;
  return safeUrl(p.url)!=="#" ? `<a class="placement-row" href="${safeUrl(p.url)}" target="_blank" rel="noopener">${inner}</a>` : `<div class="placement-row">${inner}</div>`;
}

function vlrMaps(db){
  const maps=db.maps||[], agents=db.agents||[], data=db.data||[];
  const best=maps[0], most=[...agents].sort((a,b)=>b.games-a.games)[0], hs=[...agents].sort((a,b)=>b.hs-a.hs)[0];
  if (!data.length) return `<section class="pending"><div class="pending-icon">⌁</div><h3>Stats de partidas aguardando coleta</h3><p>Os dados de carreira já estão disponíveis. Rode <code>python scripts/atualizar_vlr.py</code> para buscar as partidas deste perfil e preencher mapas, agentes, Top 5 e histórico.</p></section>`;
  return `<section class="metrics">${metric("Mapas analisados",maps.length,`${data.length} registros na base`)}${metric("Maior rating",best?num(best.rating,2):"—",best?`${best.agent} em ${best.map}`:"sem dados")}${metric("Mais utilizado",most?.agent||"—",most?`${most.games} mapas jogados`:"sem dados")}${metric("Melhor HS%",hs?.agent||"—",hs?pct(hs.hs):"sem dados")}</section>
  <section class="cards-grid">${maps.map((m,i)=>`<article class="data-card map-card-click" data-vlr-map="${esc(m.map)}"><div class="card-kicker"><span>#${String(i+1).padStart(2,"0")} · MAP</span><span>${m.games} ${m.games===1?"jogo":"jogos"}</span></div><h3>${esc(m.map)}</h3><p>Melhor rating médio com ${esc(m.agent)}</p><div class="stat-grid"><div class="stat"><b>${num(m.rating,2)}</b><span>RATING</span></div><div class="stat"><b>${num(m.acs,0)}</b><span>ACS</span></div><div class="stat"><b>${num(Number(m.k)/Math.max(Number(m.d),.01),2)}</b><span>K:D</span></div></div><div class="open-hint"><span>Ver partidas do mapa</span><span>→</span></div></article>`).join("")||empty("Nenhum mapa")}</section>`;
}

function vlrAgents(db){
  const q=state.agentSearch.toLowerCase();
  const rows=(db.agents||[]).filter(a=>`${a.agent} ${a.bestMap}`.toLowerCase().includes(q));
  if (!(db.data||[]).length) return vlrMaps(db);
  return `<div class="toolbar"><input id="vlrAgentSearch" class="search" placeholder="Buscar agente ou melhor mapa..." value="${esc(state.agentSearch)}"><span class="pill">${rows.length} agentes</span></div><div class="table-card"><div class="table-wrap"><table><thead><tr><th>Agente</th><th>Mapas</th><th>Rating</th><th>ACS</th><th>K:D</th><th>HS%</th><th>FK:FD</th><th>Melhor mapa</th><th>Rating mapa</th></tr></thead><tbody>${rows.map(a=>`<tr><td class="name-cell">${esc(a.agent)}</td><td>${a.games}</td><td><span class="pill ${a.rating>=1?"good":"bad"}">${num(a.rating,3)}</span></td><td>${num(a.acs,1)}</td><td><span class="pill ${a.kd>=1?"good":"bad"}">${num(a.kd,2)}</span></td><td>${pct(a.hs)}</td><td>${num(a.fkfd,2)}</td><td>${esc(a.bestMap)}</td><td>${num(a.bestMapRating,2)}</td></tr>`).join("")||`<tr><td colspan="9" class="empty">Nenhum agente encontrado.</td></tr>`}</tbody></table></div></div>`;
}

function vlrTop(db){
  if (!(db.data||[]).length) return vlrMaps(db);
  return `<div class="rank-list">${(db.top5||[]).map(a=>`<article class="rank-card"><div class="rank-big">${String(a.rank).padStart(2,"0")}</div><div><h3>${esc(a.agent)}</h3><p>${a.games} mapas · melhor em ${esc(a.bestMap)} · score ${num(a.score,1)}/100</p><div class="rank-stats"><span>Rating ${num(a.rating,3)}</span><span>ACS ${num(a.acs,1)}</span><span>K:D ${num(a.kd,2)}</span><span>FK:FD ${num(a.fkfd,2)}</span></div></div><div><p>${esc(a.why)}</p><div class="bar" style="margin-top:12px"><i style="width:${Math.max(2,Math.min(100,Number(a.score||0)))}%"></i></div></div></article>`).join("")||empty("Top 5 indisponível")}</div>`;
}

function vlrData(db){
  if (!(db.data||[]).length) return vlrMaps(db);
  const maps=[...new Set((db.data||[]).map(r=>r.map))].sort();
  const q=state.vlrSearch.toLowerCase(), selected=state.vlrMap;
  const rows=(db.data||[]).filter(r=>(!selected||r.map===selected)&&`${r.map} ${r.agent}`.toLowerCase().includes(q));
  return `<div class="toolbar"><input id="vlrSearch" class="search" placeholder="Buscar mapa ou agente..." value="${esc(state.vlrSearch)}"><select id="vlrMapFilter" class="select"><option value="">Todos os mapas</option>${maps.map(m=>`<option ${m===selected?"selected":""}>${esc(m)}</option>`).join("")}</select></div><div class="table-card"><div class="table-wrap"><table><thead><tr><th>#</th><th>Mapa</th><th>Agente</th><th>Rating</th><th>ACS</th><th>K</th><th>D</th><th>A</th><th>HS%</th><th>FK</th><th>FD</th><th>VLR</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.id}</td><td class="name-cell">${esc(r.map)}</td><td>${esc(r.agent)}</td><td><span class="pill ${r.rating>=1?"good":"bad"}">${num(r.rating,2)}</span></td><td>${r.acs}</td><td>${r.k}</td><td>${r.d}</td><td>${r.a}</td><td>${pct(r.hs)}</td><td>${r.fk}</td><td>${r.fd}</td><td><a class="match-link" href="${safeUrl(r.url)}" target="_blank" rel="noopener">Abrir ↗</a></td></tr>`).join("")||`<tr><td colspan="12" class="empty">Nenhuma partida encontrada.</td></tr>`}</tbody></table></div></div>`;
}

function bindVlrDynamic(db){
  $$('[data-vlr-map]').forEach(card => card.onclick = () => openVlrMap(db, card.dataset.vlrMap));
  const agentInput=$("#vlrAgentSearch"); if(agentInput) agentInput.oninput=e=>{state.agentSearch=e.target.value;const p=e.target.selectionStart;renderVlr();const n=$("#vlrAgentSearch");if(n){n.focus();n.setSelectionRange(p,p)}};
  const search=$("#vlrSearch"); if(search) search.oninput=e=>{state.vlrSearch=e.target.value;const p=e.target.selectionStart;renderVlr();const n=$("#vlrSearch");if(n){n.focus();n.setSelectionRange(p,p)}};
  const mapFilter=$("#vlrMapFilter"); if(mapFilter) mapFilter.onchange=e=>{state.vlrMap=e.target.value;renderVlr()};
}

function openVlrMap(db,map){
  const rows=(db.data||[]).filter(r=>r.map===map).sort((a,b)=>b.rating-a.rating);
  $("#modalTitle").textContent=map;
  $("#modalSubtitle").textContent=`${rows.length} ${rows.length===1?"partida":"partidas"} · ordenadas por rating`;
  $("#modalBody").innerHTML=`<table><thead><tr><th>#</th><th>Agente</th><th>Rating</th><th>ACS</th><th>K</th><th>D</th><th>A</th><th>K:D</th><th>HS%</th><th>FK</th><th>FD</th><th>VLR</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td>${i+1}</td><td class="name-cell">${esc(r.agent)}</td><td>${num(r.rating,2)}</td><td>${r.acs}</td><td>${r.k}</td><td>${r.d}</td><td>${r.a}</td><td>${num(Number(r.k)/Math.max(Number(r.d),.01),2)}</td><td>${pct(r.hs)}</td><td>${r.fk}</td><td>${r.fd}</td><td><a class="match-link" href="${safeUrl(r.url)}" target="_blank" rel="noopener">Abrir ↗</a></td></tr>`).join("")}</tbody></table>`;
  $("#mapDialog").showModal();
}
function empty(text){return `<div class="empty">${esc(text)}</div>`}

$$(".source-btn").forEach(btn => btn.onclick = () => { state.source = btn.dataset.source; state.agentSearch=""; render(); });
$$("#trackerSubnav button").forEach(btn => btn.onclick = () => { state.trackerView = btn.dataset.trackerView; state.agentSearch=""; renderTracker(); });
$$("#vlrSubnav button").forEach(btn => btn.onclick = () => { state.vlrView = btn.dataset.vlrView; state.agentSearch=""; state.vlrSearch=""; state.vlrMap=""; renderVlr(); });
$("#refreshBtn").onclick = () => loadAll(true);
$("#modalClose").onclick = () => $("#mapDialog").close();
$("#mapDialog").addEventListener("click", e => { if(e.target === $("#mapDialog")) $("#mapDialog").close(); });

loadAll(false);
setInterval(() => loadAll(false), REFRESH_MS);
