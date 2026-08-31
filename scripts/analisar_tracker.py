import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev


# Todos os caminhos padrao sao calculados a partir da pasta deste script.
# Isso permite executar o comando mesmo quando o terminal estiver em outro local.
PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_ENTRADA_PADRAO = PASTA_PROJETO / "dados_tracker" / "tracker_dados.json"
ARQUIVO_SAIDA_PADRAO = PASTA_PROJETO / "dados_tracker" / "tracker_insights.json"
ARQUIVO_DASHBOARD_PADRAO = (
    PASTA_PROJETO
    / "elsewhere-performance-lab-source"
    / "public"
    / "tracker_insights.json"
)

# Equivale a quantas partidas a media geral pesa antes de confiarmos totalmente
# na amostra individual. Aumente para tornar o ranking mais conservador.
FORCA_DA_MEDIA = 10.0
MINIMO_PARTIDAS_TOP_5 = 5

# Pesos da nota dos agentes. A soma deve ser 1.
PESOS_AGENTES = {
    "win_rate": 0.35,
    "kd": 0.25,
    "adr": 0.15,
    "acs": 0.15,
    "kast": 0.10,
}

# Pesos da nota dos mapas.
PESOS_MAPAS = {
    "win_rate": 0.55,
    "kd": 0.20,
    "adr": 0.10,
    "acs": 0.10,
    "dd_delta": 0.05,
}


def numero(valor, padrao=0.0):
    if valor is None or valor == "":
        return padrao
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip().replace("%", "").replace("+", "")
    try:
        return float(texto)
    except ValueError:
        return padrao


def inteiro(valor, padrao=0):
    return int(round(numero(valor, padrao)))


def arredondar(valor, casas=2):
    return round(float(valor), casas)


def media_ponderada(registros, campo, campo_peso):
    pares = [
        (numero(item.get(campo)), max(numero(item.get(campo_peso)), 0))
        for item in registros
        if item.get(campo) not in (None, "")
    ]
    peso_total = sum(peso for _, peso in pares)

    if peso_total == 0:
        valores = [valor for valor, _ in pares]
        return mean(valores) if valores else 0.0

    return sum(valor * peso for valor, peso in pares) / peso_total


def regressao_media(valor, partidas, media_geral, forca=FORCA_DA_MEDIA):
    """Puxa amostras pequenas para a media e preserva amostras grandes."""
    partidas = max(float(partidas), 0.0)
    return (partidas * valor + forca * media_geral) / (partidas + forca)


def normalizar_z(valores):
    if not valores:
        return []

    desvio = pstdev(valores)
    if desvio == 0:
        return [0.0] * len(valores)

    media = mean(valores)
    return [(valor - media) / desvio for valor in valores]


def confianca_amostra(partidas):
    if partidas >= 25:
        return "alta"
    if partidas >= 10:
        return "media"
    if partidas >= 5:
        return "baixa"
    return "muito_baixa"


def observacao_amostra(partidas):
    if partidas >= 25:
        return "Amostra consistente; os numeros individuais recebem grande peso."
    if partidas >= 10:
        return "Amostra razoavel, mas ainda sujeita a variacao."
    if partidas >= 5:
        return "Amostra pequena; a nota foi puxada para a media geral."
    return "Amostra muito pequena; resultados extremos foram fortemente penalizados."


def analisar_agentes(agentes):
    if not agentes:
        return {"top_5": [], "ranking_completo": [], "medias_gerais": {}}

    campos = {
        "win_rate": "Win %",
        "kd": "K/D",
        "adr": "ADR",
        "acs": "ACS",
        "kast": "KAST",
    }
    medias = {
        nome: media_ponderada(agentes, campo, "Matches")
        for nome, campo in campos.items()
    }

    processados = []
    for agente in agentes:
        partidas = inteiro(agente.get("Matches"))
        ajustados = {
            nome: regressao_media(
                numero(agente.get(campo)), partidas, medias[nome]
            )
            for nome, campo in campos.items()
        }
        processados.append(
            {
                "nome": agente.get("Agent", "Desconhecido"),
                "funcao": agente.get("Funcao"),
                "partidas": partidas,
                "confianca": confianca_amostra(partidas),
                "stats_reais": {
                    "win_rate": numero(agente.get("Win %")),
                    "kd": numero(agente.get("K/D")),
                    "adr": numero(agente.get("ADR")),
                    "acs": numero(agente.get("ACS")),
                    "kast": numero(agente.get("KAST")),
                },
                "stats_ajustados": ajustados,
            }
        )

    # Compara cada stat ajustado em desvios-padrao e aplica os pesos definidos.
    z_por_campo = {}
    for campo in campos:
        z_por_campo[campo] = normalizar_z(
            [item["stats_ajustados"][campo] for item in processados]
        )

    notas_brutas = []
    for indice, item in enumerate(processados):
        nota_estatistica = sum(
            PESOS_AGENTES[campo] * z_por_campo[campo][indice]
            for campo in PESOS_AGENTES
        )
        # Reduz diretamente a distancia da nota em relacao a media quando a
        # amostra e pequena. Assim, um 100% em uma unica partida nao supera
        # automaticamente um desempenho bom mantido em dezenas de partidas.
        confiabilidade = math.sqrt(
            item["partidas"] / (item["partidas"] + FORCA_DA_MEDIA)
        ) if item["partidas"] > 0 else 0.0
        nota = nota_estatistica * confiabilidade
        item["fator_confiabilidade"] = arredondar(confiabilidade, 4)
        item["elegivel_top_5"] = item["partidas"] >= MINIMO_PARTIDAS_TOP_5
        notas_brutas.append(nota)

    menor = min(notas_brutas)
    maior = max(notas_brutas)
    amplitude = maior - menor

    for item, nota in zip(processados, notas_brutas):
        item["score"] = arredondar(
            50.0 if amplitude == 0 else 100.0 * (nota - menor) / amplitude,
            2,
        )
        item["stats_ajustados"] = {
            chave: arredondar(valor, 2)
            for chave, valor in item["stats_ajustados"].items()
        }
        item["analise"] = gerar_analise_agente(item, medias)

    processados.sort(key=lambda item: (-item["score"], -item["partidas"]))
    for posicao, item in enumerate(processados, start=1):
        item["posicao_ranking_completo"] = posicao

    elegiveis = [item for item in processados if item["elegivel_top_5"]]
    top_5 = []
    for posicao, item in enumerate(elegiveis[:5], start=1):
        copia = dict(item)
        copia["posicao"] = posicao
        top_5.append(copia)
    return {
        "top_5": top_5,
        "ranking_completo": processados,
        "criterio_top_5": {
            "minimo_partidas": MINIMO_PARTIDAS_TOP_5,
            "motivo": (
                "Agentes abaixo do minimo permanecem no ranking completo, "
                "mas nao entram no Top 5 por insuficiencia de amostra."
            ),
        },
        "medias_gerais": {
            chave: arredondar(valor, 2) for chave, valor in medias.items()
        },
    }


def gerar_analise_agente(item, medias):
    stats = item["stats_ajustados"]
    destaques = []

    nomes = {
        "win_rate": "taxa de vitoria",
        "kd": "K/D",
        "adr": "ADR",
        "acs": "ACS",
        "kast": "KAST",
    }
    for campo in ("win_rate", "kd", "adr", "acs", "kast"):
        if stats[campo] > medias[campo] * 1.03:
            destaques.append(nomes[campo])

    if destaques:
        desempenho = "Destaques ajustados acima da media: " + ", ".join(destaques) + "."
    else:
        desempenho = "Depois do ajuste de amostra, nao possui stat claramente acima da media."

    return desempenho + " " + observacao_amostra(item["partidas"])


def limite_inferior_wilson(vitorias, partidas, z=1.645):
    """Limite inferior de 90%: premia taxa alta sem ignorar o tamanho da amostra."""
    if partidas <= 0:
        return 0.0
    p = vitorias / partidas
    denominador = 1 + (z * z / partidas)
    centro = p + (z * z / (2 * partidas))
    margem = z * math.sqrt((p * (1 - p) + z * z / (4 * partidas)) / partidas)
    return (centro - margem) / denominador


PADRAO_TOP_AGENT = re.compile(r"\s*([^;(]+?)\s*\(([-+]?\d+(?:\.\d+)?)%\)\s*")


def ler_top_agents(texto):
    agentes = []
    for parte in str(texto or "").split(";"):
        correspondencia = PADRAO_TOP_AGENT.fullmatch(parte.strip())
        if correspondencia:
            agentes.append(
                {
                    "agente": correspondencia.group(1).strip(),
                    "taxa_exibida": float(correspondencia.group(2)),
                }
            )
    return agentes


def melhor_agente_do_mapa(mapa, partidas_globais):
    candidatos = ler_top_agents(mapa.get("Top Agents"))
    taxa_mapa = numero(mapa.get("Win %"))
    partidas_mapa = inteiro(mapa.get("Wins")) + inteiro(mapa.get("Losses"))

    for candidato in candidatos:
        # O Tracker nao fornece, neste arquivo, partidas do agente naquele mapa.
        # Usa-se uma amostra-proxy conservadora, limitada pela quantidade global
        # do agente e pelo total de partidas do mapa.
        globais = partidas_globais.get(candidato["agente"], 0)
        amostra_proxy = min(globais, partidas_mapa)
        candidato["amostra_proxy"] = amostra_proxy
        candidato["chance_ajustada"] = regressao_media(
            candidato["taxa_exibida"],
            amostra_proxy,
            taxa_mapa,
            forca=6.0,
        )

    candidatos.sort(
        key=lambda item: (-item["chance_ajustada"], -item["amostra_proxy"])
    )

    if not candidatos:
        return {
            "agente": None,
            "chance_estimada": None,
            "confianca": "indisponivel",
            "nota": "A pagina nao forneceu Top Agents para este mapa.",
        }

    melhor = candidatos[0]
    return {
        "agente": melhor["agente"],
        "chance_estimada": arredondar(melhor["chance_ajustada"], 2),
        "taxa_exibida_tracker": arredondar(melhor["taxa_exibida"], 2),
        "confianca": confianca_amostra(melhor["amostra_proxy"]),
        "outros_candidatos": [
            {
                "agente": item["agente"],
                "chance_estimada": arredondar(item["chance_ajustada"], 2),
                "taxa_exibida_tracker": arredondar(item["taxa_exibida"], 2),
            }
            for item in candidatos[1:]
        ],
        "nota": (
            "Estimativa conservadora. O arquivo do Tracker nao informa quantas "
            "partidas cada agente jogou especificamente neste mapa; a confianca "
            "usa uma amostra-proxy limitada pelas partidas globais do agente."
        ),
    }


def analisar_mapas(mapas, agentes):
    if not mapas:
        return []

    partidas_globais = {
        item.get("Agent"): inteiro(item.get("Matches")) for item in agentes
    }
    campos = {
        "win_rate": "Win %",
        "kd": "K/D",
        "adr": "ADR",
        "acs": "ACS",
        "dd_delta": "DDΔ",
    }
    medias = {}
    for nome, campo in campos.items():
        valores = [numero(item.get(campo)) for item in mapas]
        medias[nome] = mean(valores) if valores else 0.0

    processados = []
    for mapa in mapas:
        vitorias = inteiro(mapa.get("Wins"))
        derrotas = inteiro(mapa.get("Losses"))
        partidas = vitorias + derrotas
        ajustados = {
            nome: regressao_media(numero(mapa.get(campo)), partidas, medias[nome])
            for nome, campo in campos.items()
        }
        ajustados["win_rate_conservador"] = limite_inferior_wilson(
            vitorias, partidas
        ) * 100

        processados.append(
            {
                "mapa": mapa.get("Map Name") or mapa.get("Map"),
                "partidas": partidas,
                "vitorias": vitorias,
                "derrotas": derrotas,
                "win_rate_real": numero(mapa.get("Win %")),
                "win_rate_conservador": ajustados["win_rate_conservador"],
                "confianca": confianca_amostra(partidas),
                "stats_ajustados": ajustados,
                "melhor_agente_estimado": melhor_agente_do_mapa(
                    mapa, partidas_globais
                ),
            }
        )

    z_por_campo = {}
    for campo in PESOS_MAPAS:
        origem = "win_rate_conservador" if campo == "win_rate" else campo
        z_por_campo[campo] = normalizar_z(
            [item["stats_ajustados"][origem] for item in processados]
        )

    notas = []
    for indice in range(len(processados)):
        notas.append(
            sum(
                PESOS_MAPAS[campo] * z_por_campo[campo][indice]
                for campo in PESOS_MAPAS
            )
        )

    menor, maior = min(notas), max(notas)
    amplitude = maior - menor
    for item, nota in zip(processados, notas):
        item["score"] = arredondar(
            50 if amplitude == 0 else 100 * (nota - menor) / amplitude, 2
        )
        item["win_rate_conservador"] = arredondar(
            item["win_rate_conservador"], 2
        )
        item["stats_ajustados"] = {
            chave: arredondar(valor, 2)
            for chave, valor in item["stats_ajustados"].items()
        }

    processados.sort(key=lambda item: (-item["score"], -item["partidas"]))
    for posicao, item in enumerate(processados, start=1):
        item["posicao"] = posicao

    return processados


def gerar_insights(dados):
    agentes = dados.get("agentes", [])
    mapas = dados.get("mapas", [])
    analise_agentes = analisar_agentes(agentes)
    ranking_mapas = analisar_mapas(mapas, agentes)

    return {
        "metadata": {
            "jogador": dados.get("jogador"),
            "season_id": dados.get("season_id"),
            "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
            "quantidade_agentes": len(agentes),
            "quantidade_mapas": len(mapas),
        },
        "metodologia": {
            "objetivo": (
                "Comparar desempenho sem deixar amostras pequenas dominarem "
                "o ranking por causa de resultados extremos."
            ),
            "agentes": {
                "tecnica": "regressao a media + normalizacao z + score ponderado",
                "forca_da_media_em_partidas": FORCA_DA_MEDIA,
                "minimo_partidas_top_5": MINIMO_PARTIDAS_TOP_5,
                "pesos": PESOS_AGENTES,
            },
            "mapas": {
                "tecnica": (
                    "limite inferior de Wilson para win rate + regressao a media "
                    "+ score ponderado"
                ),
                "pesos": PESOS_MAPAS,
            },
            "limitacao_agente_por_mapa": (
                "Top Agents nao informa a quantidade de partidas de cada agente "
                "em cada mapa. A chance por mapa e uma estimativa conservadora, "
                "nao uma probabilidade causal ou garantia de resultado."
            ),
        },
        "agentes": analise_agentes,
        "mapas": {"ranking": ranking_mapas},
        "resumo": {
            "melhor_agente_geral": (
                analise_agentes["top_5"][0]["nome"]
                if analise_agentes["top_5"]
                else None
            ),
            "melhor_mapa": ranking_mapas[0]["mapa"] if ranking_mapas else None,
            "pior_mapa": ranking_mapas[-1]["mapa"] if ranking_mapas else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analisa o JSON gerado pelo coletor do Tracker.gg."
    )
    parser.add_argument(
        "entrada", nargs="?", type=Path, default=ARQUIVO_ENTRADA_PADRAO
    )
    parser.add_argument(
        "-o", "--saida", type=Path, default=ARQUIVO_SAIDA_PADRAO
    )
    parser.add_argument(
        "--dashboard",
        type=Path,
        default=ARQUIVO_DASHBOARD_PADRAO,
        help=(
            "Caminho da copia usada pelo dashboard. Por padrao: "
            "elsewhere-performance-lab-source/public/tracker_insights.json"
        ),
    )
    argumentos = parser.parse_args()

    if not argumentos.entrada.exists():
        raise SystemExit(f"Arquivo nao encontrado: {argumentos.entrada}")

    with argumentos.entrada.open(encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    resultado = gerar_insights(dados)
    conteudo_json = json.dumps(resultado, ensure_ascii=False, indent=2)

    # Salva o arquivo principal dentro de dados_tracker.
    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    argumentos.saida.write_text(conteudo_json, encoding="utf-8")

    # Salva simultaneamente a copia que o dashboard consulta a cada 3 segundos.
    argumentos.dashboard.parent.mkdir(parents=True, exist_ok=True)
    argumentos.dashboard.write_text(conteudo_json, encoding="utf-8")

    print("Arquivos JSON atualizados:")
    print(f"1. Dados:     {argumentos.saida.resolve()}")
    print(f"2. Dashboard: {argumentos.dashboard.resolve()}")
    print("Top 5 agentes:")
    for agente in resultado["agentes"]["top_5"]:
        print(
            f"{agente['posicao']}. {agente['nome']} | "
            f"score {agente['score']} | {agente['partidas']} partidas"
        )
    print("Ranking de mapas:")
    for mapa in resultado["mapas"]["ranking"]:
        melhor = mapa["melhor_agente_estimado"]["agente"] or "indisponivel"
        print(
            f"{mapa['posicao']}. {mapa['mapa']} | score {mapa['score']} | "
            f"melhor agente estimado: {melhor}"
        )


if __name__ == "__main__":
    main()