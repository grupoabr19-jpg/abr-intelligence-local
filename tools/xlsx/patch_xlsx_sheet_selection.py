"""Historical patch helper for the XLSX worksheet-selection fix.

The current Edge Function already contains the worksheet discovery logic.
This file is kept only as operational documentation so nobody reruns the
old absolute-path patch against the wrong workspace.
"""

from pathlib import Path


EDGE_FUNCTION = Path("supabase/functions/processar-importacao/index.ts")
MIGRATION = Path("supabase/migrations/20260921200000_persistir_aba_xlsx.sql")


def main() -> None:
    print("No patch applied.")
    print(f"Expected Edge Function: {EDGE_FUNCTION}")
    print(f"Expected migration: {MIGRATION}")
    print("The worksheet-selection fix is already present in this organized tree.")


if __name__ == "__main__":
    main()
