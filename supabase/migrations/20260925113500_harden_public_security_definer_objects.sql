-- Harden objects reported by Supabase security advisors.
-- The event trigger function is invoked by Postgres, not by API roles.
REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM anon;
REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM authenticated;

-- Views in exposed schemas should run with the caller permissions.
ALTER VIEW IF EXISTS public.reconciliacao_faturamento SET (security_invoker = true);
ALTER VIEW IF EXISTS public.pendencias_cruzamento SET (security_invoker = true);
ALTER VIEW IF EXISTS public.anulados_cruzamento SET (security_invoker = true);
ALTER VIEW IF EXISTS public.reconciliation_summary SET (security_invoker = true);
ALTER VIEW IF EXISTS public.meta_ativa SET (security_invoker = true);
ALTER VIEW IF EXISTS public.realizado_ativo SET (security_invoker = true);
