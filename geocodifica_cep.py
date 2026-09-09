#!/usr/bin/env python3
"""Segunda passada de geocodificação, por CEP, para os endereços que o Nominatim não achou.

O Nominatim busca o logradouro no OpenStreetMap, que mapeia mal ruas de cidades
pequenas do interior — daí 1.790 endereços (17%) sem coordenada, concentrados
justamente nas regiões que o mapa aponta como vazias.

Mas todos esses registros têm CEP de 8 dígitos, e o CEP tem coordenada em bases
que não dependem do OSM. Duas são usadas aqui, em ordem:

  1. BrasilAPI v2  — em amostra de 60 CEPs: 97% com coordenada, 100% delas dentro
     do município correto, nenhum erro.
  2. AwesomeAPI    — reserva para o que a BrasilAPI não tem. Responde 100%, mas
     8% das coordenadas caem fora do município (acerta o nome da cidade e devolve
     um ponto na Grande SP), então a validação abaixo é obrigatória.

VALIDAÇÃO: toda coordenada é testada contra o polígono do município declarado no
CNPJ. Se cair fora, é descartada. É o que separa as duas APIs — sem isso, a
reserva injetaria erro grosseiro na base.

PRECISÃO: a coordenada é do CEP, não do número. Em CEP de logradouro cai na rua
certa; em CEP geral de município (terminado em 000) cai no centro da cidade. Por
isso o status gravado é `cep_*`, e o mapa marca esses pontos como aproximados —
mesmo tratamento que o fallback `cep_aproximado` da primeira passada já recebia.
"""
import csv
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from shapely.geometry import Point, shape

from enriquece import chave

ENTRADA = 'empresas_sp_circular_geo.csv'
CACHE = 'geo_cache/cep_coordenadas.json'
MALHA = 'geo_cache/municipios_sp_malha_com_ra.json'
UA = {'User-Agent': 'mapa-economia-circular-sp/1.0 (projeto SENAC SP)'}
PAUSA = 0.15
# a latência da API domina o tempo, não a pausa. 4 conexões simultâneas cortam a
# execução de ~50 para ~12 minutos e continuam sendo educadas com uma API pública
# mantida pela comunidade.
CONCORRENCIA = 4


def busca_brasilapi(cep):
    url = f'https://brasilapi.com.br/api/cep/v2/{cep}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            d = json.loads(r.read().decode('utf-8'))
    except Exception:
        return None
    co = (d.get('location') or {}).get('coordinates') or {}
    if co.get('latitude') and co.get('longitude'):
        return float(co['latitude']), float(co['longitude']), 'cep_brasilapi'
    return None


def busca_awesomeapi(cep):
    url = f'https://cep.awesomeapi.com.br/json/{cep}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            d = json.loads(r.read().decode('utf-8'))
    except Exception:
        return None
    if d.get('lat') and d.get('lng'):
        return float(d['lat']), float(d['lng']), 'cep_awesomeapi'
    return None


def main():
    poligonos = {chave(f['properties']['nome']): shape(f['geometry'])
                 for f in json.load(open(MALHA, encoding='utf-8'))['features']}

    linhas = list(csv.DictReader(open(ENTRADA, encoding='utf-8')))
    campos = list(linhas[0].keys())
    pendentes = [r for r in linhas if not r['latitude']]
    ceps = sorted({r['cep'] for r in pendentes if r['cep']})
    print(f'{len(pendentes)} endereços sem coordenada, {len(ceps)} CEPs distintos')

    cache = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    print(f'{len(cache)} CEPs já em cache')

    faltam = [c for c in ceps if c not in cache]
    print(f'{len(faltam)} CEPs a consultar')
    trava = threading.Lock()
    feitos = [0]

    def consulta(cep):
        achado = busca_brasilapi(cep) or busca_awesomeapi(cep)
        registro = ({'lat': achado[0], 'lon': achado[1], 'fonte': achado[2]}
                    if achado else None)
        with trava:
            cache[cep] = registro
            feitos[0] += 1
            if feitos[0] % 100 == 0:
                json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
                print(f'  {feitos[0]}/{len(faltam)} consultados', flush=True)
        time.sleep(PAUSA)

    if faltam:
        with ThreadPoolExecutor(max_workers=CONCORRENCIA) as pool:
            list(pool.map(consulta, faltam))
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'))

    # aplica, validando cada ponto contra o polígono do município declarado
    aplicados, fora, sem_dado = 0, 0, 0
    por_fonte = {}
    for r in linhas:
        if r['latitude']:
            continue
        c = cache.get(r['cep'])
        if not c:
            sem_dado += 1
            continue
        pol = poligonos.get(chave(r['municipio']))
        if pol and not pol.contains(Point(c['lon'], c['lat'])):
            fora += 1
            continue
        r['latitude'], r['longitude'] = f"{c['lat']:.6f}", f"{c['lon']:.6f}"
        r['geocode_status'] = c['fonte']
        por_fonte[c['fonte']] = por_fonte.get(c['fonte'], 0) + 1
        aplicados += 1

    tmp = ENTRADA + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    os.replace(tmp, ENTRADA)

    total = len(linhas)
    com_coord = sum(1 for r in linhas if r['latitude'])
    print(f'\naplicados: {aplicados} | descartados por cair fora do município: {fora} '
          f'| CEP sem coordenada em nenhuma fonte: {sem_dado}')
    print('por fonte:', por_fonte)
    print(f'cobertura: {com_coord} de {total} ({100 * com_coord / total:.1f}%) '
          f'— era {100 * (com_coord - aplicados) / total:.1f}%')
    print('\nrode agora: enriquece.py -> gerar_app.py')


if __name__ == '__main__':
    sys.exit(main())
