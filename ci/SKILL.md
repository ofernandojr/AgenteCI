---
name: ci
description: Agente mensal da C.I. (Comunicação Interna ao Departamento de Pessoal). Use quando o usuário mandar foto(s) do cartão de ponto, pedir para fazer/preencher/gerar a C.I. do mês, ou digitar /ci. Lê o cartão, calcula as divergências de jornada, pergunta sobre horas extras, banco de horas, compensação e motivos, e gera o .docx da C.I. no modelo oficial.
---

# Agente da C.I. mensal

O usuário só manda a foto do cartão. Você lê, roda o script, **pergunta o que só ele sabe** e entrega o .docx. Seja rápido: **no máximo 2 rodadas com o usuário** (perguntas e aprovação do texto).

`scripts/ci.py` (nesta pasta da skill) faz todas as contas. **Nunca calcule horas de cabeça e não abra o código do script: só rode.** Chame pelo caminho completo da pasta da skill; no Windows use `python`, no Mac/Linux `python3`.
- `analisar <entrada.json>`: relatório com leitura, sábados, divergências e avisos.
- `gerar <entrada.json> [--saida PASTA]`: texto da C.I. + `CI_AAAA-MM.docx` (e o JSON do app, se o config tiver `app`).

Onde gravar: no computador (Claude Code, Antigravity) use `CI/` na pasta atual; no claude.ai use `--saida /mnt/user-data/outputs`; no ChatGPT use `--saida /mnt/data`.

## Fluxo rápido (siga nesta ordem)

**1. Ler as fotos UMA vez.** Se vierem como arquivo, abra as duas na mesma chamada (em paralelo). **Não amplie, recorte, gire nem processe imagem com script.** Carimbo ilegível: escreva o melhor palpite e ponha `⚠` na nota do dia; o usuário confirma depois. Não escreva tabela da leitura na conversa.

**2. Gravar `CI/entrada_AAAA-MM.json` direto, no formato compacto** (AAAA-MM = competência = mês do dia 15):
```json
{"mes": 7, "ano": 2026,
 "q2": {"16": "08:06 12:00 12:55 17:56", "17": "05:43 - - 17:55", "27": "07:55 11:55"},
 "q1": {"1": "07:55 12:04 13:02 17:58", "9": "F", "13": "07:54 12:03 13:01"},
 "notas": {"q2": {"20": "C", "24": "Jogo do Brasil"}, "q1": {"13": "⚠ 13:01 apagado"}}}
```
- `q2` = foto da **2.ª quinzena** (dias 16–31, mês anterior); `q1` = **1.ª quinzena** (dias 1–15). O script calcula as datas.
- Cada dia: horários na ordem das colunas — Manhã entrada, Manhã saída, Tarde entrada, Tarde saída, Extra entrada, Extra saída. Coluna vazia no meio = `-`. `F` = FERIADO. Dia sem marcação (DOMINGO, folga) = não coloque.
- Carimbo do relógio: os dígitos pequenos/girados antes da hora são o **dia**; pegue só `HH:MM`. Vermelho é horário normal.
- Escrita à mão **não é marcação**, vai em `notas`: `?`, textos ("Festa Junina", "Saída?"), números ("2.17") e `C` na coluna HORAS EXTRAS (= sábado compensado).
- Mês/ano: o usuário disse? Use. Senão, ache o mês em que os dias com carimbo DOMINGO caem num domingo.

**3. Rodar `analisar` (uma vez)** e ler o relatório.
- Se aparecer `SEM CONFIG`, inclua na rodada de perguntas os dados do funcionário (ver "Config") e grave o config antes de gerar.

**4. UMA rodada de perguntas** (ferramenta de perguntas com opções, até 4 perguntas juntas; agrupe). Mostre antes, em poucas linhas, só os dias com `⚠`/notas e o resumo das divergências (copie do relatório, não reescreva tudo). Pergunte, nesta prioridade:
1. Leitura duvidosa (`⚠`): confirme o horário.
2. Marcação faltando: horário (padrão: saída 18:00 seg–qui, 17:00 sex; almoço 12:00–13:00) ou "saí mais cedo".
3. Horas a mais, por semana: Hora Extra / Banco / Compensado (semana de sábado compensado → recomende Compensado) e o motivo (sugira a nota do cartão).
4. Horas a menos e dia útil sem marcação: Descontar do banco / Ignorar (falta, folga, abono, ponte?).
Sábados de folga: assuma compensados os que têm `C`; só pergunte se houver folga sem `C`. Se sobrar decisão para depois das 4 perguntas, use o padrão do motor e avise no texto final. **Nunca invente motivo.**

**5. Gravar as respostas na entrada e rodar `gerar`.** Não rode `analisar` de novo. Mostre o texto gerado e o caminho do .docx; pergunte "Aprovar ou ajustar?". Ajuste = editar a entrada e `gerar` de novo.

## Campos de resposta na entrada
```json
"sabadosCompensados": ["2026-06-20", "2026-07-04"],
"marcacoesInformadas": {"2026-06-29": {"fim2": "18:00"}},
"dayChoices": {"2026-06-27": "extra", "2026-07-10": "ignorar"},
"dayMotivos": {"2026-06-26": "Festa Junina"},
"linhasExtras": [{"date": "2026-07-10", "texto": "Abonar o dia 10/07/2026 – EMENDA DE FERIADO;"}],
"linhasManuais": null,
"dataCI": "2026-07-15"
```
- `dayChoices`: `extra` | `banco` | `compensado` (horas a mais) · `descontar` | `ignorar` (horas a menos). Sem escolha = padrão do motor.
- `marcacoesInformadas` campos: `inicio1` entrada, `fim1` saída almoço, `inicio2` volta, `fim2` saída, `inicio3`/`fim3` extra.
- `linhasExtras`: linha livre que o motor não gera. `linhasManuais`: texto final inteiro (só se o usuário quiser reescrever).
- `dataCI`: hoje; C.I. de mês antigo = dia 15 da competência.

## Config
Procurado em: `--config`, `./ci-config.json`, `config.json` nesta pasta. Formato em `config.exemplo.json`: `funcionario` (nome, funcao, setor, empresa, unidadeNum, numero, unidade, cartao), `jornada` (padrão seg–qui 9h, sex 8h, tolerância 10 min), `cidade`, `modeloDocx` (opcional: .docx próprio com carimbo, relativo ao config). Sem config: pergunte os dados do funcionário, grave `ci-config.json` na pasta de trabalho e diga que, para não perguntar de novo, basta salvar como `config.json` na pasta da skill.

## Regras que o motor aplica (para explicar ao usuário)
Período 16 → 15 · seg–qui 9h, sex 8h, sáb/dom/feriado 0h · ±10 min não conta · sábado de folga = "Sábado dd/mm/aaaa compensado;" e, na semana dele, hora a mais de seg–sex vira compensado (não sai na C.I.) · almoço não batido deduz 1h ("Considerar hora de almoço ...") · turno após meia-noite gera "saída extra ... da manhã do dia seguinte" · extra/banco: uma linha por semana com motivo em MAIÚSCULAS · texto acima de ~14 linhas encolhe a fonte (peça para conferir antes de imprimir).
