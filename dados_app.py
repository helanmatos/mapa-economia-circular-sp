#!/usr/bin/env python3
"""Prepara, uma única vez, os dados que os quatro temas do app compartilham.

A ideia central: UMA fonte de pontos com todas as classificações já anotadas
(camada de tratamento, material, ciclo biológico, potência). Trocar de tema no
app vira só trocar filtro e cor — nenhum dado é recarregado, e por isso a
navegação entre temas é instantânea.
"""
import json

import duckdb

from enriquece import chave
from maturidade import apura, ELEMENTOS

T_RES = "read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true)"
T_EN = "read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true)"

# ---- Mapa 2: as 5 camadas de tratamento pedidas na reunião ----
CAMADAS = {
    'coleta': {
        'nome': 'Coleta e movimentação',
        'cor': '#1D6FB8',
        'cnaes': ('3811400', '3812200'),
        'desc': 'Coleta de resíduos não-perigosos e perigosos',
    },
    'triagem': {
        'nome': 'Triagem e recuperação',
        'cor': '#00897B',
        'cnaes': ('3831901', '3831999', '3832700', '3839499'),
        'desc': 'Recuperação de materiais para retorno à cadeia produtiva',
    },
    'organicos': {
        'nome': 'Orgânicos',
        'cor': '#7CB342',
        'cnaes': ('3839401',),
        'desc': 'Usinas de compostagem',
    },
    'tratamento': {
        'nome': 'Tratamento e disposição',
        'cor': '#E65100',
        'cnaes': ('3821100', '3822000'),
        'desc': 'Tratamento e destinação final',
    },
    'descontaminacao': {
        'nome': 'Descontaminação',
        'cor': '#8E24AA',
        'cnaes': ('3900500',),
        'desc': 'Descontaminação e gestão de resíduos perigosos',
    },
}
CNAE_PARA_CAMADA = {c: k for k, v in CAMADAS.items() for c in v['cnaes']}

# ---- sub-camada de materiais, dentro de "triagem e recuperação" ----
# A reunião pediu metal, plástico, papel, vidro, orgânico e construção civil.
# Só metal e plástico têm CNAE próprio; papel, vidro e construção civil caem
# todos no genérico 3839-4/99 e são indistinguíveis por esta fonte. Em vez de
# fingir uma separação que o dado não sustenta, o terceiro balde é explícito.
MATERIAIS = {
    'metal': {'nome': 'Metal', 'cor': '#546E7A', 'cnaes': ('3831901', '3831999')},
    'plastico': {'nome': 'Plástico', 'cor': '#D81B60', 'cnaes': ('3832700',)},
    'outros': {'nome': 'Papel, vidro, construção civil e outros',
               'cor': '#A1887F', 'cnaes': ('3839499',)},
}
CNAE_PARA_MATERIAL = {c: k for k, v in MATERIAIS.items() for c in v['cnaes']}

# ---- Mapa 3: ciclo biológico ----
CICLOS = {
    'compostagem': {'nome': 'Compostagem', 'cor': '#7CB342',
                    'desc': 'Usinas de compostagem (CNAE 3839-4/01)'},
    'biogas': {'nome': 'Biogás', 'cor': '#00897B',
               'desc': 'Aterro sanitário, resíduos urbanos e dejetos animais'},
    'biomassa': {'nome': 'Biomassa energética', 'cor': '#F9A825',
                 'desc': 'Bagaço de cana, resíduos florestais, licor negro, lenha'},
}

# Categorias circulares da ISO 59000 — item 4 do escopo formal. Estavam no mapa de
# pontos anterior e se perderam na unificação; as três ausentes ficam na legenda com
# zero de propósito, porque a ausência É o achado (não têm CNAE próprio na Receita).
CIRCULARES = {
    'Reciclagem': {'nome': 'Reciclagem', 'cor': '#2E7D32'},
    'Valorização energética': {'nome': 'Valorização energética', 'cor': '#F9A825'},
    'Tratamento/disposição': {'nome': 'Tratamento/disposição', 'cor': '#757575'},
    'Bioeconomia': {'nome': 'Bioeconomia', 'cor': '#8D6E63'},
    'Reuso': {'nome': 'Reuso', 'cor': '#BDBDBD'},
    'Remanufatura': {'nome': 'Remanufatura', 'cor': '#BDBDBD'},
    'Logística reversa': {'nome': 'Logística reversa', 'cor': '#BDBDBD'},
}
SEM_CNAE_PROPRIO = ('Reuso', 'Remanufatura', 'Logística reversa')

CNAE_DESC = {
    '3811400': 'Coleta de resíduos não-perigosos', '3812200': 'Coleta de resíduos perigosos',
    '3821100': 'Tratamento/disposição não-perigosos', '3822000': 'Tratamento/disposição perigosos',
    '3831901': 'Recuperação de sucata de alumínio', '3831999': 'Recuperação de sucata metálica',
    '3832700': 'Recuperação de materiais plásticos', '3839401': 'Usinas de compostagem',
    '3839499': 'Recuperação de materiais (outros)', '3900500': 'Descontaminação',
}


def carrega(con=None):
    con = con or duckdb.connect()
    mat = apura(con)

    # ---------- pontos: uma fonte para todos os temas ----------
    feats = []
    cols_res = ['nome_fantasia', 'cnae_principal', 'tipo_logradouro', 'logradouro', 'numero',
                'bairro', 'municipio', 'latitude', 'longitude', 'geocode_status',
                'regiao_administrativa', 'categoria_circular']
    for r in con.sql(f"SELECT {', '.join(cols_res)} FROM {T_RES} "
                     f"WHERE latitude != '' AND longitude != ''").fetchall():
        d = dict(zip(cols_res, r))
        cnae = d['cnae_principal']
        feats.append({
            'type': 'Feature',
            'geometry': {'type': 'Point',
                         'coordinates': [float(d['longitude']), float(d['latitude'])]},
            'properties': {
                'setor': 'residuos',
                'cnae': cnae,
                'circular': d['categoria_circular'] or '',
                'camada': CNAE_PARA_CAMADA.get(cnae, ''),
                'material': CNAE_PARA_MATERIAL.get(cnae, ''),
                # compostagem é o único CNAE de resíduos que entra no ciclo biológico
                'ciclo': 'compostagem' if cnae == '3839401' else '',
                'nome': d['nome_fantasia'] or '(sem nome fantasia)',
                'detalhe': CNAE_DESC.get(cnae, ''),
                'endereco': (f"{d['tipo_logradouro']} {d['logradouro']}, {d['numero']} - "
                             f"{d['bairro']}, {d['municipio']}"),
                'municipio': d['municipio'],
                'aprox': d['geocode_status'] == 'cep_aproximado',
                'ra': d['regiao_administrativa'] or '',
                'municipio_norm': chave(d['municipio']),
                'mw': 0,
            },
        })

    cols_en = ['nome', 'categoria_energia', 'combustivel_detalhe', 'municipio', 'latitude',
               'longitude', 'potencia_outorgada_kw', 'proprietario', 'regiao_administrativa',
               'categoria_circular']
    for r in con.sql(f"SELECT {', '.join(cols_en)} FROM {T_EN}").fetchall():
        d = dict(zip(cols_en, r))
        ciclo = 'biogas' if d['categoria_energia'] == 'Biogás' else 'biomassa'
        mw = round(float(d['potencia_outorgada_kw']) / 1000, 2)
        feats.append({
            'type': 'Feature',
            'geometry': {'type': 'Point',
                         'coordinates': [float(d['longitude']), float(d['latitude'])]},
            'properties': {
                'setor': 'energia',
                'cnae': '',
                'circular': d['categoria_circular'] or '',
                # usinas de energia contam como "orgânicos" na leitura de tratamento
                'camada': 'organicos',
                'material': '',
                'ciclo': ciclo,
                'nome': d['nome'],
                'detalhe': d['combustivel_detalhe'],
                'endereco': d['municipio'],
                'municipio': d['municipio'],
                'aprox': False,
                'ra': d['regiao_administrativa'] or '',
                'municipio_norm': chave(d['municipio']),
                'mw': mw,
                'proprietario': d['proprietario'] or '',
            },
        })

    # ---------- contagens que o painel exibe ----------
    conta_camada = {k: 0 for k in CAMADAS}
    conta_material = {k: 0 for k in MATERIAIS}
    conta_ciclo = {k: 0 for k in CICLOS}
    conta_circular = {k: 0 for k in CIRCULARES}
    mw_ciclo = {k: 0.0 for k in CICLOS}
    for f in feats:
        p = f['properties']
        if p['camada']:
            conta_camada[p['camada']] += 1
        if p['material']:
            conta_material[p['material']] += 1
        if p['ciclo']:
            conta_ciclo[p['ciclo']] += 1
            mw_ciclo[p['ciclo']] += p['mw']
        if p['circular'] in conta_circular:
            conta_circular[p['circular']] += 1

    return {
        'maturidade': mat,
        'pontos': {'type': 'FeatureCollection', 'features': feats},
        'conta_camada': conta_camada,
        'conta_material': conta_material,
        'conta_ciclo': conta_ciclo,
        'conta_circular': conta_circular,
        'mw_ciclo': {k: round(v, 1) for k, v in mw_ciclo.items()},
    }


if __name__ == '__main__':
    d = carrega()
    print(f"pontos: {len(d['pontos']['features'])}")
    print('camadas   :', d['conta_camada'])
    print('materiais :', d['conta_material'])
    print('ciclos    :', d['conta_ciclo'])
    print('circular  :', d['conta_circular'])
    print('MW        :', d['mw_ciclo'])
