#!/usr/bin/env python3
"""
Agente da C.I. mensal — motor + gerador do .docx (só biblioteca padrão do Python 3.8+).

  python ci.py analisar <entrada.json> [--config ARQ]            divergências, sábados e avisos (JSON)
  python ci.py gerar    <entrada.json> [--config ARQ] [--saida PASTA]
                                                                 texto da C.I. + CI_AAAA-MM.docx
  python ci.py config   [--config ARQ]                           mostra qual config/modelo foi achado

Config (dados do funcionário, jornada, cidade, modelo): --config, variável CI_CONFIG,
./ci-config.json (pasta atual), config.json na pasta da skill ou ao lado deste script.
Formato: config.exemplo.json.
Entrada do mês: ver SKILL.md.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape, unescape

PASTA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
PASTA_SKILL = os.path.dirname(PASTA_SCRIPT)
# Skill instalada: assets/modelo-ci.docx. Arquivos soltos (ex.: /mnt/data no ChatGPT): ao lado do script.
MODELO_PADRAO = next((m for m in (os.path.join(PASTA_SKILL, 'assets', 'modelo-ci.docx'),
                                  os.path.join(PASTA_SCRIPT, 'modelo-ci.docx')) if os.path.isfile(m)),
                     os.path.join(PASTA_SKILL, 'assets', 'modelo-ci.docx'))

DIAS = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']
MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto',
         'setembro', 'outubro', 'novembro', 'dezembro']
ALMOCO_MIN = 60
CAMPOS = ['inicio1', 'fim1', 'inicio2', 'fim2', 'inicio3', 'fim3']
ROTULO_CAMPO = {
    'inicio1': 'entrada', 'fim1': 'saída para o almoço', 'inicio2': 'volta do almoço',
    'fim2': 'saída', 'inicio3': 'entrada extra', 'fim3': 'saída extra',
}
CABECALHO = 'Olá, por gentileza considerar devidas marcações.'
JORNADA_PADRAO = {'segqui': 9, 'sex': 8, 'sab': 0, 'dom': 0, 'tol': 10}


# ---------------------------------------------------------------- datas e horas

def arred(x):
    """Arredondamento comercial (0,5 sobe), igual ao Math.round do JS."""
    return int(math.floor(x + 0.5))


def parse_time(t):
    if not t:
        return None
    h, m = str(t).split(':')[:2]
    return int(h) * 60 + int(m)


def data_de(iso):
    return dt.date.fromisoformat(iso)


def dia_da_semana(iso):
    """0=Domingo ... 6=Sábado (como no JS)."""
    return (data_de(iso).weekday() + 1) % 7


def data_br(iso):
    return f'{iso[8:10]}/{iso[5:7]}/{iso[0:4]}'


def dia_seguinte(iso):
    return (data_de(iso) + dt.timedelta(days=1)).isoformat()


def datas_do_periodo(mes, ano):
    """Período de apuração: dia 16 do mês anterior até dia 15 do mês da competência."""
    ini = dt.date(ano - 1, 12, 16) if mes == 1 else dt.date(ano, mes - 1, 16)
    fim = dt.date(ano, mes, 15)
    return [(ini + dt.timedelta(days=i)).isoformat() for i in range((fim - ini).days + 1)]


def semana_iso(iso):
    """Semana ISO (seg–dom): 'AAAA-S'. Sábado fica na semana da seg–sex anterior."""
    a, s, _ = data_de(iso).isocalendar()
    return f'{a}-{s}'


def jornada_esperada(dow, feriado, cfg):
    if feriado:
        return 0
    if dow == 0:
        return cfg.get('dom', 0) or 0
    if dow == 6:
        return cfg.get('sab', 0) or 0
    if dow == 5:
        return cfg.get('sex', 0) or 0
    return cfg.get('segqui', 0) or 0


def horas_trabalhadas(r):
    """Horas do dia + sinais: almoço não batido, virada da meia-noite, marcação faltando."""
    t = [parse_time(r.get(c)) for c in CAMPOS]
    i1, f1, i2, f2 = t[:4]
    total, cruza, saida_extra = 0.0, False, ''
    for n in range(3):
        i, f = t[n * 2], t[n * 2 + 1]
        if i is None or f is None:
            continue
        fim = f
        if fim < i:
            fim += 24 * 60
            cruza, saida_extra = True, r.get(CAMPOS[n * 2 + 1])
        total += (fim - i) / 60
    # Almoço não batido (só entrada da manhã e saída da tarde): deduz 1h de almoço
    almoco = False
    if i1 is not None and f1 is None and i2 is None and f2 is not None:
        fim = f2 + (24 * 60 if f2 < i1 else 0)
        total = max(0, (fim - i1) - ALMOCO_MIN) / 60
        almoco = True
    # Turno com só uma das pontas (fora o caso do almoço) = marcação faltando
    faltando = []
    if not almoco:
        for n in range(3):
            if (t[n * 2] is None) != (t[n * 2 + 1] is None):
                faltando.append(CAMPOS[n * 2] if t[n * 2] is None else CAMPOS[n * 2 + 1])
    return {'total': total, 'missingLunch': almoco, 'cruzaMeiaNoite': cruza,
            'horaSaidaExtra': saida_extra, 'faltando': faltando}


# ---------------------------------------------------------------- entrada compacta

def mes_da_quinzena(q, mes, ano):
    """'q2' (dias 16–31) = mês anterior à competência; 'q1' (dias 1–15) = mês da competência."""
    if q == 'q1':
        return mes, ano
    return (12, ano - 1) if mes == 1 else (mes - 1, ano)


def expandir_cartao(entrada):
    """
    Formato compacto (menos texto para a IA escrever):
      "q2": {"16": "08:06 12:00 12:55 17:56", "17": "05:43 - - 17:55", "9": "F"}, "q1": {...}
      "notas": {"q2": {"20": "C", "24": "Jogo do Brasil"}, "q1": {...}}
    Horários na ordem: entrada, saída almoço, volta, saída, entrada extra, saída extra.
    "-" ou "?" = vazio · "F" = feriado. Vira entrada["registros"] e entrada["anotacoes"] (datas ISO).
    """
    mes, ano = int(entrada['mes']), int(entrada['ano'])
    regs = {}
    anot = dict(entrada.get('anotacoes') or {})
    for q in ('q2', 'q1'):
        m, a = mes_da_quinzena(q, mes, ano)
        for dia, linha in (entrada.get(q) or {}).items():
            try:
                iso = dt.date(a, m, int(dia)).isoformat()
            except ValueError:
                continue  # ex.: dia 31 em mês de 30 dias
            r = {'date': iso}
            tokens = str(linha).split()
            if tokens and tokens[0].upper() in ('F', 'FERIADO'):
                r['feriado'] = True
            else:
                for campo, tok in zip(CAMPOS, tokens):
                    if re.fullmatch(r'\d{1,2}:\d{2}', tok):
                        h, mi = tok.split(':')
                        r[campo] = f'{int(h):02d}:{mi}'
            regs[iso] = r
        for dia, nota in ((entrada.get('notas') or {}).get(q) or {}).items():
            try:
                anot[dt.date(a, m, int(dia)).isoformat()] = nota
            except ValueError:
                pass
    for r in entrada.get('registros') or []:  # registros explícitos têm prioridade
        regs[r['date']] = {**regs.get(r['date'], {}), **r}
    return {**entrada, 'registros': sorted(regs.values(), key=lambda r: r['date']), 'anotacoes': anot}


# ---------------------------------------------------------------- análise

def analisar(entrada, cfg):
    """
    entrada = {mes, ano, registros:[{date, inicio1..fim3, feriado}], sabadosCompensados?, marcacoesInformadas?}
    cfg = {segqui, sex, sab, dom, tol (minutos)}
    """
    entrada = expandir_cartao(entrada)
    regs = {r['date']: dict(r) for r in entrada.get('registros', [])}
    informadas = entrada.get('marcacoesInformadas') or {}
    for iso, campos in informadas.items():
        regs[iso] = {'date': iso, **regs.get(iso, {}), **campos}

    datas = datas_do_periodo(int(entrada['mes']), int(entrada['ano']))
    tol = (cfg.get('tol', 0) or 0) / 60
    dias, divergencias, avisos = [], [], []

    sabados = []
    for iso in datas:
        if dia_da_semana(iso) != 6:
            continue
        r = regs.get(iso, {})
        sabados.append({'date': iso, 'semana': semana_iso(iso),
                        'trabalhado': any(r.get(c) for c in CAMPOS), 'feriado': bool(r.get('feriado'))})
    folgas = [s['date'] for s in sabados if not s['trabalhado'] and not s['feriado']]
    escolhidos = entrada.get('sabadosCompensados')
    compensados = set(folgas if escolhidos is None else escolhidos)
    semana_compensa = {s['semana']: s['date'] in compensados for s in sabados}

    for iso in datas:
        r = regs.get(iso, {'date': iso})
        dow = dia_da_semana(iso)
        feriado = bool(r.get('feriado'))
        h = horas_trabalhadas(r)
        esperado = jornada_esperada(dow, feriado, cfg)
        diff = h['total'] - esperado
        semana = semana_iso(iso)
        dias.append({'date': iso, 'dow': DIAS[dow], 'feriado': feriado, 'esperado': esperado,
                     'trabalhado': h['total'], 'diff': diff})
        for c in h['faltando']:
            avisos.append({'date': iso, 'tipo': 'marcacao-faltando', 'campo': c,
                           'texto': f'{data_br(iso)} ({DIAS[dow]}): falta {ROTULO_CAMPO[c]}'})

        if h['total'] == 0 and esperado == 0:
            continue
        if abs(diff) <= tol and not h['cruzaMeiaNoite'] and not h['missingLunch']:
            continue
        dia_util = 1 <= dow <= 5
        compensavel = diff > 0 and dia_util and semana_compensa.get(semana, False)
        # Marcação faltando é quase sempre esquecimento: não desconta por padrão
        faltando = len(h['faltando']) > 0
        if diff > tol:
            padrao = 'compensado' if compensavel else 'extra'
        elif diff < -tol:
            padrao = 'ignorar' if (h['total'] == 0 or h['missingLunch'] or faltando) else 'descontar'
        else:
            padrao = 'ignorar'
        divergencias.append({
            'date': iso, 'dow': DIAS[dow] + (' · FERIADO' if feriado else ''), 'semana': semana,
            'ehDiaUtil': dia_util, 'esperado': esperado, 'trabalhado': h['total'], 'diff': diff,
            'compensavel': compensavel, 'padrao': padrao, 'marcacaoFaltando': faltando,
            'missingLunch': h['missingLunch'], 'cruzaMeiaNoite': h['cruzaMeiaNoite'],
            'horaSaidaExtra': h['horaSaidaExtra'],
        })

    return {'datas': datas, 'dias': dias, 'divergencias': divergencias, 'sabados': sabados,
            'sabadosCompensados': sorted(compensados), 'avisos': avisos,
            'registros': regs, 'anotacoes': entrada.get('anotacoes') or {}}


# ---------------------------------------------------------------- texto da C.I.

def formatar_datas(datas, prep='de'):
    """'do dia 27/06/2026' · 'dos dias 18, 19 e 20/05/2026' · prep 'em' => no/nos."""
    um, varios = ('no dia', 'nos dias') if prep == 'em' else ('do dia', 'dos dias')
    ordem = sorted(datas)
    if len(ordem) == 1:
        return f'{um} {data_br(ordem[0])}'
    grupos = {}
    for d in ordem:
        grupos.setdefault(d[:7], []).append(d[8:10])
    partes = []
    for k, dias in grupos.items():
        fim = f'/{k[5:7]}/{k[:4]}'
        partes.append(dias[0] + fim if len(dias) == 1 else f'{", ".join(dias[:-1])} e {dias[-1]}{fim}')
    return f'{varios} {" e ".join(partes)}'


def duracao_por_extenso(minutos):
    h, m = divmod(minutos, 60)
    hs = '1 hora' if h == 1 else f'{h} horas'
    ms = '1 minuto' if m == 1 else f'{m} minutos'
    if h and m:
        return f'{hs} e {ms}'
    return hs if h else ms


def sufixo_motivo(m):
    return f' – {m.strip().upper()}' if m and m.strip() else ''


def agrupar(itens, chave):
    grupos = {}
    for it in itens:
        g = grupos.setdefault(chave(it), {'motivo': it.get('motivo', ''), 'dates': []})
        g['dates'].append(it['date'])
    return sorted(grupos.values(), key=lambda g: g['dates'][0])


def linhas_ci(analise, escolhas=None):
    """
    escolhas = {dayChoices:{iso:'extra'|'banco'|'compensado'|'descontar'|'ignorar'}, dayMotivos:{iso:txt},
                marcacoesInformadas:{iso:{campo:'HH:MM'}}, linhasExtras:[{date, texto}]}
    Retorna [{date, ordem, texto}] ordenado por data.
    """
    escolhas = escolhas or {}
    choices = escolhas.get('dayChoices') or {}
    motivos = escolhas.get('dayMotivos') or {}
    informadas = escolhas.get('marcacoesInformadas') or {}
    escolha = lambda dv: choices.get(dv['date']) or dv['padrao']
    out = []
    add = lambda date, ordem, texto: out.append({'date': date, 'ordem': ordem, 'texto': texto})
    divs = analise['divergencias']

    for iso in analise['sabadosCompensados']:
        add(iso, 0, f'Sábado {data_br(iso)} compensado;')

    almocos = [{'date': d['date'], 'motivo': motivos.get(d['date'], '')} for d in divs if d['missingLunch']]
    for g in agrupar(almocos, lambda it: it['motivo']):
        add(g['dates'][0], 1, f'Considerar hora de almoço {formatar_datas(g["dates"], "em")}{sufixo_motivo(g["motivo"])};')

    for iso, campos in informadas.items():
        for c in CAMPOS:
            if campos.get(c):
                add(iso, 2, f'Considerar {ROTULO_CAMPO[c]} às {campos[c]} {formatar_datas([iso], "em")}{sufixo_motivo(motivos.get(iso))};')

    def positivos(tipo):
        return [{'date': d['date'], 'semana': d['semana'], 'motivo': motivos.get(d['date'], '')}
                for d in divs if d['diff'] > 0 and escolha(d) == tipo]

    for g in agrupar(positivos('extra'), lambda it: f'{it["semana"]}|{it["motivo"]}'):
        add(g['dates'][0], 3, f'Considerar horas excedentes {formatar_datas(g["dates"])} como HORA EXTRA{sufixo_motivo(g["motivo"])};')
    for d in divs:
        if d['cruzaMeiaNoite'] and d['diff'] > 0 and escolha(d) == 'extra':
            add(d['date'], 3, f'Considerar saída extra do dia {data_br(d["date"])} às {d["horaSaidaExtra"]} '
                              f'da manhã do dia {data_br(dia_seguinte(d["date"]))};')
    for g in agrupar(positivos('banco'), lambda it: f'{it["semana"]}|{it["motivo"]}'):
        add(g['dates'][0], 4, f'Considerar horas excedentes {formatar_datas(g["dates"])} para BANCO DE HORAS{sufixo_motivo(g["motivo"])};')

    for d in divs:
        if d['diff'] < 0 and escolha(d) == 'descontar':
            motivo = f' – Motivo: {motivos[d["date"]].strip()}' if motivos.get(d['date']) else ''
            add(d['date'], 5, f'Descontar {duracao_por_extenso(arred(-d["diff"] * 60))} do BANCO DE HORAS '
                              f'referente ao dia {data_br(d["date"])}{motivo};')

    # Dia ignorado com motivo vira justificativa (se o motivo já não saiu em outra linha)
    ja_usado = {a['date'] for a in almocos} | set(informadas)
    for d in divs:
        if escolha(d) == 'ignorar' and motivos.get(d['date']) and d['date'] not in ja_usado:
            add(d['date'], 6, f'Justificativa referente ao dia {data_br(d["date"])}: {motivos[d["date"]].strip()};')

    for l in escolhas.get('linhasExtras') or []:
        add(l.get('date') or '9999', 7, l['texto'])

    return sorted(out, key=lambda l: (l['date'], l['ordem']))


def texto_ci(analise, escolhas=None):
    return '\n'.join([CABECALHO] + [l['texto'] for l in linhas_ci(analise, escolhas)])


def data_por_extenso(iso, cidade='São Paulo'):
    d = data_de(iso)
    return f'{cidade}, {d.day} de {MESES[d.month - 1]} de {d.year}.'


def assuntos(analise, escolhas=None):
    """Caixas do ASSUNTO a marcar."""
    choices = (escolhas or {}).get('dayChoices') or {}
    escolha = lambda dv: choices.get(dv['date']) or dv['padrao']
    divs = analise['divergencias']
    return {
        'horasExtras': any(d['diff'] > 0 and escolha(d) == 'extra' for d in divs),
        'compensacao': bool(analise['sabadosCompensados']) or any(
            (d['diff'] > 0 and escolha(d) in ('banco', 'compensado')) or (d['diff'] < 0 and escolha(d) == 'descontar')
            for d in divs),
    }


# ---------------------------------------------------------------- .docx

MARCA_OBS = 'considerar devidas marca'
NEGRITO = re.compile(r'(HORA EXTRA|BANCO DE HORAS)')
# Só parágrafos "folha": o que ancora uma caixa de texto contém outros <w:p> e fica de fora
PARAGRAFO = re.compile(r'<w:p\b[^>]*>(?:(?!<w:p\b).)*?</w:p>', re.S)
TEXTO = re.compile(r'<w:t(?:\s[^>]*)?>(.*?)</w:t>', re.S)
CAIXA_TEXTO = re.compile(r'<w:txbxContent>.*?</w:txbxContent>', re.S)
CAMPOS_FUNCIONARIO = {
    'NOME': 'nome', 'FUNCAO': 'funcao', 'SETOR': 'setor', 'EMPRESA': 'empresa',
    'UNIDADE_NUM': 'unidadeNum', 'NUMERO': 'numero', 'UNIDADE': 'unidade', 'CARTAO': 'cartao',
}


def texto_do_paragrafo(p):
    return unescape(''.join(TEXTO.findall(p)))


def tamanho_fonte(n_linhas):
    # O quadro de observações tem altura fixa: encolhe a fonte quando o mês tem muita linha
    if n_linhas <= 11:
        return 22
    if n_linhas <= 14:
        return 20
    return 18


def montar_paragrafos(linhas, p_modelo):
    ppr = re.search(r'<w:pPr>.*?</w:pPr>', p_modelo, re.S)
    ppr = ppr.group(0) if ppr else ''
    rpr = re.search(r'<w:r\b[^>]*>\s*(<w:rPr>.*?</w:rPr>)', p_modelo, re.S)
    rpr = rpr.group(1) if rpr else '<w:rPr></w:rPr>'
    sz = tamanho_fonte(len(linhas))
    ppr = ppr.replace('w:val="22"', f'w:val="{sz}"')
    rpr = rpr.replace('w:val="22"', f'w:val="{sz}"')
    rpr_negrito = rpr if '<w:b/>' in rpr else rpr.replace('</w:rPr>', '<w:b/><w:bCs/></w:rPr>')
    saida = []
    for linha in linhas:
        runs = []
        for pedaco in NEGRITO.split(linha):
            if pedaco:
                props = rpr_negrito if NEGRITO.fullmatch(pedaco) else rpr
                runs.append(f'<w:r>{props}<w:t xml:space="preserve">{escape(pedaco)}</w:t></w:r>')
        saida.append(f'<w:p>{ppr}{"".join(runs)}</w:p>')
    return ''.join(saida)


def trocar_observacoes(xml, linhas):
    """Mantém a 1ª linha do quadro ('Olá, ...') e troca as demais. A caixa aparece 2× (Word + fallback VML)."""
    trocas = 0

    def trocar(m):
        nonlocal trocas
        bloco = m.group(0)
        if MARCA_OBS not in unescape(bloco):
            return bloco
        paragrafos = list(PARAGRAFO.finditer(bloco))
        if len(paragrafos) < 2:
            return bloco
        trocas += 1
        return bloco[:paragrafos[0].end()] + montar_paragrafos(linhas, paragrafos[1].group(0)) + '</w:txbxContent>'

    xml = CAIXA_TEXTO.sub(trocar, xml)
    if not trocas:
        raise SystemExit('Quadro de observações não encontrado no modelo (procurei "Olá, por gentileza considerar devidas marcações").')
    return xml


def trocar_data(xml, data):
    trocas = 0

    def trocar(m):
        nonlocal trocas
        p = m.group(0)
        txt = texto_do_paragrafo(p)
        if not re.match(r'^\s*\S.*, *\d{1,2} de \S+ (de )?\d{4}\.?\s*$', txt):
            return p
        recuo = re.match(r'^\s*', txt).group(0)
        primeiro = [True]

        def sub_t(_):
            if primeiro[0]:
                primeiro[0] = False
                return f'<w:t xml:space="preserve">{escape(recuo + data)}</w:t>'
            return '<w:t></w:t>'

        trocas += 1
        return TEXTO.sub(sub_t, p)

    xml = PARAGRAFO.sub(trocar, xml)
    if not trocas:
        print('Aviso: linha da data ("Cidade, dd de mês de aaaa.") não encontrada; data mantida.', file=sys.stderr)
    return xml


def marcar_assunto(xml, rotulo):
    """Item do ASSUNTO é lista com marcador de caixa vazia (Wingdings). Marcado: tira a lista e põe ☒."""
    caixa = ('<w:r><w:rPr><w:rFonts w:ascii="Wingdings" w:hAnsi="Wingdings" w:cs="Wingdings"/>'
             '<w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:sym w:font="Wingdings" w:char="F0FD"/></w:r>'
             '<w:r><w:tab/></w:r>')

    def trocar(m):
        p = m.group(0)
        if texto_do_paragrafo(p).strip() != rotulo:
            return p
        p = re.sub(r'<w:numPr>.*?</w:numPr>', '', p, flags=re.S).replace('w:val="num"', 'w:val="left"')
        return p.replace('</w:pPr>', '</w:pPr>' + caixa, 1)

    return PARAGRAFO.sub(trocar, xml)


def preencher_funcionario(xml, funcionario):
    """Troca {{NOME}}, {{FUNCAO}}... do modelo pelos dados do config (modelo pessoal sem marcadores: nada muda)."""
    for marcador, chave in CAMPOS_FUNCIONARIO.items():
        xml = xml.replace('{{' + marcador + '}}', escape(str((funcionario or {}).get(chave, ''))))
    return xml


def gerar_docx(modelo, saida, linhas, data, marcar, funcionario=None):
    with zipfile.ZipFile(modelo) as zin:
        xml = zin.read('word/document.xml').decode('utf-8')
        xml = preencher_funcionario(xml, funcionario)
        xml = trocar_observacoes(xml, linhas)
        xml = trocar_data(xml, data)
        if marcar.get('horasExtras'):
            xml = marcar_assunto(xml, 'Cartão - horas extras')
        if marcar.get('compensacao'):
            xml = marcar_assunto(xml, 'Cartão - compensação')
        if '{{' in xml:
            print('Aviso: sobrou marcador {{...}} no modelo; confira os dados do funcionário no config.', file=sys.stderr)
        with zipfile.ZipFile(saida, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                dados = xml.encode('utf-8') if item.filename == 'word/document.xml' else zin.read(item.filename)
                zout.writestr(item, dados)


# ---------------------------------------------------------------- config e CLI

def achar_config(caminho=None):
    candidatos = [caminho, os.environ.get('CI_CONFIG'), os.path.join(os.getcwd(), 'ci-config.json'),
                  os.path.join(PASTA_SKILL, 'config.json'), os.path.join(PASTA_SCRIPT, 'config.json')]
    for c in candidatos:
        if c and os.path.isfile(c):
            with open(c, encoding='utf-8') as f:
                cfg = json.load(f)
            cfg['_arquivo'] = os.path.abspath(c)
            return cfg
    if caminho:
        raise SystemExit(f'Config não encontrado: {caminho}')
    return None


def caminho_modelo(cfg):
    m = (cfg or {}).get('modeloDocx')
    if not m:
        return MODELO_PADRAO
    if os.path.isabs(m):
        return m
    return os.path.join(os.path.dirname(cfg['_arquivo']), m)


def jornada(cfg):
    return {**JORNADA_PADRAO, **((cfg or {}).get('jornada') or {})}


def ler_json(caminho):
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def hm(h):
    m = arred(abs(h) * 60)
    return f'{"-" if h < 0 else "+"}{m // 60}h{m % 60:02d}'


def relatorio(a, choices, cfg):
    """Texto curto para a IA mostrar/copiar: leitura, sábados, divergências e avisos."""
    sem = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb']
    d0, d1 = a['datas'][0], a['datas'][-1]
    out = [f'Período {data_br(d0)} a {data_br(d1)}', '', 'LEITURA (entrada | almoço | volta | saída | extra)']
    for iso in a['datas']:
        r, nota = a['registros'].get(iso, {}), a['anotacoes'].get(iso)
        marcas = [r.get(c) or '--:--' for c in CAMPOS]
        if not any(r.get(c) for c in CAMPOS) and not r.get('feriado') and not nota:
            continue
        horas = 'FERIADO' if r.get('feriado') else ' '.join(marcas[:4]) + (f' | {marcas[4]}-{marcas[5]}' if r.get('inicio3') or r.get('fim3') else '')
        out.append(f'{iso[8:10]}/{iso[5:7]} {sem[dia_da_semana(iso)]}  {horas}' + (f'   nota: {nota}' if nota else ''))
    sab = []
    for s in a['sabados']:
        estado = 'trabalhado' if s['trabalhado'] else 'feriado' if s['feriado'] else \
            'folga → compensado' if s['date'] in a['sabadosCompensados'] else 'folga (não compensado)'
        sab.append(f'{data_br(s["date"])[:5]} {estado}')
    out += ['', 'SÁBADOS: ' + ' · '.join(sab), '', 'DIVERGÊNCIAS (saldo · escolha atual · padrão)']
    if not a['divergencias']:
        out.append('nenhuma')
    for d in a['divergencias']:
        sinais = [t for t, ok in (('almoço não batido', d['missingLunch']), ('marcação faltando', d['marcacaoFaltando']),
                                  (f'sai {d["horaSaidaExtra"]} do dia seguinte', d['cruzaMeiaNoite']),
                                  ('semana de sábado compensado', d['compensavel'])) if ok]
        out.append(f'{data_br(d["date"])[:5]} {sem[dia_da_semana(d["date"])]}  {hm(d["diff"])}  '
                   f'{choices.get(d["date"]) or d["padrao"]} (padrão {d["padrao"]})  sem {d["semana"]}'
                   + (f'  [{"; ".join(sinais)}]' if sinais else ''))
    if a['avisos']:
        out += ['', 'AVISOS'] + [x['texto'] for x in a['avisos']]
    if not cfg:
        out += ['', 'SEM CONFIG: usando jornada padrão (seg–qui 9h, sex 8h, tolerância 10 min). Peça os dados do funcionário antes de gerar.']
    return '\n'.join(out)


def cmd_analisar(args):
    cfg = achar_config(args.config)
    entrada = ler_json(args.entrada)
    a = analisar(entrada, jornada(cfg))
    choices = entrada.get('dayChoices') or {}
    if not args.json:
        print(relatorio(a, choices, cfg))
        return
    saida = {
        'periodo': f'{a["datas"][0]} a {a["datas"][-1]}',
        'sabados': a['sabados'],
        'sabadosCompensados': a['sabadosCompensados'],
        'divergencias': [{
            'date': d['date'], 'dow': d['dow'], 'semana': d['semana'], 'esperado': d['esperado'],
            'trabalhado': hm(d['trabalhado'])[1:], 'diff': hm(d['diff']),
            'escolha': choices.get(d['date']) or d['padrao'], 'padrao': d['padrao'],
            **({'compensavel': True} if d['compensavel'] else {}),
            **({'almocoNaoBatido': True} if d['missingLunch'] else {}),
            **({'marcacaoFaltando': True} if d['marcacaoFaltando'] else {}),
            **({'cruzaMeiaNoite': d['horaSaidaExtra']} if d['cruzaMeiaNoite'] else {}),
        } for d in a['divergencias']],
        'avisos': [x['texto'] for x in a['avisos']],
    }
    if not cfg:
        saida['semConfig'] = 'Nenhum config achado: usando jornada padrão (seg–qui 9h, sex 8h, tolerância 10 min).'
    print(json.dumps(saida, ensure_ascii=False, indent=2))


def json_do_app(cfg, entrada, a, texto):
    """Mesmo formato do Exportar/Importar (.json) do app Folha de Ponto (opcional: só se o config tiver "app")."""
    informadas = entrada.get('marcacoesInformadas') or {}
    regs = {r['date']: r for r in entrada.get('registros', [])}
    registros = []
    for date in a['datas']:
        r = {**regs.get(date, {}), **informadas.get(date, {})}
        o = {'date': date, **{c: r.get(c) or '' for c in CAMPOS}, 'feriado': bool(r.get('feriado'))}
        o['temTurno2'] = bool(o['inicio2'] or o['fim2'])
        o['temTurno3'] = bool(o['inicio3'] or o['fim3'])
        registros.append(o)
    choices = entrada.get('dayChoices') or {}
    j = jornada(cfg)
    return {
        'mes': str(entrada['mes']), 'ano': str(entrada['ano']), **cfg['app'],
        'jtSegQui': str(j['segqui']), 'jtSex': str(j['sex']), 'jtSab': str(j['sab']),
        'jtDom': str(j['dom']), 'jtTol': str(j['tol']),
        'ciObs': texto, 'dayChoices': {d['date']: choices.get(d['date']) or d['padrao'] for d in a['divergencias']},
        'dayMotivos': entrada.get('dayMotivos') or {}, 'registros': registros,
    }


def cmd_gerar(args):
    cfg = achar_config(args.config)
    if not cfg:
        raise SystemExit('Nenhum config achado. Crie ci-config.json (modelo: config.exemplo.json) com os dados do funcionário.')
    entrada = expandir_cartao(ler_json(args.entrada))
    a = analisar(entrada, jornada(cfg))
    linhas = entrada.get('linhasManuais') or [l['texto'] for l in linhas_ci(a, entrada)]
    texto = '\n'.join([CABECALHO] + linhas)
    mes, ano = int(entrada['mes']), int(entrada['ano'])
    data_ci = entrada.get('dataCI') or f'{ano}-{mes:02d}-15'
    cidade = cfg.get('cidade') or 'São Paulo'
    tag = f'{ano}-{mes:02d}'
    pasta = args.saida or os.path.join(os.getcwd(), 'CI')
    os.makedirs(pasta, exist_ok=True)

    modelo = caminho_modelo(cfg)
    if not os.path.isfile(modelo):
        raise SystemExit(f'Modelo .docx não encontrado: {modelo}')
    docx = os.path.join(pasta, f'CI_{tag}.docx')
    gerar_docx(modelo, docx, linhas, data_por_extenso(data_ci, cidade), assuntos(a, entrada), cfg.get('funcionario'))

    print(texto)
    print(f'\n--\n{len(linhas)} linha(s) · {data_por_extenso(data_ci, cidade)}')
    print(f'docx: {docx}')
    if cfg.get('app'):
        app = os.path.join(pasta, f'Folha_Ponto_{MESES[mes - 1].capitalize()}_{ano}.json')
        with open(app, 'w', encoding='utf-8') as f:
            json.dump(json_do_app(cfg, entrada, a, texto), f, ensure_ascii=False, indent=2)
        print(f'app:  {app}')


def cmd_config(args):
    cfg = achar_config(args.config)
    print(json.dumps({
        'config': cfg['_arquivo'] if cfg else None,
        'modelo': caminho_modelo(cfg),
        'modeloExiste': os.path.isfile(caminho_modelo(cfg)),
        'jornada': jornada(cfg),
        'funcionario': (cfg or {}).get('funcionario'),
    }, ensure_ascii=False, indent=2))


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='Agente da C.I. mensal')
    sub = p.add_subparsers(dest='cmd', required=True)
    for nome in ('analisar', 'gerar'):
        s = sub.add_parser(nome)
        s.add_argument('entrada')
        s.add_argument('--config')
        if nome == 'gerar':
            s.add_argument('--saida', help='pasta de saída (padrão: ./CI)')
        else:
            s.add_argument('--json', action='store_true', help='saída em JSON em vez do relatório')
    s = sub.add_parser('config')
    s.add_argument('--config')
    args = p.parse_args(argv)
    {'analisar': cmd_analisar, 'gerar': cmd_gerar, 'config': cmd_config}[args.cmd](args)


if __name__ == '__main__':
    main()
