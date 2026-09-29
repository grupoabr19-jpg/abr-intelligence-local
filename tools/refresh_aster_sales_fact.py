from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.api.data import SALE_DATE_SQL, money_sql
from tools.apply_migrations import connect_database, load_env


ENTITY = "aster_report_d0a4d301"


def refresh() -> dict[str, object]:
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute("truncate table public.dashboard_sales_fact")
            cur.execute(
                f"""
                insert into public.dashboard_sales_fact(
                  staging_id,
                  source_id,
                  hash_registro,
                  sync_id,
                  imported_at,
                  sale_date,
                  valor_total,
                  receita_liquida,
                  lucro_bruto,
                  margem_contribuicao,
                  peso_total,
                  cliente_codigo,
                  cliente,
                  item,
                  produto,
                  familia,
                  segmento,
                  cidade,
                  estado,
                  vendedor,
                  tipo,
                  nota_fiscal,
                  valor_perdido,
                  motivo_perda,
                  refreshed_at
                )
                select
                  id,
                  source_id,
                  hash_registro,
                  sync_id,
                  imported_at,
                  {SALE_DATE_SQL},
                  {money_sql("Valor Total")},
                  {money_sql("RecLiquida")},
                  {money_sql("LucroBruto")},
                  {money_sql("Margem de Contribuição (MC)")},
                  {money_sql("Peso Total")},
                  nullif(payload_original->>'CodCliente', ''),
                  coalesce(
                    nullif(payload_original->>'Cliente', ''),
                    nullif(payload_original->>'Nome do cliente', ''),
                    nullif(payload_original->>'Nome Cliente', ''),
                    nullif(payload_original->>'CodCliente', ''),
                    'Sem cliente'
                  ),
                  nullif(payload_original->>'Item', ''),
                  coalesce(
                    nullif(payload_original->>'Descrição', ''),
                    nullif(payload_original->>'Item', ''),
                    'Sem item'
                  ),
                  coalesce(nullif(payload_original->>'Familia', ''), 'Sem familia'),
                  coalesce(nullif(payload_original->>'Segmento', ''), 'Sem segmento'),
                  coalesce(nullif(payload_original->>'Cidade', ''), 'Sem cidade'),
                  coalesce(nullif(payload_original->>'Estado', ''), 'Sem UF'),
                  coalesce(nullif(payload_original->>'Vendedor', ''), 'Sem vendedor'),
                  coalesce(nullif(payload_original->>'Tipo', ''), 'Sem tipo'),
                  coalesce(
                    nullif(payload_original->>'N° NF', ''),
                    nullif(payload_original->>'Nº NF', ''),
                    nullif(payload_original->>'NF', ''),
                    nullif(payload_original->>'Nota fiscal', ''),
                    nullif(payload_original->>'Nota Fiscal', '')
                  ),
                  {money_sql("Valor Venda Perdida")},
                  coalesce(nullif(trim(payload_original->>'Motivo 1'), ''), 'Sem motivo'),
                  now()
                from public.staging_dados
                where entidade = %s
                """,
                (ENTITY,),
            )
            cur.execute("delete from public.dashboard_sales_summary_cache")
            cur.execute(
                """
                select
                  count(*)::int,
                  min(sale_date),
                  max(sale_date),
                  coalesce(sum(valor_total), 0),
                  coalesce(sum(peso_total), 0)
                from public.dashboard_sales_fact
                """
            )
            rows, min_date, max_date, total, weight = cur.fetchone()
            conn.commit()

    return {
        "entity": ENTITY,
        "rows": rows,
        "data_min": min_date.isoformat() if min_date else None,
        "data_max": max_date.isoformat() if max_date else None,
        "valor_total": f"{total:.2f}",
        "peso_total": f"{weight:.2f}",
    }


def main() -> None:
    print(json.dumps(refresh(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
