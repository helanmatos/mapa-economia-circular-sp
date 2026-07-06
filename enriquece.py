#!/usr/bin/env python3
"""
Enriquecimento das bases de iniciativas de economia circular (SP):
  - Região Administrativa (RA) por município (item 2/8 do escopo formal)
  - Categoria circular ISO 59000 (item 4 do escopo formal)

Gera:
  - empresas_sp_circular_enriquecido.csv  (residuos + RA + categoria_circular)
  - energia_biomassa_biogas_enriquecido.csv (energia + RA + categoria_circular)
  - kpis_regiao_administrativa.csv (contagem de iniciativas por RA - item 11)
  - kpis_categoria_circular.csv (contagem por categoria circular - item 11)
"""
import csv
import unicodedata


def normaliza(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return s.upper().strip()


# Correcoes manuais para nomes que nao normalizam identico entre as fontes:
# hifen nao e removido pela normalizacao; "Luis"/"Luiz" e grafia alternativa oficial;
# "Ipaucu"/"Ipaussu" e variante de grafia; acento suspenso (´) em vez de apostrofo
# reto (') na fonte ANEEL faz o "d´Oeste" normalizar sem apostrofo nenhum.
ALIASES = {
    'BIRITIBA-MIRIM': 'BIRITIBA MIRIM',
    'LUIS ANTONIO': 'LUIZ ANTONIO',
    "SAO JOAO DO PAU D'ALHO": "SAO JOAO DO PAU-D'ALHO",
    'IPAUCU': 'IPAUSSU',
    'SANTA BARBARA DOESTE': "SANTA BARBARA D'OESTE",
}

# Categoria circular ISO 59000 (item 4 do escopo). CNAEs de tratamento/disposicao
# final e descontaminacao ficam fora das 6 categorias "circulares" propriamente
# ditas -> bucket honesto "Tratamento/disposição" (gestao linear, nao circular).
CATEGORIA_CNAE = {
    '3811400': 'Reciclagem',            # coleta de residuos nao-perigosos (alimenta reciclagem)
    '3812200': 'Tratamento/disposição',  # coleta de residuos perigosos
    '3821100': 'Tratamento/disposição',  # tratamento/disposicao nao-perigosos
    '3822000': 'Tratamento/disposição',  # tratamento/disposicao perigosos
    '3831901': 'Reciclagem',            # recuperacao sucata aluminio
    '3831999': 'Reciclagem',            # recuperacao sucata metalica
    '3832700': 'Reciclagem',            # recuperacao plasticos
    '3839401': 'Bioeconomia',           # usinas de compostagem
    '3839499': 'Reciclagem',            # recuperacao de materiais (outros)
    '3900500': 'Tratamento/disposição',  # descontaminacao
}
CATEGORIA_ENERGIA = {
    'biomassa': 'Valorização energética',
    'biogas': 'Valorização energética',
}


def carrega_ra():
    ra = {}
    with open('municipios_regiao_administrativa.csv', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            ra[row['municipio_norm']] = row['regiao_administrativa']
    return ra


def busca_ra(municipio, ra_map):
    chave = normaliza(municipio)
    chave = ALIASES.get(chave, chave)
    return ra_map.get(chave, '')


def enriquece_residuos(ra_map):
    entrada = 'empresas_sp_circular_geo.csv'
    saida = 'empresas_sp_circular_enriquecido.csv'
    sem_ra = 0
    with open(entrada, encoding='utf-8') as fin, open(saida, 'w', newline='', encoding='utf-8') as fout:
        reader = csv.DictReader(fin)
        campos = reader.fieldnames + ['regiao_administrativa', 'categoria_circular']
        writer = csv.DictWriter(fout, fieldnames=campos)
        writer.writeheader()
        n = 0
        for row in reader:
            ra = busca_ra(row['municipio'], ra_map)
            if not ra:
                sem_ra += 1
            row['regiao_administrativa'] = ra
            row['categoria_circular'] = CATEGORIA_CNAE.get(row['cnae_principal'], '')
            writer.writerow(row)
            n += 1
    print(f"residuos: {n} linhas ({sem_ra} sem RA) -> {saida}")


def enriquece_energia(ra_map):
    entrada = 'energia_biomassa_biogas_sp.csv'
    saida = 'energia_biomassa_biogas_enriquecido.csv'
    sem_ra = 0
    with open(entrada, encoding='utf-8') as fin, open(saida, 'w', newline='', encoding='utf-8') as fout:
        reader = csv.DictReader(fin)
        campos = reader.fieldnames + ['regiao_administrativa', 'categoria_circular']
        writer = csv.DictWriter(fout, fieldnames=campos)
        writer.writeheader()
        n = 0
        for row in reader:
            ra = busca_ra(row['municipio'], ra_map)
            if not ra:
                sem_ra += 1
            cat_energia = 'biogas' if row['categoria_energia'] == 'Biogás' else 'biomassa'
            row['regiao_administrativa'] = ra
            row['categoria_circular'] = CATEGORIA_ENERGIA.get(cat_energia, '')
            writer.writerow(row)
            n += 1
    print(f"energia: {n} linhas ({sem_ra} sem RA) -> {saida}")


def kpis():
    import duckdb
    con = duckdb.connect()
    sql_uniao = """
    SELECT regiao_administrativa, categoria_circular FROM read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true)
    WHERE latitude IS NOT NULL AND latitude != ''
    UNION ALL
    SELECT regiao_administrativa, categoria_circular FROM read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true)
    """
    con.sql(f"""
        COPY (SELECT regiao_administrativa, count(*) n_iniciativas
              FROM ({sql_uniao}) WHERE regiao_administrativa != ''
              GROUP BY 1 ORDER BY 2 DESC)
        TO 'kpis_regiao_administrativa.csv' (HEADER)
    """)
    con.sql(f"""
        COPY (SELECT categoria_circular, count(*) n_iniciativas
              FROM ({sql_uniao}) WHERE categoria_circular != ''
              GROUP BY 1 ORDER BY 2 DESC)
        TO 'kpis_categoria_circular.csv' (HEADER)
    """)
    print("\n=== KPI: iniciativas por Região Administrativa ===")
    con.sql("SELECT * FROM read_csv('kpis_regiao_administrativa.csv', header=true)").show(max_rows=20)
    print("=== KPI: iniciativas por categoria circular ===")
    con.sql("SELECT * FROM read_csv('kpis_categoria_circular.csv', header=true)").show()


if __name__ == '__main__':
    ra_map = carrega_ra()
    enriquece_residuos(ra_map)
    enriquece_energia(ra_map)
    kpis()
