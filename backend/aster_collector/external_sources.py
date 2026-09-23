from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalSpreadsheetSource:
    key: str
    title: str
    folder_url: str
    selection_rule: str
    latest_file_id: str
    latest_file_name: str
    latest_modified_time: str
    local_path: str
    likely_coverage: tuple[str, ...]
    notes: str


EXTERNAL_SPREADSHEET_SOURCES: tuple[ExternalSpreadsheetSource, ...] = (
    ExternalSpreadsheetSource(
        key="drive:margem_resumo_latest",
        title="Planilha mais recente de margem/resumo GABR",
        folder_url="https://drive.google.com/drive/folders/1u3lRKrvf5lFpChAmhaiSb7s7ypp2DCAA",
        selection_rule="Sempre usar o arquivo mais recente da pasta por modified_time.",
        latest_file_id="10NyDI5OQrdXFPCS7pldd5bAZ4RyfcwTm",
        latest_file_name="Margem_GABR_20260916.xlsx",
        latest_modified_time="2026-09-17T14:50:44.478Z",
        local_path="Planilhas/Margem_GABR_20260916.xlsx",
        likely_coverage=("vendas_faturamento", "cadastro_produtos"),
        notes=(
            "Fonte complementar local para margem, custo, preco medio, tabela de preco e resumo comercial "
            "quando o Aster nao trouxer todos os campos."
        ),
    ),
    ExternalSpreadsheetSource(
        key="drive:gestao_producao_latest",
        title="Planilha mais recente de gestao da producao",
        folder_url="https://drive.google.com/drive/folders/1p1uHLXOL3DWDN-emm8N8Tw4ycnnWX35w",
        selection_rule="Sempre usar o arquivo mais recente da pasta por modified_time.",
        latest_file_id="1AEQqOgFpArFYI6unz52825pks4RkV2Qf",
        latest_file_name="Gestão da Produção.xlsx",
        latest_modified_time="2026-09-23T12:44:47.046Z",
        local_path="Planilhas/Gestão da Produção.xlsx",
        likely_coverage=("pedidos_carteira", "cadastro_produtos", "logistica_frete"),
        notes="Fonte complementar local para pedido, item, carteira, producao/PCP, picking, NF, frete e dados de produto usados na operacao.",
    ),
)


def external_sources_by_requirement() -> dict[str, tuple[ExternalSpreadsheetSource, ...]]:
    index: dict[str, list[ExternalSpreadsheetSource]] = {}
    for source in EXTERNAL_SPREADSHEET_SOURCES:
        for requirement_key in source.likely_coverage:
            index.setdefault(requirement_key, []).append(source)
    return {key: tuple(items) for key, items in index.items()}
