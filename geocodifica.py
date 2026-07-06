#!/usr/bin/env python3
"""
Geocodificação dos endereços de empresas_sp_circular.csv via Nominatim (OpenStreetMap).

Respeita a politica de uso do Nominatim: max 1 req/s, User-Agent identificando a
aplicacao. Deduplicamos por endereço unico (cep+logradouro+numero+bairro+municipio)
para nao repetir consultas.

Resumivel: grava cada resultado em geo_cache.jsonl (append-only) assim que chega;
se o processo cair/for interrompido, re-executar retoma do que falta (skip por chave
ja presente no cache).

Estrategia por endereco (3 tentativas, so avanca se a anterior falhar):
  1) query estruturada (street=tipo+logradouro+numero, city, state, postalcode, country)
  2) query livre (q= endereco formatado como string)
  3) fallback por CEP apenas (aproximado - cai no centro da area do CEP)

Uso:
  python geocodifica.py coletar   # roda a coleta (resumivel)
  python geocodifica.py juntar    # junta geo_cache.jsonl ao CSV -> gera CSV com lat/lon
"""
import sys
import csv
import json
import time
import os
import requests

CSV_IN = 'empresas_sp_circular.csv'
CACHE = 'geo_cache.jsonl'
CSV_OUT = 'empresas_sp_circular_geo.csv'

NOMINATIM = 'https://nominatim.openstreetmap.org/search'
HEADERS = {'User-Agent': 'MapaEconomiaCircularSENAC/1.0 (contato: matos.helan@gmail.com)'}
RATE_SLEEP = 1.1  # > 1 req/s exigido pela politica do Nominatim


def chave(row):
    return '|'.join([row['cep'], row['logradouro'], row['numero'], row['bairro'], row['municipio']])


def carrega_enderecos_unicos():
    vistos = {}
    with open(CSV_IN, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            k = chave(row)
            if k not in vistos:
                vistos[k] = row
    return vistos


def carrega_cache():
    feitos = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    feitos[d['key']] = d
                except json.JSONDecodeError:
                    continue
    return feitos


def consulta(params):
    try:
        r = requests.get(NOMINATIM, params=params, headers=HEADERS, timeout=15)
        time.sleep(RATE_SLEEP)
        if r.status_code != 200:
            return None
        data = r.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        time.sleep(RATE_SLEEP)
    return None


def geocodifica_endereco(row):
    rua = f"{row['tipo_logradouro']} {row['logradouro']} {row['numero']}".strip()

    # tentativa 1: estruturada
    # OBS: 'state' junto de 'postalcode' faz o Nominatim falhar em varios casos
    # (parametros sobre-restringem a busca) -> o CEP ja ancora a regiao (SP).
    r = consulta({
        'format': 'jsonv2', 'limit': 1, 'country': 'Brazil',
        'city': row['municipio'], 'street': rua, 'postalcode': row['cep'],
    })
    if r:
        return r[0], r[1], 'endereco_estruturado'

    # tentativa 2: texto livre
    texto = f"{rua}, {row['bairro']}, {row['municipio']}, SP, Brasil"
    r = consulta({'format': 'jsonv2', 'limit': 1, 'q': texto})
    if r:
        return r[0], r[1], 'endereco_livre'

    # tentativa 3: so o CEP (aproximado)
    if row['cep']:
        r = consulta({'format': 'jsonv2', 'limit': 1, 'country': 'Brazil',
                       'postalcode': row['cep']})
        if r:
            return r[0], r[1], 'cep_aproximado'

    return None, None, 'falhou'


def coletar():
    enderecos = carrega_enderecos_unicos()
    feitos = carrega_cache()
    pendentes = [k for k in enderecos if k not in feitos]
    total = len(enderecos)
    print(f"[{time.strftime('%H:%M:%S')}] {total} enderecos unicos | "
          f"{len(feitos)} ja no cache | {len(pendentes)} pendentes")

    with open(CACHE, 'a', encoding='utf-8') as cache_f:
        for i, k in enumerate(pendentes, 1):
            row = enderecos[k]
            lat, lon, status = geocodifica_endereco(row)
            rec = {'key': k, 'lat': lat, 'lon': lon, 'status': status}
            cache_f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            cache_f.flush()
            if i % 50 == 0 or i == len(pendentes):
                print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(pendentes)} "
                      f"processados nesta execucao (total no cache: {len(feitos)+i})")

    print(f"[{time.strftime('%H:%M:%S')}] COLETA CONCLUIDA")


# Bounding box generoso do estado de SP - resultados fora disso sao geocodes
# claramente errados (Nominatim as vezes casa CEP/nome ambiguo com outro estado).
SP_LAT_MIN, SP_LAT_MAX = -25.4, -19.5
SP_LON_MIN, SP_LON_MAX = -53.5, -44.0


def dentro_de_sp(lat, lon):
    return SP_LAT_MIN <= lat <= SP_LAT_MAX and SP_LON_MIN <= lon <= SP_LON_MAX


def juntar():
    cache = carrega_cache()
    n_ok = sum(1 for d in cache.values() if d['lat'] is not None)
    print(f"cache: {len(cache)} enderecos, {n_ok} com coordenadas")

    n_fora = 0
    with open(CSV_IN, encoding='utf-8') as fin, open(CSV_OUT, 'w', newline='', encoding='utf-8') as fout:
        reader = csv.DictReader(fin)
        campos = reader.fieldnames + ['latitude', 'longitude', 'geocode_status']
        writer = csv.DictWriter(fout, fieldnames=campos)
        writer.writeheader()
        n = 0
        for row in reader:
            k = chave(row)
            d = cache.get(k, {})
            lat, lon, status = d.get('lat'), d.get('lon'), d.get('status', 'nao_processado')
            if lat is not None and lon is not None and not dentro_de_sp(lat, lon):
                lat, lon, status = None, None, 'fora_dos_limites_sp'
                n_fora += 1
            row['latitude'] = lat if lat is not None else ''
            row['longitude'] = lon if lon is not None else ''
            row['geocode_status'] = status
            writer.writerow(row)
            n += 1
    print(f"{n} linhas -> {CSV_OUT} ({n_fora} descartadas por cair fora do estado de SP)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == 'coletar':
        coletar()
    elif sys.argv[1] == 'juntar':
        juntar()
    else:
        sys.exit(__doc__)
