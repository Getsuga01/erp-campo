"""Rota de métricas e indicadores (3.26) — a partir das views do banco."""
import math

from fastapi import APIRouter

from oracle_client import sessao
from rotas import linha_para_dict, numero

router = APIRouter()


@router.get("/metricas")
def metricas() -> dict:
    """Taxa de sucesso, top 5 erros, tempo médio/p95 por lote e estado da fila."""
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute("SELECT NVL(SUM(total_recebidos), 0), NVL(SUM(total_gravados), 0) FROM INT_LOTE")
        recebidos, gravados = (int(valor) for valor in cur.fetchone())
        taxa = round(gravados * 100 / recebidos, 2) if recebidos else None

        cur.execute(
            "SELECT duracao_minutos FROM V_INDICADORES_LOTE WHERE duracao_minutos IS NOT NULL "
            "ORDER BY duracao_minutos"
        )
        duracoes = [float(linha[0]) for linha in cur.fetchall()]
        tempo_medio = round(sum(duracoes) / len(duracoes), 3) if duracoes else None
        tempo_p95 = round(duracoes[max(0, math.ceil(0.95 * len(duracoes)) - 1)], 3) if duracoes else None

        cur.execute(
            "SELECT codigo_erro, qtd, ultima_ocorrencia FROM "
            "  (SELECT * FROM V_TOP_ERROS ORDER BY qtd DESC) WHERE ROWNUM <= 5"
        )
        descricao = cur.description
        top_erros = [linha_para_dict(linha, descricao) for linha in cur.fetchall()]

        cur.execute("SELECT situacao, qtd, idade_mais_antigo_min FROM V_FILA_STATUS")
        descricao = cur.description
        fila = [linha_para_dict(linha, descricao) for linha in cur.fetchall()]

    pendentes = next((item for item in fila if item["situacao"] == "PENDENTE"), None)
    dead_letters = next((item for item in fila if item["situacao"] == "DEAD_LETTER"), None)
    return {
        "lotes": {
            "total_recebidos": recebidos,
            "total_gravados": gravados,
            "taxa_sucesso_pct": taxa,
            "tempo_medio_min": tempo_medio,
            "tempo_p95_min": tempo_p95,
        },
        "top_5_erros": [
            {**erro, "qtd": numero(erro["qtd"])} for erro in top_erros
        ],
        "fila": [{**item, "qtd": numero(item["qtd"])} for item in fila],
        "fila_pendente_qtd": int(pendentes["qtd"]) if pendentes else 0,
        "dead_letter_qtd": int(dead_letters["qtd"]) if dead_letters else 0,
        "idade_fila_min": numero(pendentes["idade_mais_antigo_min"]) if pendentes else None,
    }
