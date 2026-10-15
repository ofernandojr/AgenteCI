# AgenteCI — C.I. mensal a partir da foto do cartão de ponto

Agente de IA que preenche a **C.I. (Comunicação Interna ao Departamento de Pessoal)** todo mês.
Você manda a foto do cartão de ponto. O agente:

1. lê as marcações (carimbos do relógio e anotações à mão);
2. calcula as divergências (jornada seg–qui 9h, sex 8h, tolerância 10 min, período 16 → 15, sábado compensado, almoço não batido);
3. pergunta o que só você sabe (hora extra, banco ou compensado, motivos, horários esquecidos);
4. gera o `CI_AAAA-MM.docx` no modelo oficial, pronto para imprimir e assinar.

Funciona no **Claude** (Claude Code, claude.ai, Claude Desktop), no **Antigravity** e no **ChatGPT**. É uma skill no padrão aberto *Agent Skills* (`SKILL.md`), com um motor em Python sem dependências.

## Estrutura

```
ci/                         <- a skill (é esta pasta que se instala)
  SKILL.md                  roteiro do agente: regras, perguntas, formato
  scripts/ci.py             motor + gerador do .docx (Python 3.8+, só biblioteca padrão)
  assets/modelo-ci.docx     modelo da C.I. com {{NOME}}, {{FUNCAO}}... (sem dados pessoais)
  config.exemplo.json       modelo do config
  config.json               SEU config (não vai para o Git)
  pessoal/                  SEU .docx com carimbo/assinatura, se quiser (não vai para o Git)
chatgpt/INSTRUCOES.md       instruções para GPT/Projeto do ChatGPT
empacotar.py                gera dist/ci.zip e dist/chatgpt/ para upload
tests/test_ci.py            testes do motor
```

## 1. Baixar e configurar (uma vez)

Precisa de **Python 3** no computador (`python --version`). O repositório é privado, então clone logado:

```bash
gh repo clone ofernandojr/AgenteCI
```

Crie seu config a partir do exemplo e preencha com seus dados:

```bash
cp AgenteCI/ci/config.exemplo.json AgenteCI/ci/config.json
```

- `funcionario`: nome, função, setor, empresa, unidade (nº), número (funcional), unidade (nome), cartão.
- `jornada`: horas por dia e tolerância em minutos.
- `modeloDocx`: opcional. Se a sua C.I. tem carimbo ou assinatura impressos, copie o seu `.docx` para `ci/pessoal/` e coloque `"modeloDocx": "pessoal/C.I.docx"`. Sem isso, usa `assets/modelo-ci.docx`.

Se você não criar o config, o agente pergunta seus dados na primeira vez.

Para claude.ai e ChatGPT, gere os pacotes de upload:

```bash
python AgenteCI/empacotar.py
```

O comando cria `dist/ci.zip` e a pasta `dist/chatgpt/`. Esses pacotes levam o seu config: suba só na sua conta.

## 2. Instalar

### Claude Code (terminal, VS Code, app desktop)

Copie a pasta `ci` para as suas skills globais.

Windows (PowerShell):
```powershell
Copy-Item -Recurse AgenteCI\ci $HOME\.claude\skills\ci
```

Mac/Linux:
```bash
cp -r AgenteCI/ci ~/.claude/skills/ci
```

Abra uma sessão nova do Claude Code e digite `/ci`, ou só "faz minha C.I." com as fotos. Para instalar em um projeto só, copie para `<projeto>/.claude/skills/ci`.

### claude.ai e Claude Desktop

1. Rode `python empacotar.py`.
2. Em claude.ai, abra **Settings → Capabilities**. Deixe ligado **Code execution and file creation**.
3. Em **Skills**, clique em **Upload skill** e escolha `dist/ci.zip`. Ative a skill.
4. Em um chat novo, anexe as fotos e escreva "faz minha C.I. deste mês".

Precisa de plano pago (Pro, Max, Team ou Enterprise). A skill vale para a sua conta no site e no app desktop.

### Antigravity (Google)

Copie a pasta `ci` para as skills globais.

Windows (PowerShell):
```powershell
Copy-Item -Recurse AgenteCI\ci $HOME\.gemini\config\skills\ci
```

Mac/Linux:
```bash
mkdir -p ~/.gemini/config/skills && cp -r AgenteCI/ci ~/.gemini/config/skills/ci
```

Versões antigas usam `~/.gemini/antigravity/skills/`. Para um projeto só, copie para `<projeto>/.agents/skills/ci`.

No painel do agente, abra **Customizations** e confira que a skill `ci` aparece. Depois anexe as fotos e peça "use a skill ci para fazer minha C.I.". Se a skill global não for achada, use a do projeto (`.agents/skills/ci`).

### ChatGPT

**A) Com Skills** (se a sua conta mostra **Plugins → Skills** na barra lateral):

1. Rode `python empacotar.py`.
2. Vá em **Skills → Create → Upload from your computer** e escolha a pasta `ci` (ou `dist/ci.zip`).
3. Espere a verificação. Depois, em um chat, anexe as fotos e peça a C.I.

**B) Sem Skills** (GPT personalizado ou Projeto; funciona em qualquer plano pago):

1. Rode `python empacotar.py`.
2. Crie um GPT: **Explore GPTs → Create → Configure**.
3. Em **Instructions**, cole o bloco de [chatgpt/INSTRUCOES.md](chatgpt/INSTRUCOES.md).
4. Em **Knowledge**, anexe os 4 arquivos de `dist/chatgpt/`: `SKILL.md`, `ci.py`, `modelo-ci.docx` e `config.json`.
5. Em **Capabilities**, ligue **Code Interpreter & Data Analysis**.
6. Salve como **Only me** (tem seus dados) e use: anexe as fotos e peça a C.I.

Num **Projeto** é igual: cole as instruções nas instruções do projeto e anexe os mesmos arquivos.

## 3. Uso mensal

1. Tire foto da frente e do verso do cartão (2.ª quinzena e 1.ª quinzena).
2. Mande as fotos e peça "faz minha C.I.".
3. Confira a leitura e responda às perguntas.
4. Aprove o texto e baixe o `CI_AAAA-MM.docx`. Imprima e assine.

## Regras que o agente aplica

- **Período:** dia 16 do mês anterior até dia 15. A competência é o mês do dia 15.
- **Jornada:** seg–qui 9h, sex 8h, sáb/dom/feriado 0h. Diferença de até 10 min não conta.
- **Sábado de folga** vira "Sábado dd/mm/aaaa compensado;". Na semana dele, hora a mais de seg–sex vira **compensado** e não sai na C.I.
- **Almoço não batido** (só entrada da manhã e saída da tarde): deduz 1h e gera "Considerar hora de almoço ...".
- **Marcação esquecida:** o agente pergunta o horário e escreve "Considerar saída às HH:MM no dia ...".
- **Hora extra e banco:** uma linha por semana, com o motivo em maiúsculas.
- **Desconto:** "Descontar 1 hora e 15 minutos do BANCO DE HORAS referente ao dia ...".
- **Caixas do ASSUNTO:** marca "Cartão - horas extras" e "Cartão - compensação" quando há hora extra, compensação, banco ou desconto.

Detalhes completos em [ci/SKILL.md](ci/SKILL.md).

## Testar o motor

```bash
python tests/test_ci.py
```

Você também pode rodar o motor direto, sem IA:

```bash
python ci/scripts/ci.py config
python ci/scripts/ci.py analisar CI/entrada_2026-07.json
python ci/scripts/ci.py gerar CI/entrada_2026-07.json
```

## Atualizar

```bash
cd AgenteCI && git pull
```

Depois copie de novo a pasta `ci` (Claude Code e Antigravity) ou rode `python empacotar.py` e suba o zip/arquivos de novo (claude.ai e ChatGPT). O seu `config.json` e a pasta `pessoal/` não são sobrescritos pelo `git pull`.

## Privacidade

`ci/config.json`, `ci/pessoal/`, `CI/` e `dist/` estão no `.gitignore`. O modelo do repositório não tem nome, funcional nem carimbo de ninguém: os seus dados entram só na hora de gerar.
