"""Testes de regressão do motor da C.I. Rodar: python tests/test_ci.py
Fixture = cartão real da competência 07/2026 (16/06 a 15/07)."""
import os
import sys
import tempfile
import traceback
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ci', 'scripts'))
import ci  # noqa: E402

CFG = {'segqui': 9, 'sex': 8, 'sab': 0, 'dom': 0, 'tol': 10}
CAMPOS = ['inicio1', 'fim1', 'inicio2', 'fim2', 'inicio3', 'fim3']


def reg(date, *marcas, feriado=False):
    marcas = list(marcas) + [''] * (6 - len(marcas))
    return {'date': date, **dict(zip(CAMPOS, marcas)), 'feriado': feriado}


REGISTROS = [
    reg('2026-06-16', '08:06', '12:00', '12:55', '17:56'),
    reg('2026-06-17', '05:43', '', '', '17:55'),
    reg('2026-06-18', '07:55', '11:56', '12:57', '17:55'),
    reg('2026-06-19', '07:56', '11:58', '12:55', '16:56'),
    reg('2026-06-22', '07:56', '11:58', '12:57', '17:56'),
    reg('2026-06-23', '08:05', '13:45', '14:44', '17:55'),
    reg('2026-06-24', '07:57', '', '', '17:33'),
    reg('2026-06-25', '07:55', '11:56', '12:56', '17:56'),
    reg('2026-06-26', '07:55', '', '', '17:38'),
    reg('2026-06-27', '07:55', '11:55'),
    reg('2026-06-29', '07:56', '12:04', '13:05', ''),
    reg('2026-06-30', '08:00', '12:03', '13:01', '17:55'),
    reg('2026-07-01', '07:55', '12:04', '13:02', '17:58'),
    reg('2026-07-02', '07:57', '12:02', '12:56', '17:55'),
    reg('2026-07-03', '07:54', '12:01', '13:00', '16:58'),
    reg('2026-07-06', '07:59', '12:01', '13:00', '17:57'),
    reg('2026-07-07', '07:55', '12:00', '12:58', '17:58'),
    reg('2026-07-08', '07:55', '11:56', '12:56', '17:56'),
    reg('2026-07-09', feriado=True),
    reg('2026-07-10', '07:55', '12:00', '13:00', '16:55'),
    reg('2026-07-13', '07:54', '12:03', '13:01', '17:56'),
    reg('2026-07-14', '07:55', '12:00', '13:00', '17:55'),
    reg('2026-07-15', '07:55', '12:00', '13:00', '17:55'),
]
ENTRADA = {'mes': 7, 'ano': 2026, 'registros': REGISTROS}
A = ci.analisar(ENTRADA, CFG)


def por_data(a, iso):
    return next((d for d in a['divergencias'] if d['date'] == iso), None)


def r2(x):
    return round(x, 2)


TESTES = []


def test(fn):
    TESTES.append(fn)
    return fn


# ---------------- período e semanas
@test
def periodo_16_06_a_15_07():
    d = ci.datas_do_periodo(7, 2026)
    assert (d[0], d[-1], len(d)) == ('2026-06-16', '2026-07-15', 30)


@test
def periodo_que_cruza_o_ano():
    d = ci.datas_do_periodo(1, 2027)
    assert (d[0], d[-1]) == ('2026-12-16', '2027-01-15')


@test
def sabado_na_mesma_semana_da_seg_sex():
    assert ci.semana_iso('2026-06-15') == ci.semana_iso('2026-06-20')
    assert ci.semana_iso('2026-06-20') != ci.semana_iso('2026-06-22')


# ---------------- horas trabalhadas
@test
def dia_completo():
    assert r2(ci.horas_trabalhadas(reg('x', '08:00', '12:00', '13:00', '18:00'))['total']) == 9


@test
def almoco_nao_batido_deduz_1h():
    h = ci.horas_trabalhadas(reg('x', '05:43', '', '', '17:55'))
    assert h['missingLunch'] and h['faltando'] == []
    assert r2(h['total']) == r2((12 * 60 + 12 - 60) / 60)


@test
def saida_faltando_vira_aviso():
    assert ci.horas_trabalhadas(reg('x', '07:56', '12:04', '13:05', ''))['faltando'] == ['fim2']


@test
def turno_que_vira_a_meia_noite():
    h = ci.horas_trabalhadas(reg('x', '08:00', '12:00', '13:00', '18:00', '19:00', '01:30'))
    assert h['cruzaMeiaNoite'] and h['horaSaidaExtra'] == '01:30' and r2(h['total']) == 15.5


# ---------------- divergências
@test
def dentro_da_tolerancia():
    assert por_data(A, '2026-06-23') is None and por_data(A, '2026-06-22') is None


@test
def sabado_de_folga_compensado_por_padrao():
    assert A['sabadosCompensados'] == ['2026-06-20', '2026-07-04', '2026-07-11']


@test
def hora_a_mais_em_semana_compensada():
    d = por_data(A, '2026-06-17')
    assert d['compensavel'] and d['padrao'] == 'compensado' and r2(d['diff']) == 2.2


@test
def sabado_trabalhado_extra():
    d = por_data(A, '2026-06-27')
    assert r2(d['diff']) == 4 and d['padrao'] == 'extra'


@test
def semana_com_sabado_trabalhado_nao_compensa():
    d = por_data(A, '2026-06-26')
    assert d['missingLunch'] and not d['compensavel'] and d['padrao'] == 'extra'


@test
def negativos():
    assert por_data(A, '2026-06-24')['padrao'] == 'ignorar'
    assert por_data(A, '2026-06-29')['padrao'] == 'ignorar' and por_data(A, '2026-06-29')['marcacaoFaltando']
    a = ci.analisar({'mes': 7, 'ano': 2026, 'registros': [reg('2026-06-30', '09:00', '12:00', '13:00', '18:00')]}, CFG)
    assert por_data(a, '2026-06-30')['padrao'] == 'descontar'


@test
def feriado_nao_diverge():
    assert por_data(A, '2026-07-09') is None


@test
def aviso_marcacao_faltando():
    assert [x['date'] for x in A['avisos']] == ['2026-06-29']


@test
def sabados_compensados_explicito():
    a = ci.analisar({**ENTRADA, 'sabadosCompensados': ['2026-06-20']}, CFG)
    assert a['sabadosCompensados'] == ['2026-06-20']


@test
def marcacao_informada_completa_o_dia():
    a = ci.analisar({**ENTRADA, 'marcacoesInformadas': {'2026-06-29': {'fim2': '18:00'}}}, CFG)
    assert a['avisos'] == [] and por_data(a, '2026-06-29') is None


# ---------------- formatação
@test
def formatar_datas():
    assert ci.formatar_datas(['2026-06-27']) == 'do dia 27/06/2026'
    assert ci.formatar_datas(['2026-05-20', '2026-05-18', '2026-05-19', '2026-05-21']) == 'dos dias 18, 19, 20 e 21/05/2026'
    assert ci.formatar_datas(['2026-06-29', '2026-06-30', '2026-07-01']) == 'dos dias 29 e 30/06/2026 e 01/07/2026'
    assert ci.formatar_datas(['2026-05-27', '2026-05-28'], 'em') == 'nos dias 27 e 28/05/2026'


@test
def duracao_por_extenso():
    assert ci.duracao_por_extenso(60) == '1 hora'
    assert ci.duracao_por_extenso(40) == '40 minutos'
    assert ci.duracao_por_extenso(135) == '2 horas e 15 minutos'


@test
def data_por_extenso():
    assert ci.data_por_extenso('2026-07-15') == 'São Paulo, 15 de julho de 2026.'


# ---------------- texto da C.I.
@test
def texto_completo():
    escolhas = {
        'dayChoices': {'2026-06-26': 'extra', '2026-06-29': 'ignorar'},
        'dayMotivos': {'2026-06-24': 'Jogo do Brasil', '2026-06-26': 'Festa Junina'},
        'marcacoesInformadas': {'2026-06-29': {'fim2': '18:00'}},
    }
    a = ci.analisar({**ENTRADA, 'marcacoesInformadas': escolhas['marcacoesInformadas']}, CFG)
    assert ci.texto_ci(a, escolhas) == '\n'.join([
        'Olá, por gentileza considerar devidas marcações.',
        'Considerar hora de almoço no dia 17/06/2026;',
        'Sábado 20/06/2026 compensado;',
        'Considerar hora de almoço no dia 24/06/2026 – JOGO DO BRASIL;',
        'Considerar hora de almoço no dia 26/06/2026 – FESTA JUNINA;',
        'Considerar horas excedentes do dia 26/06/2026 como HORA EXTRA – FESTA JUNINA;',
        'Considerar horas excedentes do dia 27/06/2026 como HORA EXTRA;',
        'Considerar saída às 18:00 no dia 29/06/2026;',
        'Sábado 04/07/2026 compensado;',
        'Sábado 11/07/2026 compensado;',
    ])


@test
def extras_da_semana_numa_linha():
    regs = [reg(d, '08:00', '12:00', '13:00', '19:00') for d in ('2026-06-29', '2026-06-30', '2026-07-01')]
    a = ci.analisar({'mes': 7, 'ano': 2026, 'registros': regs + [reg('2026-07-04', '08:00', '12:00')]}, CFG)
    linhas = [l['texto'] for l in ci.linhas_ci(a)]
    # sábado 04/07 trabalhado é da mesma semana ISO => mesma linha
    assert 'Considerar horas excedentes dos dias 29 e 30/06/2026 e 01 e 04/07/2026 como HORA EXTRA;' in linhas, linhas


@test
def banco_e_desconto():
    regs = [reg('2026-06-29', '08:00', '12:00', '13:00', '19:00'), reg('2026-06-30', '09:00', '12:00', '13:00', '18:00')]
    a = ci.analisar({'mes': 7, 'ano': 2026, 'registros': regs + [reg('2026-07-04', '08:00', '12:00')]}, CFG)
    linhas = [l['texto'] for l in ci.linhas_ci(a, {'dayChoices': {'2026-06-29': 'banco'}})]
    assert 'Considerar horas excedentes do dia 29/06/2026 para BANCO DE HORAS;' in linhas
    assert 'Descontar 1 hora do BANCO DE HORAS referente ao dia 30/06/2026;' in linhas


@test
def assuntos_marcados():
    assert ci.assuntos(A) == {'horasExtras': True, 'compensacao': True}


# ---------------- entrada compacta (formato que a IA escreve)
COMPACTA = {
    'mes': 7, 'ano': 2026,
    'q2': {'16': '08:06 12:00 12:55 17:56', '17': '05:43 - - 17:55', '18': '07:55 11:56 12:57 17:55',
           '19': '07:56 11:58 12:55 16:56', '22': '07:56 11:58 12:57 17:56', '23': '08:05 13:45 14:44 17:55',
           '24': '07:57 - - 17:33', '25': '07:55 11:56 12:56 17:56', '26': '07:55 - - 17:38', '27': '07:55 11:55',
           '29': '07:56 12:04 13:05', '30': '08:00 12:03 13:01 17:55', '31': '08:00 12:00 13:00 18:00'},
    'q1': {'1': '07:55 12:04 13:02 17:58', '2': '07:57 12:02 12:56 17:55', '3': '07:54 12:01 13:00 16:58',
           '6': '07:59 12:01 13:00 17:57', '7': '07:55 12:00 12:58 17:58', '8': '07:55 11:56 12:56 17:56',
           '9': 'F', '10': '07:55 12:00 13:00 16:55', '13': '07:54 12:03 13:01 17:56', '14': '07:55 12:00 13:00 17:55',
           '15': '07:55 12:00 13:00 17:55'},
    'notas': {'q2': {'20': 'C', '24': 'Jogo do Brasil'}, 'q1': {'4': 'C'}},
}


@test
def compacta_igual_a_registros():
    a = ci.analisar(COMPACTA, CFG)  # dia 31/06 não existe e é ignorado
    assert [(d['date'], r2(d['diff']), d['padrao']) for d in a['divergencias']] == \
           [(d['date'], r2(d['diff']), d['padrao']) for d in A['divergencias']]
    assert ci.texto_ci(a) == ci.texto_ci(A)


@test
def compacta_datas_feriado_e_notas():
    e = ci.expandir_cartao({'mes': 1, 'ano': 2027, 'q2': {'20': '8:00 12:00'}, 'q1': {'1': 'F'},
                            'notas': {'q2': {'20': 'X'}}})
    regs = {r['date']: r for r in e['registros']}
    assert regs['2026-12-20']['inicio1'] == '08:00' and regs['2027-01-01']['feriado']
    assert e['anotacoes'] == {'2026-12-20': 'X'}


@test
def relatorio_resume_leitura_e_divergencias():
    a = ci.analisar(COMPACTA, CFG)
    txt = ci.relatorio(a, {}, {'jornada': CFG})
    assert '24/06 qua  07:57 --:-- --:-- 17:33   nota: Jogo do Brasil' in txt
    assert '09/07 qui  FERIADO' in txt
    assert '17/06 qua  +2h12  compensado' in txt and 'AVISOS' in txt


# ---------------- .docx
@test
def docx_do_modelo_do_repositorio():
    funcionario = {'nome': 'Fulano de Tal', 'funcao': 'Técnico', 'setor': 'TV', 'empresa': '1',
                   'unidadeNum': '2', 'numero': '123', 'unidade': 'Campus X', 'cartao': '99'}
    linhas = [l['texto'] for l in ci.linhas_ci(A)]
    with tempfile.TemporaryDirectory() as tmp:
        saida = os.path.join(tmp, 'ci.docx')
        ci.gerar_docx(ci.MODELO_PADRAO, saida, linhas, ci.data_por_extenso('2026-07-15'), ci.assuntos(A), funcionario)
        xml = zipfile.ZipFile(saida).read('word/document.xml').decode('utf-8')
    assert '{{' not in xml
    assert 'Fulano de Tal' in xml and 'Campus X' in xml
    assert xml.count('Sábado 20/06/2026 compensado;') == 2  # caixa de texto + fallback VML
    assert 'São Paulo, 15 de julho de 2026.' in xml
    assert xml.count('w:char="F0FD"') == 4  # 2 caixas marcadas × 2 cópias


if __name__ == '__main__':
    ok = falhas = 0
    for fn in TESTES:
        try:
            fn()
            ok += 1
            print(f'  ok  {fn.__name__}')
        except Exception:
            falhas += 1
            print(f'FAIL  {fn.__name__}\n{traceback.format_exc()}')
    print(f'\n{ok} ok, {falhas} falha(s)')
    sys.exit(1 if falhas else 0)
