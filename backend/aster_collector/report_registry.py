from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DateFieldBinding:
    name: str
    input_position: int
    param_name: str


@dataclass(frozen=True)
class StaticFieldBinding:
    name: str
    input_position: int
    value: str
    hidden_input_id: str | None = None


@dataclass(frozen=True)
class TextFieldBinding:
    name: str
    input_position: int
    value: str
    param_name: str


@dataclass(frozen=True)
class ReportConfig:
    query_id: str
    area: str
    name: str
    entity: str
    automation_status: str
    static_fields: tuple[StaticFieldBinding, ...] = ()
    text_fields: tuple[TextFieldBinding, ...] = ()
    date_fields: tuple[DateFieldBinding, ...] = ()
    notes: str = ""


REPORTS: dict[str, ReportConfig] = {
    "D0A4D301": ReportConfig(
        query_id="D0A4D301",
        area="comercial_vendas",
        name="ABR - Analise de Vendas por Item",
        entity="aster_report_d0a4d301",
        automation_status="validated",
        static_fields=(StaticFieldBinding("Filial", 1, "Todos", "Filial"),),
        date_fields=(
            DateFieldBinding("Data de", 2, "DATADE"),
            DateFieldBinding("Data ate", 3, "DATAATE"),
        ),
        notes="Tipo vazio representa todos; filial deve ser selecionada como Todos pelo dropdown.",
    ),
    "0F75E84D": ReportConfig(
        query_id="0F75E84D",
        area="comercial_executivo",
        name="Resumo Comercial",
        entity="aster_report_0f75e84d",
        automation_status="validated",
        date_fields=(
            DateFieldBinding("Data Inicial", 0, "DATAINI"),
            DateFieldBinding("Data Final", 1, "DATAFIM"),
        ),
        notes="Fonte validada para indicadores comerciais consolidados.",
    ),
    "AB439998": ReportConfig(
        query_id="AB439998",
        area="comercial_vendas",
        name="ABR - Vendas Por Indicacao",
        entity="aster_report_ab439998",
        automation_status="candidate",
        date_fields=(
            DateFieldBinding("Data De", 0, "DATADE"),
            DateFieldBinding("Data Ate", 1, "DATAAT"),
        ),
        notes="Executou em janela curta sem body.data; precisa testar periodo maior.",
    ),
    "027051BD": ReportConfig(
        query_id="027051BD",
        area="comercial_clientes",
        name="Segmentacao de Lead",
        entity="aster_report_027051bd",
        automation_status="validated",
        notes="Parametro CardCode opcional; validado sem filtro com base comercial/clientes.",
    ),
    "37D9E431": ReportConfig(
        query_id="37D9E431",
        area="financeiro",
        name="ABR - Contas a Receber - PN",
        entity="aster_report_37d9e431",
        automation_status="deprioritized",
        text_fields=(TextFieldBinding("PN", 0, "C000002", "PN"),),
        date_fields=(
            DateFieldBinding("Data de lancamento de", 1, "DataLctoDe"),
            DateFieldBinding("Data de lancamento ate", 2, "DataLctoAte"),
        ),
        notes="Fora da prioridade atual; manter apenas como referencia financeira eventual.",
    ),
    "804C04C1": ReportConfig(
        query_id="804C04C1",
        area="estoque",
        name="Estoque",
        entity="aster_report_804c04c1",
        automation_status="training",
        static_fields=(StaticFieldBinding("FAMILIA", 0, "TODAS AS FAMILIAS", "_FAMILIA"),),
        notes="Requer FAMILIA; usa opcao agregada TODAS AS FAMILIAS.",
    ),
    "6630A54D": ReportConfig(
        query_id="6630A54D",
        area="estoque",
        name="Estoque Disponivel",
        entity="aster_report_6630a54d",
        automation_status="training",
        static_fields=(StaticFieldBinding("FAMILIA", 0, "TODAS AS FAMILIAS", "_FAMILIA"),),
        notes="Requer FAMILIA; usa opcao agregada TODAS AS FAMILIAS.",
    ),
    "DBF2AB0E": ReportConfig(
        query_id="DBF2AB0E",
        area="estoque",
        name="Estoque WMS",
        entity="aster_report_dbf2ab0e",
        automation_status="training",
        static_fields=(StaticFieldBinding("FAMILIA", 0, "TODAS AS FAMILIAS", "_FAMILIA"),),
        notes="Requer FAMILIA; usa opcao agregada TODAS AS FAMILIAS.",
    ),
    "6AD70B15": ReportConfig(
        query_id="6AD70B15",
        area="estoque_produto",
        name="Estrutura de Produto",
        entity="aster_report_6ad70b15",
        automation_status="training",
        text_fields=(TextFieldBinding("Codigo do item", 0, "PA000002", "_ItemCode"),),
        notes="Usa item real aprendido do relatorio de vendas para treino inicial.",
    ),
    "A6B5B978": ReportConfig(
        query_id="A6B5B978",
        area="estoque",
        name="Estoque URIFER",
        entity="aster_report_a6b5b978",
        automation_status="needs_ui_discovery",
        notes="Contrato capturado sem parametros obrigatorios, mas a UI ainda nao disparou execute automatico.",
    ),
    "CAF55C1D": ReportConfig(
        query_id="CAF55C1D",
        area="preco_cliente",
        name="Ultimo preco de venda",
        entity="aster_report_caf55c1d",
        automation_status="validated",
        static_fields=(
            StaticFieldBinding("Codigo do cliente", 0, "C000002", "CardCode"),
            StaticFieldBinding("Codigo do item", 1, "PA000002", "ItemCode"),
        ),
        notes="Validado com retorno de dados; filtros queryField podem retornar nulos quando o relatorio autoexecuta.",
    ),
    "C1A4D279": ReportConfig(
        query_id="C1A4D279",
        area="transporte",
        name="Ocorrencias",
        entity="aster_report_c1a4d279",
        automation_status="candidate",
        date_fields=(DateFieldBinding("Data de Entrega", 2, "DATAEN"),),
        notes="Requer data de entrega; rota/minuta sao opcionais.",
    ),
    "897A37D9": ReportConfig(
        query_id="897A37D9",
        area="outros",
        name="Mapa de relacao",
        entity="aster_report_897a37d9",
        automation_status="candidate",
        notes="Precisa avaliar utilidade analitica.",
    ),
}


def get_report_config(query_id: str) -> ReportConfig:
    return REPORTS.get(
        query_id.upper(),
        ReportConfig(
            query_id=query_id.upper(),
            area="desconhecido",
            name=f"Relatorio Aster {query_id.upper()}",
            entity=f"aster_report_{query_id.lower()}",
            automation_status="unknown",
        ),
    )
