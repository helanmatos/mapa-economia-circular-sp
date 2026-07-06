#!/usr/bin/env python3
"""
Extração de empresas (SP) por CNAE de resíduos/reciclagem — Mapa de Economia Circular (SENAC SP).

Processa os dados abertos do CNPJ da RFB localmente com DuckDB, parte por parte,
pra manter o pico de disco baixo. O arquivo de entrada já vem convertido para UTF-8
pelo orquestrador (iconv ISO-8859-1 -> UTF-8), porque o validador latin-1 do DuckDB
rejeita alguns arquivos da RFB que contêm bytes fora da faixa aceita.

Modos:
  python extrai.py parte <arquivo.utf8> <saida.parquet>   # filtra UMA parte -> parquet
  python extrai.py merge                                   # une parquets + municipios -> CSV
"""
import os
import sys
import glob
import duckdb

# CNAEs de resíduos / reciclagem (sem traço/barra, como vêm no arquivo) — Grupo 38 + 3900-5/00
CNAES = (
    '3811400', '3812200', '3821100', '3822000',
    '3831901', '3831999', '3832700',
    '3839401', '3839499', '3900500',
)

# Layout posicional do arquivo ESTABELECIMENTOS (30 colunas, sem cabeçalho)
COLS = [
    'cnpj_basico', 'cnpj_ordem', 'cnpj_dv', 'matriz_filial', 'nome_fantasia',
    'situacao_cadastral', 'data_situacao', 'motivo_situacao', 'cidade_exterior', 'pais',
    'data_inicio', 'cnae_principal', 'cnae_secundaria', 'tipo_logradouro', 'logradouro',
    'numero', 'complemento', 'bairro', 'cep', 'uf', 'municipio', 'ddd1', 'tel1', 'ddd2', 'tel2',
    'ddd_fax', 'fax', 'email', 'situacao_especial', 'data_situacao_especial',
]
SCHEMA = "{" + ", ".join(f"'{c}': 'VARCHAR'" for c in COLS) + "}"
CNAE_LIST = "(" + ", ".join(f"'{c}'" for c in CNAES) + ")"


def processa_parte(arquivo, saida):
    # Escreve em .tmp e só renomeia no sucesso -> nunca sobra parquet de 0 byte se falhar.
    tmp = saida + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    sql = f"""
    COPY (
        SELECT cnpj_basico, cnpj_ordem, cnpj_dv, nome_fantasia, cnae_principal,
               tipo_logradouro, logradouro, numero, complemento, bairro, cep,
               uf, municipio AS cod_municipio, ddd1, tel1, email
        FROM read_csv('{arquivo}',
                      delim=';', header=false, quote='"',
                      encoding='utf-8', columns={SCHEMA}, ignore_errors=true)
        WHERE uf = 'SP'
          AND situacao_cadastral = '02'          -- 02 = Ativa
          AND cnae_principal IN {CNAE_LIST}
    ) TO '{tmp}' (FORMAT parquet)
    """
    duckdb.sql(sql)
    os.replace(tmp, saida)
    n = duckdb.sql(f"SELECT count(*) FROM read_parquet('{saida}')").fetchone()[0]
    print(f"  {arquivo} -> {saida}: {n} empresas")
    return n


def merge():
    munic = glob.glob('dados_rf/*MUNICCSV')
    if not munic:
        sys.exit("ERRO: arquivo de municípios (*MUNICCSV) não encontrado em dados_rf/")
    municipios = munic[0]

    # Só parquets válidos (ignora qualquer 0 byte remanescente).
    parts = sorted(p for p in glob.glob('saida_partes/parte_*.parquet') if os.path.getsize(p) > 100)
    if not parts:
        sys.exit("ERRO: nenhum parquet válido em saida_partes/")
    plist = "[" + ", ".join(f"'{p}'" for p in parts) + "]"
    print(f"merge de {len(parts)} partes: {', '.join(os.path.basename(p) for p in parts)}")

    sql = f"""
    COPY (
        SELECT e.cnpj_basico, e.cnpj_ordem, e.cnpj_dv,
               e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj,
               e.nome_fantasia, e.cnae_principal,
               e.tipo_logradouro, e.logradouro, e.numero, e.complemento, e.bairro, e.cep,
               e.uf, m.nome AS municipio, e.ddd1, e.tel1, e.email
        FROM read_parquet({plist}) e
        LEFT JOIN read_csv('{municipios}',
                      delim=';', header=false, quote='"', encoding='latin-1',
                      columns={{'codigo':'VARCHAR','nome':'VARCHAR'}}, ignore_errors=true) m
               ON e.cod_municipio = m.codigo
        ORDER BY m.nome, e.cnae_principal
    ) TO 'empresas_sp_circular.csv' (HEADER, DELIMITER ',')
    """
    duckdb.sql(sql)
    n = duckdb.sql("SELECT count(*) FROM read_csv('empresas_sp_circular.csv', header=true)").fetchone()[0]
    print(f"{n} empresas -> empresas_sp_circular.csv")


if __name__ == '__main__':
    if len(sys.argv) >= 4 and sys.argv[1] == 'parte':
        processa_parte(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 2 and sys.argv[1] == 'merge':
        merge()
    else:
        sys.exit(__doc__)
