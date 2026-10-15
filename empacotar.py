"""
Gera os pacotes para instalar o agente nas plataformas que pedem upload.

  python empacotar.py           -> dist/ci.zip (com seu config.json e ci/pessoal/, para a SUA conta)
  python empacotar.py --limpo   -> dist/ci.zip sem dados pessoais (para compartilhar)

Também cria dist/chatgpt/ com os arquivos soltos para um GPT/Projeto do ChatGPT.
dist/ está no .gitignore.
"""
import json
import os
import shutil
import sys
import zipfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(RAIZ, 'ci')
DIST = os.path.join(RAIZ, 'dist')
PESSOAL = ('config.json', 'pessoal')


def pessoal(rel):
    return rel.split(os.sep)[0] in PESSOAL


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    limpo = '--limpo' in sys.argv
    os.makedirs(DIST, exist_ok=True)
    destino = os.path.join(DIST, 'ci.zip')
    n = 0
    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as z:
        for pasta, dirs, arquivos in os.walk(SKILL):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for a in arquivos:
                caminho = os.path.join(pasta, a)
                rel = os.path.relpath(caminho, SKILL)
                if limpo and pessoal(rel):
                    continue
                z.write(caminho, os.path.join('ci', rel))  # zip contém a PASTA ci/, não os arquivos soltos
                n += 1
    print(f'{destino} ({n} arquivos{", sem dados pessoais" if limpo else ""})')

    # ChatGPT (GPT/Projeto): arquivos soltos, tudo vai para /mnt/data
    gpt = os.path.join(DIST, 'chatgpt')
    shutil.rmtree(gpt, ignore_errors=True)
    os.makedirs(gpt)
    copias = [('SKILL.md', 'SKILL.md'), ('scripts/ci.py', 'ci.py'), ('assets/modelo-ci.docx', 'modelo-ci.docx')]
    for origem, nome in copias:
        shutil.copy(os.path.join(SKILL, origem), os.path.join(gpt, nome))
    nomes = [n for _, n in copias]
    cfg_path = os.path.join(SKILL, 'config.json')
    if not limpo and os.path.isfile(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = json.load(f)
        # No ChatGPT tudo fica solto em /mnt/data: o modelo pessoal vira o modelo-ci.docx
        if cfg.get('modeloDocx'):
            shutil.copy(os.path.join(SKILL, cfg['modeloDocx']), os.path.join(gpt, 'modelo-ci.docx'))
            cfg['modeloDocx'] = None
        with open(os.path.join(gpt, 'config.json'), 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        nomes.append('config.json')
    print(f'{gpt}{os.sep} ({", ".join(nomes)})')
    if not limpo and os.path.isfile(cfg_path):
        print('Atenção: os pacotes têm seus dados pessoais. Suba só na sua conta; não compartilhe.')


if __name__ == '__main__':
    main()
