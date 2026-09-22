from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity", help="Filtra uma entidade especifica, ex: aster_report_d0a4d301")
    args = parser.parse_args()

    env = load_env()
    entity_filter = args.entity
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            if entity_filter:
                cur.execute(
                    """
                    select entidade, sync_id, count(*)
                    from public.staging_dados
                    where entidade = %s
                    group by entidade, sync_id
                    order by sync_id desc
                    limit 10
                    """,
                    (entity_filter,),
                )
            else:
                cur.execute(
                    """
                    select entidade, sync_id, count(*)
                    from public.staging_dados
                    where entidade like 'aster_report_%'
                    group by entidade, sync_id
                    order by max(imported_at) desc
                    limit 10
                    """
                )
            print(f"staging_by_sync={cur.fetchall()}")

            if entity_filter:
                cur.execute(
                    """
                    select entidade, sync_id, status, registros_lidos, registros_inseridos
                    from public.historico_importacoes
                    where entidade = %s
                    order by iniciado_em desc
                    limit 10
                    """,
                    (entity_filter,),
                )
            else:
                cur.execute(
                    """
                    select entidade, sync_id, status, registros_lidos, registros_inseridos
                    from public.historico_importacoes
                    where entidade like 'aster_report_%'
                    order by iniciado_em desc
                    limit 10
                    """
                )
            print(f"historico={cur.fetchall()}")


if __name__ == "__main__":
    main()
