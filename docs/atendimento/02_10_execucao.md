# Batches 02 a 10 - Atendimento

Data: 2026-09-25

## Batch 02 - Dimensoes operacionais

Implementado:

- `dim_atendimento_regiao_polo`
- `dim_atendimento_colaborador`
- `dim_kommo_pipeline`
- `dim_kommo_status`
- `dim_atendimento_origem`
- ajuste da `dim_regiao_varejo` para aceitar `ATACADO`
- inclusao de Wilson Bueno, Larissa e Julio como Atacado

## Batch 03 - Fatos de atendimento

Implementado:

- `fato_atendimento_lead`
- `fato_atendimento_sla`
- `fato_atendimento_followup`
- `tools/refresh_atendimento_facts.py`

A carga de fatos parte da staging atual do Kommo e preserva compatibilidade com o dashboard.

## Batch 04 - API usando fatos

Implementado:

- `backend/api/data.py` agora tenta ler `fato_atendimento_*` primeiro.
- Se os fatos estiverem vazios, o backend retorna ao fluxo antigo por `staging_dados`.
- O payload de `attendance_summary` manteve o contrato principal usado pelo frontend.

## Batch 05 - Frontend Atendimento

Implementado:

- Visao Geral mostra fonte da base e qualidade.
- Aba SLA passou a ter tabela real por colaborador.
- Aba Equipe mostra cadastro por praca/polo.
- Ranking continua usando colaborador + funcao + regiao/polo.

## Batch 06 - SLA e follow-up

Implementado:

- SLA 5 minutos e 15 minutos nos fatos.
- Leads sem resposta.
- Leads abertos sem proxima tarefa.
- Cobertura de follow-up por colaborador e regiao.

Limitacao atual:

- A base validada ainda nao possui campos suficientes para calcular SLA em todos os leads. O refresh registra isso em `atendimento_data_quality`.

## Batch 07 - Qualidade e auditoria

Implementado:

- `atendimento_data_quality`
- `atendimento_refresh_runs`
- historico das ultimas atualizacoes exposto no dashboard.

## Batch 08 - Operacao e agendamento

Comandos operacionais:

```powershell
.\.venv\Scripts\python.exe tools\collect_kommo_attendance.py --date-from 2026-01-01 --date-to 2026-09-25
.\.venv\Scripts\python.exe tools\refresh_atendimento_facts.py
```

Sugestao para Render Cron:

1. Rodar coleta Kommo.
2. Rodar refresh dos fatos.
3. Alertar se qualquer comando retornar codigo diferente de zero.

## Batch 09 - Testes e validacao

Implementado:

- `tools/test_atendimento_logic.py`
- validacao de classificacao operacional:
  - Liderancas
  - Comunicacao interna
  - Venda ganha
  - Venda perdida
  - andamento
- validacao de chave normalizada de dimensao.

## Batch 10 - Fechamento

Estado final:

- Atendimento tem camada RAW.
- Atendimento tem dimensoes.
- Atendimento tem fatos.
- Dashboard consome fatos quando disponiveis.
- Staging continua como compatibilidade.
- Pontos sem dados suficientes ficam registrados como qualidade/pendencia, sem inventar indicador.

Proximos passos recomendados:

- popular `raw_kommo_events` com eventos/mensagens quando a API estiver liberada;
- trocar campos customizados de SLA por eventos reais de primeira mensagem e primeira resposta;
- criar agregados materializados se o volume crescer;
- criar cron no Render para carga diaria;
- revisar RLS antes de expor qualquer tabela pela Data API publica.
