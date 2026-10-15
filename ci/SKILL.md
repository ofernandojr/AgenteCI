---
name: ci
description: Agente mensal da C.I. (Comunicação Interna ao Departamento de Pessoal). Use quando o usuário mandar foto(s) do cartão de ponto, pedir para fazer/preencher/gerar a C.I. do mês, ou digitar /ci. Lê o cartão, calcula as divergências de jornada, pergunta sobre horas extras, banco de horas, compensação e motivos, e gera o .docx da C.I. no modelo oficial.
---

# Agente da C.I. mensal

Objetivo: o usuário só manda a foto do cartão. Você lê, calcula, **pergunta o que só ele sabe** e entrega a C.I. pronta em .docx.

## Peças (nesta pasta)
- `scripts/ci.py`: motor + gerador do .docx, só Python 3 padrão. **Nunca faça as contas de cabeça: use sempre o script.**
  - `python scripts/ci.py config`: mostra qual config/modelo foi achado.
  - `python scripts/ci.py analisar <entrada.json>`: divergências, sábados e avisos.
  - `python scripts/ci.py gerar <entrada.json> --saida <pasta>`: texto da C.I. + `CI_AAAA-MM.docx`.
- `assets/modelo-ci.docx`: modelo da C.I. com marcadores ({{NOME}} etc.) preenchidos pelo config.
- `config.exemplo.json`: formato do config.

Use o caminho completo desta pasta da skill ao chamar o script (ex.: `python /caminho/da/skill/scripts/ci.py ...`). No Windows o comando costuma ser `python`; no Mac/Linux, `python3`.

## Onde salvar arquivos (depende de onde você está rodando)
- **Claude Code / Antigravity (no computador):** trabalhe na pasta atual; entrada em `CI/entrada_AAAA-MM.json`, saída em `CI/` (padrão do `gerar`).
- **claude.ai / Claude Desktop (sandbox):** grave em `/mnt/user-data/outputs/` (`--saida /mnt/user-data/outputs`) e entregue o link do .docx.
- **ChatGPT:** grave em `/mnt/data/` (`--saida /mnt/data`) e entregue o link de download.

## 0. Config (primeira vez)
Rode `scripts/ci.py config`. Se `config` vier `null`, peça ao usuário: nome, função, setor, empresa, unidade (nº), número (funcional), unidade (nome), cartão nº, cidade, e se a jornada é a padrão (seg–qui 9h, sex 8h, tolerância 10 min). Grave `ci-config.json` na pasta de trabalho no formato de `config.exemplo.json` e avise que, para não perguntar de novo, ele deve salvar esse arquivo como `config.json` dentro da pasta da skill.
- `modeloDocx`: caminho de um .docx próprio (relativo à pasta do config). Use quando o usuário tiver o modelo com carimbo/assinatura. Sem ele, usa `assets/modelo-ci.docx`.

## Regras de negócio
- Período de apuração **16 → 15**. Competência = mês do dia 15. Foto "2.ª quinzena" = dias 16–31 do mês anterior; "1.ª quinzena" = dias 1–15 da competência.
- Jornada esperada: seg–qui 9h, sex 8h, sáb/dom 0h, feriado 0h. Tolerância de 10 min (±) não é divergência.
- Sábado de folga (sem marcação, não feriado) = "Sábado dd/mm/aaaa compensado;". Na semana de sábado compensado, hora a mais de seg–sex vira **compensado** (não sai na C.I.).
- Almoço não batido (só entrada da manhã e saída da tarde) deduz 1h e gera "Considerar hora de almoço ...".
- Turno que passa da meia-noite gera "Considerar saída extra do dia X às HH:MM da manhã do dia Y;".

## 1. Fotos e competência
- Precisa das duas quinzenas; se faltar uma, peça.
- Descubra mês/ano pelos carimbos **DOMINGO**: ache o mês em que aqueles dias caem num domingo (2.ª quinzena = mês anterior à competência). Se o usuário disse o mês, use o dele.

## 2. Ler o cartão
Para cada dia, 6 colunas: Manhã entrada/saída (`inicio1`/`fim1`), Tarde entrada/saída (`inicio2`/`fim2`), Extra entrada/saída (`inicio3`/`fim3`).
- Carimbo do relógio: os dígitos pequenos/girados antes da hora são o **dia**; ignore, pegue só `HH:MM`. Carimbo vermelho é horário normal (saída).
- Carimbo apagado: olhe com cuidado; se não tiver certeza, marque ⚠ na tabela.
- `FERIADO` → `"feriado": true`. `DOMINGO` → dia sem marcação.
- Escrita à mão **não é marcação**: `?` = marcação esquecida; texto ("Festa Junina", "Saída?"), números ("2.17", "0.43") e `C` na coluna HORAS EXTRAS (= sábado compensado) vão para `anotacoes`.
- Dias que ainda não aconteceram (foto tirada antes do dia 15) ficam em branco: pergunte se espera ou se foram dias normais.

Mostre uma tabela curta (só dias com marcação ou anotação) e confirme ("Leitura confere?"). Corrija o que o usuário apontar.

## 3. Entrada e análise
Grave `entrada_AAAA-MM.json` (AAAA-MM = competência) e rode `analisar`.

```json
{
  "mes": 7, "ano": 2026,
  "registros": [
    {"date": "2026-06-16", "inicio1": "08:06", "fim1": "12:00", "inicio2": "12:55", "fim2": "17:56"},
    {"date": "2026-07-09", "feriado": true}
  ],
  "anotacoes": {"2026-06-24": "Jogo do Brasil", "2026-06-20": "C"},
  "sabadosCompensados": ["2026-06-20"],
  "marcacoesInformadas": {"2026-06-29": {"fim2": "18:00"}},
  "dayChoices": {"2026-06-27": "extra"},
  "dayMotivos": {"2026-06-24": "Jogo do Brasil"},
  "linhasExtras": [{"date": "2026-07-10", "texto": "Abonar o dia 10/07/2026 – EMENDA DE FERIADO;"}],
  "linhasManuais": null,
  "dataCI": "2026-07-15"
}
```
- `dayChoices`: `extra` | `banco` | `compensado` (horas a mais) · `descontar` | `ignorar` (horas a menos). Sem escolha = padrão do motor.
- `marcacoesInformadas`: horário esquecido que o usuário informou; entra na conta e gera "Considerar saída às HH:MM no dia ...".
- `linhasExtras`: linha livre que o motor não gera. `linhasManuais`: lista com o texto final inteiro (só se o usuário quiser reescrever tudo).
- Motivo sai em MAIÚSCULAS no fim da linha ("– FESTA JUNINA"), como na C.I. real.

## 4. Perguntas (o coração do agente)
Pergunte de forma objetiva, com opções (botões, se a plataforma tiver), agrupando por assunto. Mostre sempre data, dia da semana e saldo (`+2h12`). **Nunca invente motivo**: só use o que o usuário disser ou a anotação do cartão que ele confirmar.

1. **Sábados de folga**: quais foram compensados. Sugira os que têm `C` no cartão.
2. **Marcação faltando** (`avisos` / `marcacaoFaltando`): qual horário bater. Opções: horário padrão (saída 18:00 seg–qui, 17:00 sex; almoço 12:00–13:00), "Saí mais cedo / não voltei" ou horário exato.
3. Grave as respostas e **rode `analisar` de novo** (muda saldo e padrão compensado/extra).
4. **Horas a mais**, por semana: Hora Extra / Banco de Horas / Compensado (dia útil). Semana de sábado compensado → recomende Compensado. Depois o **motivo** (anotações do cartão daquele dia, "Sem motivo" ou outro).
5. **Almoço não batido**: motivo (a anotação sugere).
6. **Horas a menos**: Descontar do banco / Ignorar (+ justificativa opcional).
7. **Dia útil sem nenhuma marcação**: falta → `descontar`; folga/abono/ponte → `ignorar` + `linhasExtras` com a justificativa; feriado esquecido → `"feriado": true`.

## 5. Gerar e entregar
`dataCI`: hoje; se for C.I. de mês antigo, dia 15 da competência.

Rode `gerar`. Mostre o texto e pergunte se está ok (Aprovar / Editar). Ajuste e gere de novo até aprovar. Entregue o `CI_AAAA-MM.docx` (abrir no Word, imprimir, assinar).
- Mais de ~14 linhas: a fonte encolhe para caber no quadro; peça para conferir antes de imprimir.
- Se o config tiver `app`, o `gerar` também cria `Folha_Ponto_<Mês>_<Ano>.json` para importar no app Folha de Ponto (Ações → Importar).
