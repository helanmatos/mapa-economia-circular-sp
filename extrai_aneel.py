#!/usr/bin/env python3
"""
Extração de usinas de energia por biogás/biomassa em SP — ANEEL SIGA (Sistema de
Informações de Geração). Setor "Energia" do escopo formal do Mapa de Economia Circular.

Fonte: https://dadosabertos.aneel.gov.br/dataset/siga-sistema-de-informacoes-de-geracao-da-aneel
Diferente do CNPJ de resíduos, este dataset já vem com coordenadas exatas
(NumCoordNEmpreendimento/NumCoordEEmpreendimento) — não precisa geocodificar.
"""
import os
import subprocess
import duckdb

URL = ('https://dadosabertos.aneel.gov.br/dataset/6d90b77c-c5f5-4d81-bdec-7bc619494bb9/'
       'resource/11ec447d-698d-4ab8-977f-b424d5deee6a/download/siga-empreendimentos-geracao.csv')
SAIDA = 'energia_biomassa_biogas_sp.csv'
BRUTO = 'dados_rf/siga-empreendimentos-geracao.csv'
BRUTO_UTF8 = 'dados_rf/siga-empreendimentos-geracao.utf8.csv'

# Mesmo problema de encoding do CNPJ: o validador latin-1 estrito do DuckDB rejeita
# o arquivo -> baixa local e converte ISO-8859-1 -> UTF-8 byte-safe via iconv.
if not os.path.exists(BRUTO_UTF8):
    subprocess.run(['curl', '-sL', '--retry', '5', URL, '-o', BRUTO], check=True)
    env_c = {**os.environ, 'LC_ALL': 'C', 'LANG': 'C'}
    with open(BRUTO_UTF8, 'wb') as out:
        p1 = subprocess.Popen(['tr', '-d', '\\000'], stdin=open(BRUTO, 'rb'), stdout=subprocess.PIPE, env=env_c)
        subprocess.run(['iconv', '-f', 'ISO-8859-1', '-t', 'UTF-8'], stdin=p1.stdout, stdout=out, check=True)
        p1.wait()
    if p1.returncode != 0:
        raise RuntimeError(f"tr falhou com codigo {p1.returncode}")
    os.remove(BRUTO)

# Sub-fontes dentro de "Biomassa" (DscOrigemCombustivel) que mapeiam para biogás
# (aterro/dejetos) vs biomassa propriamente dita (bagaço de cana, floresta etc.)
BIOGAS_FONTES = ('Resíduos sólidos urbanos', 'Resíduos animais')

con = duckdb.connect()
sql = f"""
COPY (
    SELECT
        "NomEmpreendimento" AS nome,
        "CodCEG" AS codigo_ceg,
        "SigTipoGeracao" AS tipo_geracao,
        "DscFaseUsina" AS fase,
        "DscOrigemCombustivel" AS origem_combustivel,
        "DscFonteCombustivel" AS fonte_combustivel,
        CASE WHEN "DscFonteCombustivel" IN {BIOGAS_FONTES} THEN 'Biogás' ELSE 'Biomassa' END AS categoria_energia,
        "NomFonteCombustivel" AS combustivel_detalhe,
        "DatEntradaOperacao" AS data_entrada_operacao,
        CAST(replace("MdaPotenciaOutorgadaKw", ',', '.') AS DOUBLE) AS potencia_outorgada_kw,
        CAST(replace("NumCoordNEmpreendimento", ',', '.') AS DOUBLE) AS latitude,
        CAST(replace("NumCoordEEmpreendimento", ',', '.') AS DOUBLE) AS longitude,
        "DscPropriRegimePariticipacao" AS proprietario,
        trim(replace("DscMuninicpios", ' - SP', '')) AS municipio
    FROM read_csv('{BRUTO_UTF8}', delim=';', header=true, encoding='utf-8', ignore_errors=true)
    WHERE "SigUFPrincipal" = 'SP'
      AND "DscOrigemCombustivel" = 'Biomassa'
      AND "DscFaseUsina" = 'Operação'
      AND "NumCoordNEmpreendimento" IS NOT NULL AND "NumCoordNEmpreendimento" != ''
      -- mesmo bounding box generoso de SP usado na geocodificacao das empresas
      AND CAST(replace("NumCoordNEmpreendimento", ',', '.') AS DOUBLE) BETWEEN -25.4 AND -19.5
      AND CAST(replace("NumCoordEEmpreendimento", ',', '.') AS DOUBLE) BETWEEN -53.5 AND -44.0
) TO '{SAIDA}' (HEADER, DELIMITER ',')
"""
con.sql(sql)
n = con.sql(f"SELECT count(*) FROM read_csv('{SAIDA}', header=true)").fetchone()[0]
print(f"{n} usinas de biogas/biomassa em operacao (SP) -> {SAIDA}")
con.sql(f"""SELECT categoria_energia, count(*) n, round(sum(potencia_outorgada_kw)/1000,1) as mw_total
            FROM read_csv('{SAIDA}', header=true) GROUP BY 1 ORDER BY 2 DESC""").show()
