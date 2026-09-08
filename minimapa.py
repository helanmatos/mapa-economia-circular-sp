#!/usr/bin/env python3
"""Minimapa de localização — sempre um nível geográfico ACIMA do que está na tela.

  vendo o estado    -> minimapa mostra o país, com SP destacado
  vendo uma região  -> minimapa mostra o estado, com a RA destacada
  vendo um município-> minimapa mostra a RA, com o município destacado

São paths SVG pré-calculados, não um segundo mapa MapLibre: abrir outro contexto
WebGL só para desenhar um contorno e um retângulo não se justifica. Cada nível tem
projeção própria (equiretangular no paralelo médio do seu recorte), e o JS usa a
projeção do nível ativo para posicionar o retângulo do viewport.
"""
import json
import math

from shapely.geometry import shape
from shapely.ops import unary_union

LARGURA, ALTURA = 132, 116
MARGEM = 5

# tolerâncias de simplificação, em graus. O minimapa tem ~130px de largura, então
# detalhe fino é invisível e só pesaria o arquivo.
TOL_PAIS = 0.12
TOL_ESTADO = 0.02
TOL_RA = 0.006


def _projecao(bounds):
    lon0, lat0, lon1, lat1 = bounds
    klon = math.cos(math.radians((lat0 + lat1) / 2))
    larg = max((lon1 - lon0) * klon, 1e-9)
    alt = max(lat1 - lat0, 1e-9)
    esc = min((LARGURA - 2 * MARGEM) / larg, (ALTURA - 2 * MARGEM) / alt)
    return {
        'lon0': round(lon0, 6), 'lat1': round(lat1, 6),
        'klon': round(klon, 6), 'esc': round(esc, 6),
        'dx': round((LARGURA - larg * esc) / 2, 3),
        'dy': round((ALTURA - alt * esc) / 2, 3),
    }


def _path(geom, proj, tol):
    """Converte uma geometria shapely em path SVG, já simplificada e projetada."""
    g = geom.simplify(tol, preserve_topology=True)
    if g.is_empty:
        return ''
    partes = g.geoms if g.geom_type.startswith('Multi') else [g]
    saida = []
    for parte in partes:
        if parte.is_empty or not hasattr(parte, 'exterior'):
            continue
        pts = [(round((x - proj['lon0']) * proj['klon'] * proj['esc'] + proj['dx'], 1),
                round((proj['lat1'] - y) * proj['esc'] + proj['dy'], 1))
               for x, y in parte.exterior.coords]
        if len(pts) < 3:
            continue
        saida.append('M' + 'L'.join(f'{x} {y}' for x, y in pts) + 'Z')
    return ''.join(saida)


def constroi(geojson_ra, geojson_mun, brasil_path='geo_cache/brasil_ufs.json', uf='35'):
    brasil = json.load(open(brasil_path, encoding='utf-8'))
    ufs = {f['properties']['codarea']: shape(f['geometry']) for f in brasil['features']}

    # ---------- nível PAÍS (mostrado quando se está vendo o estado) ----------
    todas = unary_union(list(ufs.values()))
    proj_pais = _projecao(todas.bounds)
    mini = {
        'pais': {
            'fundo': _path(todas, proj_pais, TOL_PAIS),
            'destaque': _path(ufs[uf], proj_pais, TOL_PAIS),
            'proj': proj_pais,
            'rotulo': 'Brasil',
        }
    }

    # ---------- nível ESTADO (mostrado quando se está vendo uma RA) ----------
    ras = {f['properties']['regiao_administrativa']: shape(f['geometry'])
           for f in geojson_ra['features']}
    estado = unary_union(list(ras.values()))
    proj_estado = _projecao(estado.bounds)
    mini['estado'] = {
        'fundo': _path(estado, proj_estado, TOL_ESTADO),
        'destaques': {nome: _path(g, proj_estado, TOL_ESTADO) for nome, g in ras.items()},
        'proj': proj_estado,
        'rotulo': 'São Paulo',
    }

    # ---------- nível RA (mostrado quando se está vendo um município) ----------
    por_ra = {}
    for f in geojson_mun['features']:
        por_ra.setdefault(f['properties']['regiao_administrativa'], []).append(f)

    mini['ra'] = {}
    for nome, feats in por_ra.items():
        geom_ra = ras.get(nome) or unary_union([shape(f['geometry']) for f in feats])
        proj = _projecao(geom_ra.bounds)
        mini['ra'][nome] = {
            'fundo': _path(geom_ra, proj, TOL_RA),
            'destaques': {f['properties']['municipio_norm']:
                          _path(shape(f['geometry']), proj, TOL_RA) for f in feats},
            'proj': proj,
            'rotulo': nome,
        }
    return mini


if __name__ == '__main__':
    ra = json.load(open('geo_cache/regioes_administrativas.geojson', encoding='utf-8'))
    mun = json.load(open('geo_cache/municipios_sp_malha_com_ra.json', encoding='utf-8'))
    for f in mun['features']:
        f['properties'].setdefault('municipio_norm', f['properties']['nome'])
    m = constroi(ra, mun)
    bruto = json.dumps(m, ensure_ascii=False)
    print(f"país  : fundo {len(m['pais']['fundo'])} chars | destaque {len(m['pais']['destaque'])}")
    print(f"estado: fundo {len(m['estado']['fundo'])} | {len(m['estado']['destaques'])} RAs")
    print(f"RAs   : {len(m['ra'])} recortes | "
          f"{sum(len(v['destaques']) for v in m['ra'].values())} municípios")
    print(f"total serializado: {len(bruto)/1024:.0f} KB")
