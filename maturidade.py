#!/usr/bin/env python3
"""Índice de maturidade circular — fonte única de verdade.

Tanto o mapa (gerar_mapa_hub_circular.py) quanto o documento técnico
(gerar_documento_completo.py) importam daqui. Antes a lógica estava duplicada,
e foi exatamente assim que o join de município divergiu entre os artefatos:
a agregação da energia usava upper() (preserva acento) e a consulta usava
normaliza() (remove acento), derrubando em silêncio 105 das 239 usinas.

Definições:
  nível do MUNICÍPIO  = quantos dos 4 serviços existem nele (0 a 4)
  classe da REGIÃO    = média dos municípios, arredondada, com trava de lacuna
"""
import json

import duckdb

from enriquece import chave

GEOJSON_MUN = 'geo_cache/municipios_sp_malha_com_ra.json'

ELEMENTOS = {
    'coleta': ('3811400', '3812200'),
    'reciclagem': ('3831901', '3831999', '3832700', '3839499'),
    'tratamento_disposicao': ('3821100', '3822000', '3900500'),
    'organicos_cnpj': ('3839401',),
}

# paleta das classes 0..4 — escolhida para sobreviver a impressão em preto-e-branco
# (luminância crescente) e a deuteranopia (o par laranja/verde-claro não colide)
PALETA = ['#B00020', '#E65100', '#F5C518', '#8BC34A', '#1B5E20']
# Rótulos do MUNICÍPIO: aqui a escala é literalmente "quantos dos 4 serviços existem".
NIVEL_INFO = {
    4: ('Circular completo (4 de 4 serviços)', PALETA[4]),
    3: ('Quase completo (3 de 4 serviços)', PALETA[3]),
    2: ('Intermediário (2 de 4 serviços)', PALETA[2]),
    1: ('Básico (1 de 4 serviços)', PALETA[1]),
    0: ('Sem infraestrutura mapeada', PALETA[0]),
}

# Rótulos da REGIÃO: a classe da RA é a MÉDIA dos seus municípios, não a contagem de
# serviços da região. Usar o texto do município aqui produzia afirmação falsa nas 16
# RAs — a 9ª Araçatuba tem os 4 serviços presentes e aparecia como "Básico (1 de 4
# serviços)", contradizendo a própria tabela do popup logo abaixo. Os limites citados
# são exatamente os cortes de arredondamento usados em pinta().
CLASSE_INFO = {
    4: ('Circular — média acima de 3,5 serviços por município', PALETA[4]),
    3: ('Avançada — média entre 2,5 e 3,5 por município', PALETA[3]),
    2: ('Intermediária — média entre 1,5 e 2,5 por município', PALETA[2]),
    1: ('Básica — média abaixo de 1,5 por município', PALETA[1]),
    0: ('Sem infraestrutura mapeada', PALETA[0]),
}

T_RES = "read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true)"
T_EN = "read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true)"


# Escada COMPOSICIONAL pedida na reunião de 07/09/2026. A especialista descreveu os
# estágios pelo que a região TEM, não por quantos itens tem: "é básico, ela só tem
# coleta e reciclagem, ou é um nível mais estruturado, coleta reciclagem e tratamento,
# ou é um nível circular mesmo, onde a gente tem todos os elementos".
#
# Isso é diferente da contagem 0-4: um município com coleta + orgânicos tem 2 serviços
# mas NÃO é "básico" no sentido dela, porque não fecha coleta+reciclagem. As duas
# leituras convivem no mapa — a contagem dá a granularidade, o estágio dá o nome.
ESTAGIOS = ['sem', 'incipiente', 'basico', 'estruturado', 'circular']
ESTAGIO_INFO = {
    'circular':    ('Circular', 'coleta, reciclagem, tratamento e orgânicos', PALETA[4]),
    'estruturado': ('Estruturado', 'coleta, reciclagem e tratamento', PALETA[3]),
    'basico':      ('Básico', 'coleta e reciclagem', PALETA[2]),
    'incipiente':  ('Incipiente', 'tem algum serviço, mas não fecha coleta + reciclagem', PALETA[1]),
    'sem':         ('Sem infraestrutura', 'nenhum dos 4 serviços', PALETA[0]),
}


def estagio(coleta, reciclagem, tratamento, organicos):
    """Estágio composicional, na escada nomeada da reunião.

    A ordem importa: circular exige os 4; estruturado exige a base + tratamento;
    básico exige exatamente a base. Qualquer outra combinação com pelo menos um
    serviço é 'incipiente' — é o balde honesto para quem tem orgânicos sem ter
    reciclagem, por exemplo, caso que a escada original não previa.
    """
    base = coleta > 0 and reciclagem > 0
    if base and tratamento > 0 and organicos > 0:
        return 'circular'
    if base and tratamento > 0:
        return 'estruturado'
    if base:
        return 'basico'
    if coleta > 0 or reciclagem > 0 or tratamento > 0 or organicos > 0:
        return 'incipiente'
    return 'sem'


def calcula_nivel(coleta, reciclagem, tratamento, organicos):
    return sum([coleta > 0, reciclagem > 0, tratamento > 0, organicos > 0])


def elementos_faltando(coleta, reciclagem, tratamento, organicos):
    faltando = []
    if coleta == 0:
        faltando.append('Coleta')
    if reciclagem == 0:
        faltando.append('Reciclagem')
    if tratamento == 0:
        faltando.append('Tratamento/Disposição')
    if organicos == 0:
        faltando.append('Orgânicos')
    return ', '.join(faltando) if faltando else 'nenhum elemento'


def pinta(niveis, ra=False):
    """Cor de uma unidade (RA ou município) a partir dos níveis dos municípios dela.

    `ra=True` escolhe os rótulos de região (que falam em média) em vez dos rótulos de
    município (que falam em contagem de serviços). A escala numérica é a mesma; o que
    ela SIGNIFICA não é, e trocar os textos gera afirmação falsa.

    A MESMA função pinta os dois casos: um município é o caso N=1.

    A classe é a média municipal arredondada (cortes em 0,5 / 1,5 / 2,5 / 3,5) e sofre
    uma TRAVA DE LACUNA: quanto maior a fatia de municípios sem nenhum registro, mais
    baixo o teto da classe. A trava só rebaixa, nunca promove.

    É a média — não a trava — que corrige o problema original: antes a RA era pintada
    pela presença do serviço "em algum lugar da região", e a 8ª São José do Rio Preto
    aparecia verde-escuro com 38,5% dos seus municípios zerados, acima da 2ª Santos,
    que não tem nenhum município zerado. Com os dados atuais a trava não chega a ser
    acionada em nenhuma das 16 RAs: ela é salvaguarda para uma região de média alta
    concentrada em poucos municípios, situação que hoje não ocorre.
    """
    n = len(niveis)
    media = sum(niveis) / n
    pct_vazio = sum(1 for v in niveis if v == 0) / n
    classe_base = min(4, max(0, int(media + 0.5)))
    teto = 4 if pct_vazio < 0.15 else 2 if pct_vazio < 0.30 else 1 if pct_vazio < 0.50 else 0
    classe = min(classe_base, teto)
    listras = 'liso' if pct_vazio < 0.15 else 'leve' if pct_vazio < 0.30 else 'forte'
    return {
        'classe': classe,
        'classe_desc': (CLASSE_INFO if ra else NIVEL_INFO)[classe][0],
        'media': round(media, 2),
        'pct_vazio': round(pct_vazio * 100, 1),
        'n_mun': n,
        'n_vazios': sum(1 for v in niveis if v == 0),
        'dist': [sum(1 for v in niveis if v == k) for k in range(5)],
        'listras': listras,
        'travada': classe < classe_base,
    }


def apura(con=None):
    """Apura o índice para os 645 municípios e as 16 RAs.

    Devolve um dicionário com o geojson de municípios já anotado, os níveis por RA,
    e os agregados que o documento técnico cita.
    """
    con = con or duckdb.connect()

    # O índice é POR MUNICÍPIO, e o município está preenchido em 100% dos registros —
    # inclusive nos 1.790 sem coordenada. Filtrar por latitude aqui descartava empresas
    # cujo município é perfeitamente conhecido, criando 26 municípios "sem infraestrutura"
    # que na verdade tinham empresas, e inflando os desertos justamente no interior, onde
    # a geocodificação falha mais. A coordenada só é necessária para desenhar o pin.
    linhas = con.sql(f"""
        SELECT municipio,
          sum(CASE WHEN cnae_principal IN {ELEMENTOS['coleta']} THEN 1 ELSE 0 END) coleta,
          sum(CASE WHEN cnae_principal IN {ELEMENTOS['reciclagem']} THEN 1 ELSE 0 END) reciclagem,
          sum(CASE WHEN cnae_principal IN {ELEMENTOS['tratamento_disposicao']} THEN 1 ELSE 0 END) tratamento,
          sum(CASE WHEN cnae_principal IN {ELEMENTOS['organicos_cnpj']} THEN 1 ELSE 0 END) organicos_compost,
          count(*) total_residuos
        FROM {T_RES} GROUP BY 1
    """).fetchall()
    campos = ['coleta', 'reciclagem', 'tratamento', 'organicos_compost', 'total_residuos']
    dados_mun = {chave(r[0]): dict(zip(campos, r[1:])) for r in linhas}

    # empresas que entram no índice mas NÃO aparecem como ponto no mapa, por falta de
    # coordenada. Depois da correção acima elas já contam para a maturidade do município;
    # o que se perde é só a localização exata dentro dele.
    sem_coord = {}
    # o CSV traz latitude vazia, que o DuckDB lê como NULL — não como string vazia
    for mun, n in con.sql(f"SELECT municipio, count(*) FROM {T_RES} "
                          f"WHERE latitude IS NULL GROUP BY 1").fetchall():
        k = chave(mun)
        sem_coord[k] = sem_coord.get(k, 0) + n

    energia_por_mun = {}
    for mun, n in con.sql(f"SELECT municipio, count(*) FROM {T_EN} GROUP BY 1").fetchall():
        k = chave(mun)
        energia_por_mun[k] = energia_por_mun.get(k, 0) + n

    geojson_mun = json.load(open(GEOJSON_MUN, encoding='utf-8'))
    niveis_por_ra = {}
    vazio = {'coleta': 0, 'reciclagem': 0, 'tratamento': 0, 'organicos_compost': 0, 'total_residuos': 0}
    for feat in geojson_mun['features']:
        k = chave(feat['properties']['nome'])
        d = dados_mun.get(k, vazio)
        n_energia = energia_por_mun.get(k, 0)
        organicos = d['organicos_compost'] + n_energia
        nivel = calcula_nivel(d['coleta'], d['reciclagem'], d['tratamento'], organicos)
        nao_geo = sem_coord.get(k, 0)
        total_emp = (d['coleta'] + d['reciclagem'] + d['tratamento']
                     + d['organicos_compost'])
        feat['properties'].update({
            'nivel': nivel,
            'nao_geocodificadas': nao_geo,
            # município que tem empresa mas NENHUMA aparece como ponto: o índice está
            # certo, mas ao abrir o município o mapa fica sem pin nenhum
            'sem_pin': nao_geo > 0 and nao_geo >= total_emp,
            'coleta': d['coleta'], 'reciclagem': d['reciclagem'], 'tratamento': d['tratamento'],
            'organicos': organicos, 'total_iniciativas': d['total_residuos'] + n_energia,
            'faltando': elementos_faltando(d['coleta'], d['reciclagem'], d['tratamento'], organicos),
            'municipio_norm': k,
            'estagio': estagio(d['coleta'], d['reciclagem'], d['tratamento'], organicos),
            **pinta([nivel]),  # município = caso N=1 da mesma regra de cor da RA
        })
        niveis_por_ra.setdefault(feat['properties']['regiao_administrativa'], []).append(nivel)

    nomes_malha = {chave(f['properties']['nome']) for f in geojson_mun['features']}
    usinas_total = sum(energia_por_mun.values())
    usinas_casadas = sum(n for k, n in energia_por_mun.items() if k in nomes_malha)

    classes_ra = {nome: pinta(ns, ra=True) for nome, ns in niveis_por_ra.items()}

    # taxa de falha de geocodificação por RA — a medida do viés
    falha_ra = {}
    for ra_nome, tot, fal in con.sql(f"""
        SELECT regiao_administrativa, count(*),
               sum(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END)
        FROM {T_RES} WHERE regiao_administrativa != '' GROUP BY 1""").fetchall():
        falha_ra[ra_nome] = {'total': tot, 'sem_coord': int(fal),
                             'pct': round(100 * fal / tot, 1) if tot else 0.0}
    sem_pin = [f['properties']['nome'] for f in geojson_mun['features']
               if f['properties']['sem_pin']]
    dist = [sum(1 for f in geojson_mun['features'] if f['properties']['nivel'] == k) for k in range(5)]
    total_mun = len(geojson_mun['features'])

    dist_estagio = {e: sum(1 for f in geojson_mun['features'] if f['properties']['estagio'] == e)
                    for e in ESTAGIOS}
    estagios_por_ra = {}
    for f in geojson_mun['features']:
        ra_nome = f['properties']['regiao_administrativa']
        estagios_por_ra.setdefault(ra_nome, []).append(f['properties']['estagio'])

    return {
        'falha_geocodificacao_ra': falha_ra,
        'municipios_sem_pin': sem_pin,
        'total_sem_coord': sum(sem_coord.values()),
        'dist_estagio': dist_estagio,
        'estagios_por_ra': estagios_por_ra,
        'geojson_mun': geojson_mun,
        'niveis_por_ra': niveis_por_ra,
        'classes_ra': classes_ra,
        'dist_municipal': dist,
        'total_municipios': total_mun,
        'media_estadual': sum(i * c for i, c in enumerate(dist)) / total_mun,
        'usinas_total': usinas_total,
        'usinas_casadas': usinas_casadas,
        'ras_travadas': [ra for ra, c in classes_ra.items() if c['travada']],
        'dados_mun': dados_mun,
        'energia_por_mun': energia_por_mun,
    }


if __name__ == '__main__':
    a = apura()
    print('distribuição municipal 0..4:', a['dist_municipal'], '| total', a['total_municipios'])
    print(f"média estadual: {a['media_estadual']:.3f}")
    print(f"usinas casadas: {a['usinas_casadas']} de {a['usinas_total']}")
    print('RAs rebaixadas pela trava:', a['ras_travadas'] or 'nenhuma')
    for ra, c in sorted(a['classes_ra'].items(), key=lambda x: -x[1]['media']):
        print(f"  {ra:26} classe {c['classe']}  média {c['media']:.2f}  "
              f"vazios {c['pct_vazio']:>5.1f}%  {c['listras']}")
