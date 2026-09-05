#!/usr/bin/env python3
"""Baixa população (IBGE) e IDHM (Ipeadata) por município de SP.

Gera contexto_municipios.csv, usado pelo tema "Contexto" do app.

Duas ressalvas honestas sobre estes dados:

1. O IDHM municipal mais recente que EXISTE é o de 2010. Depois disso o índice
   passou a ser calculado com a PNAD Contínua, que só tem representatividade
   estadual — a série anual do Ipeadata até 2024 não tem nenhum município. A
   versão com o Censo 2022 ainda não foi publicada. Não é escolha de fonte:
   é o estado da arte do indicador.
2. A população é a estimativa mais recente do IBGE. Cruzar IDHM de 2010 com
   população de hoje embute uma defasagem de mais de uma década, e o app diz
   isso na legenda em vez de esconder.

O join com a malha é por CÓDIGO IBGE de 7 dígitos (campo `codarea`), não por
nome — é o mesmo identificador nas três pontas, então não há risco de perder
município por acento ou grafia.
"""
import csv
import gzip
import io
import json
import urllib.request

UF = '35'  # São Paulo
SAIDA = 'contexto_municipios.csv'

URL_POP = ('https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1'
           '/variaveis/9324?localidades=N6[N3[35]]')
URL_CENSO = ('https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022'
             '/variaveis/93?localidades=N6[N3[35]]')
SERIES_IDHM = {
    'idhm': 'ADH_IDHM',
    'idhm_renda': 'ADH_IDHM_R',
    'idhm_longevidade': 'ADH_IDHM_L',
    'idhm_educacao': 'ADH_IDHM_E',
}
URL_IPEA = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{}')"
ANO_IDHM = '2010'


def baixa_json(url, rotulo):
    req = urllib.request.Request(url, headers={'User-Agent': 'mapa-economia-circular-sp/1.0'})
    with urllib.request.urlopen(req, timeout=180) as r:
        bruto = r.read()
        # alguns agregados do IBGE respondem gzipado mesmo sem Accept-Encoding
        if r.headers.get('Content-Encoding') == 'gzip' or bruto[:2] == b'\x1f\x8b':
            bruto = gzip.decompress(bruto)
    dados = json.loads(bruto.decode('utf-8'))
    print(f'  {rotulo}: ok')
    return dados


def le_agregado(url, rotulo):
    """Extrai {codigo_ibge: valor} de um agregado da API v3 do IBGE."""
    dados = baixa_json(url, rotulo)
    saida, periodo = {}, None
    for res in dados[0]['resultados']:
        for s in res['series']:
            cod = s['localidade']['id']
            for ano, valor in s['serie'].items():
                periodo = ano
                if valor not in ('...', '-', '..', None):
                    saida[cod] = int(valor)
    return saida, periodo


def le_ipeadata(sercodigo, rotulo):
    """Extrai {codigo_ibge: valor} da série do Ipeadata, só municípios de SP em 2010."""
    dados = baixa_json(URL_IPEA.format(sercodigo), rotulo)
    saida = {}
    for reg in dados['value']:
        if reg.get('NIVNOME') != 'Municípios':
            continue
        cod = str(reg.get('TERCODIGO') or '')
        if not cod.startswith(UF) or not reg.get('VALDATA', '').startswith(ANO_IDHM):
            continue
        if reg.get('VALVALOR') is not None:
            saida[cod] = round(float(reg['VALVALOR']), 3)
    return saida


def main():
    print('baixando população (IBGE)...')
    pop, ano_pop = le_agregado(URL_POP, f'estimativa municipal')
    censo, _ = le_agregado(URL_CENSO, 'Censo 2022')

    print('baixando IDHM (Ipeadata, base do Atlas do Desenvolvimento Humano)...')
    idhm = {campo: le_ipeadata(serie, serie) for campo, serie in SERIES_IDHM.items()}

    malha = json.load(open('geo_cache/municipios_sp_malha_com_ra.json', encoding='utf-8'))
    codigos = [f['properties']['codarea'] for f in malha['features']]
    nomes = {f['properties']['codarea']: f['properties']['nome'] for f in malha['features']}

    campos = (['cod_ibge', 'municipio', 'populacao', 'ano_populacao', 'censo2022']
              + list(SERIES_IDHM) + ['ano_idhm'])
    faltando = {c: 0 for c in ['populacao', 'censo2022'] + list(SERIES_IDHM)}
    with open(SAIDA, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for cod in codigos:
            linha = {'cod_ibge': cod, 'municipio': nomes[cod],
                     'populacao': pop.get(cod, ''), 'ano_populacao': ano_pop,
                     'censo2022': censo.get(cod, ''), 'ano_idhm': ANO_IDHM}
            for campo in SERIES_IDHM:
                linha[campo] = idhm[campo].get(cod, '')
            for k in faltando:
                if linha[k] == '':
                    faltando[k] += 1
            w.writerow(linha)

    n = len(codigos)
    print(f'\n-> {SAIDA}: {n} municípios')
    print(f'   população {ano_pop}: {n - faltando["populacao"]}/{n}'
          f' | Censo 2022: {n - faltando["censo2022"]}/{n}'
          f' | IDHM {ANO_IDHM}: {n - faltando["idhm"]}/{n}')
    if any(faltando.values()):
        print('   sem dado:', {k: v for k, v in faltando.items() if v})


if __name__ == '__main__':
    main()
