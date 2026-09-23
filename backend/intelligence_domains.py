from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntelligenceDomain:
    key: str
    title: str
    description: str
    status: str
    sources: tuple[str, ...]
    current_scope: tuple[str, ...]
    next_scope: tuple[str, ...]
    boundaries: tuple[str, ...]


DOMAINS: tuple[IntelligenceDomain, ...] = (
    IntelligenceDomain(
        key="internal",
        title="Inteligencia Interna",
        description=(
            "Dados operacionais do Grupo ABR: Aster, planilhas internas, regioes comerciais, "
            "staging e bases derivadas de vendas, pedidos, estoque, margem, clientes e logistica."
        ),
        status="active",
        sources=(
            "aster",
            "local_spreadsheets",
            "commercial_regions",
            "supabase_staging",
        ),
        current_scope=(
            "relatorios Aster treinados e validados",
            "planilhas locais em Planilhas/",
            "classificacao de vendas por canal e regiao",
            "requisitos internos de dados e lacunas operacionais",
        ),
        next_scope=(
            "ingestao normalizada das planilhas locais",
            "promocao das cargas internas para tabelas finais",
            "jobs recorrentes de coleta Aster e leitura de planilhas",
        ),
        boundaries=(
            "Nao misturar series de mercado externo neste dominio.",
            "Fontes deste dominio devem representar operacao interna, cliente, produto, estoque, pedido ou faturamento ABR.",
        ),
    ),
    IntelligenceDomain(
        key="external",
        title="Inteligencia Externa",
        description=(
            "Sinais de mercado usados para contextualizar decisoes internas: mercado nacional do aco, "
            "mercado internacional, cotacoes, indices, cambio, insumos e referencias de frete."
        ),
        status="planned",
        sources=(
            "steel_market_brazil",
            "steel_market_international",
            "steel_price_quotes",
            "fx_rates",
            "commodities",
        ),
        current_scope=(
            "separacao conceitual e namespace reservado",
        ),
        next_scope=(
            "catalogar fontes externas confiaveis",
            "definir frequencia e licenca de uso por fonte",
            "criar coletores externos separados da automacao Aster",
            "normalizar series historicas para analise comparativa",
        ),
        boundaries=(
            "Nao depender de sessao Aster ou planilhas internas.",
            "Nao gravar indicadores externos como se fossem dados operacionais internos.",
        ),
    ),
)


def list_intelligence_domains() -> list[dict[str, object]]:
    return [
        {
            "key": domain.key,
            "title": domain.title,
            "description": domain.description,
            "status": domain.status,
            "sources": list(domain.sources),
            "current_scope": list(domain.current_scope),
            "next_scope": list(domain.next_scope),
            "boundaries": list(domain.boundaries),
        }
        for domain in DOMAINS
    ]
