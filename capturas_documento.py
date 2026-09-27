#!/usr/bin/env python3
"""Gera as capturas de tela usadas no relatório de entrega.

Usa o Chrome já instalado na máquina via Playwright (channel='chrome'), então não
baixa navegador nenhum. Requer o app servido localmente:

    python -m http.server 8765 --bind 127.0.0.1

Cada captura é um estado do app reproduzido por código — se o app mudar, basta
rodar de novo para o documento acompanhar.
"""
import sys

from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:8765/index.html'
SAIDA = 'docs/capturas'
VIEWPORT = {'width': 1400, 'height': 860}

# (arquivo, descrição, JS que monta o estado)
CENARIOS = [
    ('01_hub_estado', 'Hub Circular — visão do estado', ''),
    ('02_hub_regiao', 'Hub Circular — região aberta nos municípios',
     "irRegiao('9ª Araçatuba');"),
    ('03_hub_municipio', 'Hub Circular — município com os estabelecimentos',
     "irRegiao('7ª Bauru'); irMunicipio('BAURU', 'Bauru');"),
    ('04_tratamento', 'Tratamento de resíduos — cinco camadas',
     "document.querySelector('[data-tema=\"tratamento\"]').click();"),
    ('05_ciclo', 'Ciclo biológico — potência por usina',
     "document.querySelector('[data-tema=\"biologico\"]').click();"),
    ('06_contexto', 'Contexto — IDHM por município',
     "document.querySelector('[data-tema=\"contexto\"]').click();"
     "document.querySelector('[data-ctxvar=\"idhm\"]').click();"),
]


def espera_mapa(pg, ms=3500):
    """Espera a animação de enquadramento terminar e os tiles carregarem."""
    pg.wait_for_timeout(ms)
    for _ in range(20):
        if pg.evaluate('!map.isMoving() && map.areTilesLoaded()'):
            break
        pg.wait_for_timeout(500)
    pg.evaluate('map.triggerRepaint()')
    pg.wait_for_timeout(800)


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch(channel='chrome', headless=True,
                                args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        for arquivo, descricao, js in CENARIOS:
            # página nova a cada cenário: nenhum estado herdado do anterior
            pg = nav.new_page(viewport=VIEWPORT, device_scale_factor=2)
            erros = []
            pg.on('pageerror', lambda e: erros.append(str(e)))
            pg.goto(URL, wait_until='domcontentloaded', timeout=90000)
            pg.wait_for_function('typeof map !== "undefined" && map.getLayer("ra-fill")',
                                 timeout=90000)
            espera_mapa(pg)
            if js:
                pg.evaluate(js)
                espera_mapa(pg)
            if erros:
                print(f'  ERRO em {arquivo}: {erros[0][:120]}')
                return 1
            destino = f'{SAIDA}/{arquivo}.jpg'
            pg.screenshot(path=destino, type='jpeg', quality=86)
            print(f'  {destino} — {descricao}')
            pg.close()
        nav.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
