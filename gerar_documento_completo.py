#!/usr/bin/env python3
"""Gera o documento completo do projeto: processo, dados, método, insights, conclusões e lacunas."""
import duckdb
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, PageBreak)

from maturidade import apura, NIVEL_INFO, CLASSE_INFO, ESTAGIO_INFO, ESTAGIOS
from dados_app import CAMADAS, MATERIAIS, CICLOS, carrega as carrega_app

SAIDA = 'documento_completo_mapa_economia_circular.pdf'
DATA_DOC = '05/09/2026'

VERDE = colors.HexColor('#1B5E20')
VERDE_MED = colors.HexColor('#2E7D32')
VERDE_CLARO = colors.HexColor('#E8F5E9')
VERMELHO_CLARO = colors.HexColor('#FFEBEE')
AMBAR_CLARO = colors.HexColor('#FFF8E1')
CINZA = colors.HexColor('#555555')
CINZA_CLARO = colors.HexColor('#F5F5F5')

CNAE_DESC = {
    '3811400': 'Coleta de resíduos não-perigosos',
    '3812200': 'Coleta de resíduos perigosos',
    '3821100': 'Tratamento/disposição não-perigosos',
    '3822000': 'Tratamento/disposição perigosos',
    '3831901': 'Recuperação de sucata de alumínio',
    '3831999': 'Recuperação de sucata metálica',
    '3832700': 'Recuperação de materiais plásticos',
    '3839401': 'Usinas de compostagem',
    '3839499': 'Recuperação de materiais (outros)',
    '3900500': 'Descontaminação',
}

con = duckdb.connect()
t_res = "read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true)"
t_en = "read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true)"

total_base = con.sql(f"SELECT count(*) FROM {t_res}").fetchone()[0]
total_geo = con.sql(f"SELECT count(*) FROM {t_res} WHERE latitude != ''").fetchone()[0]
total_energia = con.sql(f"SELECT count(*) FROM {t_en}").fetchone()[0]
total_mapa = total_geo + total_energia

status_geo = dict(con.sql(f"SELECT geocode_status, count(*) FROM {t_res} GROUP BY 1").fetchall())
por_cnae = dict(con.sql(f"SELECT cnae_principal, count(*) FROM {t_res} GROUP BY 1").fetchall())
por_categoria = dict(con.sql(f"""
    WITH u AS (SELECT categoria_circular FROM {t_res} WHERE latitude != ''
               UNION ALL SELECT categoria_circular FROM {t_en})
    SELECT categoria_circular, count(*) FROM u GROUP BY 1
""").fetchall())
mw_biomassa = str(con.sql(f"SELECT round(sum(CAST(potencia_outorgada_kw AS DOUBLE))/1000,1) FROM {t_en} WHERE categoria_energia='Biomassa'").fetchone()[0]).replace('.', ',')
mw_biogas = str(con.sql(f"SELECT round(sum(CAST(potencia_outorgada_kw AS DOUBLE))/1000,1) FROM {t_en} WHERE categoria_energia='Biogás'").fetchone()[0]).replace('.', ',')

por_ra = con.sql("""
    WITH n_mun AS (
      SELECT regiao_administrativa, count(*) qtd FROM read_csv('municipios_regiao_administrativa.csv', header=true) GROUP BY 1
    ), n_ini AS (
      SELECT regiao_administrativa, count(*) n FROM (
        SELECT regiao_administrativa FROM read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true) WHERE latitude!='' AND regiao_administrativa!=''
        UNION ALL SELECT regiao_administrativa FROM read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true) WHERE regiao_administrativa!=''
      ) GROUP BY 1
    )
    SELECT i.regiao_administrativa, i.n, m.qtd, round(i.n*1.0/m.qtd,1) norm
    FROM n_ini i JOIN n_mun m USING(regiao_administrativa) ORDER BY norm
""").fetchall()

# formata numeros isoladamente (nunca encadear .replace em string com prosa)
def fmt(n):
    return f'{n:,}'.replace(',', '.')

total_base_fmt, total_geo_fmt, total_mapa_fmt = fmt(total_base), fmt(total_geo), fmt(total_mapa)
pct_geo = f'{100*total_geo/total_base:.1f}%'
pct_falhou = f'{100*status_geo.get("falhou",0)/total_base:.1f}%'
# cobertura territorial calculada, não fixa: ficou desatualizada quando a
# geocodificação por CEP colocou mais 26 municípios no mapa
from enriquece import chave as _chave
_malha_cob = {f['properties']['municipio_norm'] for f in apura(con)['geojson_mun']['features']}
_com_ponto = set()
for _tab, _filtro in ((t_res, "latitude != ''"), (t_en, '1=1')):
    for (_mun,) in con.sql(f'SELECT DISTINCT municipio FROM {_tab} WHERE {_filtro}').fetchall():
        _com_ponto.add(_chave(_mun))
_com_ponto &= _malha_cob
N_MUN_TOTAL = len(_malha_cob)
N_COBERTOS = len(_com_ponto)
N_SEM_COB = N_MUN_TOTAL - N_COBERTOS
pct_cobertura = f'{100 * N_COBERTOS / N_MUN_TOTAL:.1f}%'.replace('.', ',')

# indice de maturidade: vem do MESMO modulo que gera o mapa, para o documento nunca
# divergir do que esta publicado
mat = apura(con)
dist_mun = mat['dist_municipal']
n_mun_total = mat['total_municipios']
media_estadual = f"{mat['media_estadual']:.2f}".replace('.', ',')
classes_ra = mat['classes_ra']
ras_por_classe = {}
for _nome, _c in classes_ra.items():
    ras_por_classe.setdefault(_c['classe'], []).append(_nome)
ras_por_hachura = {}
for _nome, _c in classes_ra.items():
    ras_por_hachura.setdefault(_c['listras'], []).append(_nome)
dist_estagio = mat['dist_estagio']
APP = carrega_app(con)
conta_camada, conta_material = APP['conta_camada'], APP['conta_material']
conta_ciclo, mw_ciclo = APP['conta_ciclo'], APP['mw_ciclo']

# cruzamento maturidade x contexto socioeconômico
import csv as _csv, math as _math, statistics as _st
_ctx = {r['cod_ibge']: r for r in _csv.DictReader(open('contexto_municipios.csv', encoding='utf-8'))}
_l = []
for _f in mat['geojson_mun']['features']:
    _c = _ctx.get(_f['properties']['codarea'])
    if _c and _c['idhm'] and _c['populacao']:
        _l.append((float(_c['idhm']), int(_c['populacao']), _f['properties']['nivel']))


def _pearson(xs, ys):
    mx, my = _st.mean(xs), _st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0


R_IDHM = _pearson([x[0] for x in _l], [x[2] for x in _l])
R_POP = _pearson([_math.log10(max(x[1], 1)) for x in _l], [x[2] for x in _l])
POP_N0 = int(_st.median([x[1] for x in _l if x[2] == 0]))
POP_N4 = int(_st.median([x[1] for x in _l if x[2] == 4]))
IDHM_N0 = _st.mean([x[0] for x in _l if x[2] == 0])
IDHM_N4 = _st.mean([x[0] for x in _l if x[2] == 4])

FALHA_RA = sorted(mat['falha_geocodificacao_ra'].items(), key=lambda x: -x[1]['pct'])
N_ZEROS_FALSOS = len(mat['municipios_sem_pin'])
TOTAL_SEM_COORD = mat['total_sem_coord']

mun_sem_registro = dist_mun[0]
pct_sem_registro = f'{100*mun_sem_registro/n_mun_total:.1f}%'


def num(v, casas=1):
    """Formata numero com virgula decimal SEM tocar na pontuacao do texto ao redor."""
    return f'{v:.{casas}f}'.replace('.', ',')

ss = getSampleStyleSheet()
h1 = ParagraphStyle('h1', parent=ss['Heading1'], textColor=VERDE, fontSize=15, spaceBefore=18, spaceAfter=7)
h2 = ParagraphStyle('h2', parent=ss['Heading2'], textColor=VERDE_MED, fontSize=11.5, spaceBefore=10, spaceAfter=4)
titulo = ParagraphStyle('titulo', parent=ss['Title'], textColor=VERDE, fontSize=21, leading=26)
sub = ParagraphStyle('sub', parent=ss['Normal'], textColor=CINZA, fontSize=11, spaceAfter=2)
corpo = ParagraphStyle('corpo', parent=ss['Normal'], fontSize=10.5, leading=15.5, spaceAfter=7)
item = ParagraphStyle('item', parent=corpo, leftIndent=12, spaceAfter=4)
cel = ParagraphStyle('cel', parent=ss['Normal'], fontSize=9.3, leading=12)
cel_b = ParagraphStyle('cel_b', parent=cel, textColor=colors.white, fontName='Helvetica-Bold')
cel_feito = ParagraphStyle('cel_feito', parent=cel, textColor=VERDE_MED, fontName='Helvetica-Bold')
cel_parcial = ParagraphStyle('cel_parcial', parent=cel, textColor=colors.HexColor('#B26A00'), fontName='Helvetica-Bold')
cel_naofeito = ParagraphStyle('cel_naofeito', parent=cel, textColor=colors.HexColor('#C62828'), fontName='Helvetica-Bold')
rodape = ParagraphStyle('rodape', parent=ss['Normal'], fontSize=8, textColor=CINZA, alignment=1)
resumo_box = ParagraphStyle('resumo', parent=corpo, backColor=VERDE_CLARO, borderPadding=10, leading=16)

story = []
def P(txt, st=corpo): story.append(Paragraph(txt, st))
def SP_(h=8): story.append(Spacer(1, h))
def linha(cor=colors.HexColor('#CCCCCC')): story.append(HRFlowable(width='100%', thickness=0.6, color=cor, spaceAfter=8))

# ============ CAPA / SUMARIO EXECUTIVO ============
P('Mapa de Economia Circular', titulo)
P('Estado de São Paulo — Documento Técnico Completo', sub)
P(f'Processo, dados, método, insights e lacunas · Revolução Circular, Geração 2027 (GD 1) · SENAC SP · {DATA_DOC}', sub)
SP_(6)
story.append(HRFlowable(width='100%', thickness=2, color=VERDE_MED, spaceAfter=12))

P('Sumário executivo', h1)
P(f'Este documento descreve, de forma completa, o trabalho realizado até o momento no projeto '
  f'Mapa de Economia Circular do estado de São Paulo: as fontes de dados usadas, o método de '
  f'extração e tratamento, o conteúdo dos mapas publicados, os insights que podem ser extraídos '
  f'da base atual, as conclusões possíveis dentro do que já foi levantado, e o que ainda falta '
  f'para atender integralmente ao escopo formal do projeto.'
  f'<br/><br/>'
  f'Em números: <b>{total_base_fmt} empresas</b> de resíduos sólidos urbanos identificadas via '
  f'CNPJ da Receita Federal (<b>{pct_geo}</b> geocodificadas), <b>239 usinas</b> de energia por '
  f'biogás/biomassa via ANEEL, agregadas por <b>16 Regiões Administrativas</b> e classificadas em '
  f'<b>4 categorias circulares</b> (ISO 59000), somando <b>{total_mapa_fmt} iniciativas</b> '
  f'georreferenciadas com cobertura de <b>{pct_cobertura}</b> dos municípios do estado. Os dados '
  f'estão publicados em <b>três mapas interativos</b>: o Hub Circular por Região Administrativa '
  f'(com índice de maturidade e navegação Estado - Região - Município - empresas), o mapa de '
  f'pontos individuais e o mapa de calor.', resumo_box)

SP_(10)
P('Mapas publicados:', h2)
P('— Hub Circular por Região Administrativa: <link href="https://helanmatos.github.io/mapa-economia-circular-sp/mapa_hub_circular.html">'
  'helanmatos.github.io/mapa-economia-circular-sp/mapa_hub_circular.html</link>', item)
P('— Mapa de pontos: <link href="https://helanmatos.github.io/mapa-economia-circular-sp/">'
  'helanmatos.github.io/mapa-economia-circular-sp</link>', item)
P('— Mapa de calor: <link href="https://helanmatos.github.io/mapa-economia-circular-sp/mapa_calor.html">'
  'helanmatos.github.io/mapa-economia-circular-sp/mapa_calor.html</link>', item)
P('— Repositório (código e dados): <link href="https://github.com/helanmatos/mapa-economia-circular-sp">'
  'github.com/helanmatos/mapa-economia-circular-sp</link>', item)

story.append(PageBreak())

# ============ 1. OBJETIVO E CONTEXTO ============
P('1. Objetivo e contexto do projeto', h1)
P('O projeto se insere no programa <b>Revolução Circular</b> (Geração 2027, GD 1) do SENAC SP, '
  'especificado no documento formal "Escopo de Construção para Mapa da Economia Circular – Estado '
  'de SP" (especialista Maiara Scarparo Rodrigues Esteves). O objetivo integrado definido no escopo '
  'é realizar um mapeamento sistemático das iniciativas de economia circular no estado, para: '
  'diagnosticar o estágio do ecossistema, subsidiar políticas públicas, e permitir benchmarking '
  'entre regiões.')
P('O escopo formal define <b>3 setores</b> centrais (resíduos sólidos urbanos, energia via biogás/'
  'biomassa, e logística reversa), pede classificação por <b>6 categorias circulares</b> da ISO '
  '59000 (reuso, reciclagem, remanufatura, bioeconomia, logística reversa, valorização energética), '
  'e uma matriz de dados por iniciativa incluindo tipo de organização, escala, estágio de '
  'maturidade e impacto (ambiental/econômico/social) — além de recomendar múltiplas fontes '
  '(institucionais, privadas, terceiro setor, academia).')
P('Este documento cobre o que foi construído até agora: a camada de dados de <b>resíduos sólidos '
  'urbanos</b> (via CNPJ) e <b>energia</b> (via ANEEL), enriquecida com Região Administrativa e '
  'categoria circular, publicada em dois mapas interativos.')

# ============ 2. FONTES DE DADOS ============
P('2. Fontes de dados', h1)
P('Três fontes de dados foram utilizadas até o momento, cada uma com propósito e cobertura '
  'distintos:')
fontes = [
    [Paragraph('Fonte', cel_b), Paragraph('Uso', cel_b), Paragraph('Cobertura', cel_b), Paragraph('Como foi obtida', cel_b)],
    [Paragraph('Receita Federal — CNPJ', cel), Paragraph('Empresas de resíduos sólidos, por CNAE', cel),
     Paragraph('Ativas, competência jun/2026', cel), Paragraph('Dados Abertos do CNPJ, mirror Casa dos Dados (site oficial mudou de estrutura em jan/2026)', cel)],
    [Paragraph('ANEEL — SIGA', cel), Paragraph('Usinas de biogás/biomassa em operação', cel),
     Paragraph('Operação, jul/2026', cel), Paragraph('Dados Abertos da ANEEL (Sistema de Informações de Geração), já com coordenadas oficiais', cel)],
    [Paragraph('IBGE / Wikipédia', cel), Paragraph('Município -> Região Administrativa (RA)', cel),
     Paragraph('645 municípios, 16 RAs', cel), Paragraph('Tabela extraída via pandas.read_html de fonte não-governamental (ver limitações, seção 8)', cel)],
]
tbl_fontes = Table(fontes, colWidths=[3.3*cm, 4.2*cm, 3*cm, 6.5*cm])
tbl_fontes.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(tbl_fontes)
SP_(8)
P('Os CNAEs de resíduos incluídos correspondem ao Grupo 38 da classificação CONCLA/IBGE (coleta, '
  'tratamento e disposição de resíduos; recuperação de materiais) mais o 3900-5/00 '
  '(descontaminação). CNAEs de energia em geral (3511-5/01, 3520-4/01) foram deliberadamente '
  'excluídos por serem genéricos demais — trariam qualquer usina/distribuidora de qualquer fonte '
  '(hídrica, fóssil, nuclear) e poluiriam a base; por isso energia foi tratada separadamente via '
  'ANEEL, que classifica cada usina por fonte de combustível.')

story.append(PageBreak())

# ============ 3. METODO / PIPELINE ============
P('3. Método — pipeline técnico', h1)
P('O processamento foi feito localmente com <b>DuckDB</b> (SQL analítico sobre arquivos, sem '
  'depender de nuvem/BigQuery), em 5 etapas sequenciais:')

etapas = [
    ('1. Extração CNPJ', 'Download dos 10 arquivos de Estabelecimentos da Receita Federal (~5 GB), processados parte por parte (baixa -> filtra SP + situação ativa + CNAE -> descarta o bruto) para não acumular dezenas de GB. Filtro aplicado direto no SQL.'),
    ('2. Geocodificação', 'Endereços convertidos em latitude/longitude via Nominatim/OpenStreetMap (gratuito, limite de 1 req/s). Estratégia em 3 tentativas por endereço: busca estruturada -> busca por texto livre -> aproximação pelo centro do CEP. Resultados fora do bounding box de SP são descartados (match ambíguo do geocodificador).'),
    ('3. Extração ANEEL', 'CSV público do SIGA (Sistema de Informações de Geração), filtrado por SP + origem "Biomassa" + fase "Operação". Já vem com coordenadas exatas — não precisa geocodificar. Classificado em Biogás (resíduos sólidos urbanos/animais) vs. Biomassa propriamente dita (agroindustrial/floresta).'),
    ('4. Enriquecimento', 'Duas camadas adicionadas: (a) Região Administrativa, via tabela de referência município->RA; (b) categoria circular ISO 59000, mapeando cada CNAE/tipo de energia para Reciclagem, Bioeconomia, Valorização energética ou Tratamento/disposição.'),
    ('5. Índice de maturidade', 'Para cada um dos 645 municípios, conta quantos dos 4 serviços da cadeia existem ali (coleta, reciclagem, tratamento/disposição, orgânicos). A classe de cada Região Administrativa é a média dos seus municípios, arredondada. Depende de casar o nome do município entre três fontes com grafias diferentes — ver seção 4.'),
    ('6. Geração dos mapas', 'MapLibre GL JS (renderização em GPU, sem chave de API) com basemap CARTO Positron gratuito. Três visualizações: Hub Circular por Região Administrativa (coroplético, com drill-down até a empresa), pontos individuais coloridos e mapa de calor (heatmap) com transição suave para pontos ao aproximar zoom. Filtros por Região Administrativa, setor/atividade e categoria circular.'),
]
for titulo_etapa, desc in etapas:
    P(f'<b>{titulo_etapa}</b> — {desc}', item)

SP_(6)
P('Decisões metodológicas relevantes:', h2)
P('— <b>Bounding box de SP</b>: coordenadas fora de um retângulo geográfico generoso do estado são '
  'descartadas (poucos casos de geocodificação ambígua que caem em outro estado).', item)
P('— <b>Encoding</b>: tanto o arquivo da Receita Federal quanto o da ANEEL continham bytes que o '
  'validador latin-1 do DuckDB rejeita — corrigido convertendo para UTF-8 via <i>iconv</i> antes de '
  'processar.', item)
P('— <b>Categoria circular não é o mesmo que CNAE bruto</b>: optei por manter "Tratamento/disposição" como '
  'categoria separada das 4 categorias circulares mapeadas, em vez de forçar aterro/descontaminação '
  'dentro de "Reciclagem" — são gestão linear de resíduos, não estratégia circular.', item)

# ============ 4. QUALIDADE E LIMITACOES DOS DADOS ============
story.append(PageBreak())
P('4. Qualidade e limitações dos dados', h1)
P(f'Da base de <b>{total_base_fmt} empresas</b>, <b>{total_geo_fmt} ({pct_geo})</b> foram '
  f'geocodificadas com sucesso. O detalhamento por status:')

dados_status = [
    [Paragraph('Status', cel_b), Paragraph('Linhas', cel_b), Paragraph('%', cel_b)],
    [Paragraph('Endereço estruturado (match direto)', cel), Paragraph(fmt(status_geo.get('endereco_estruturado',0)), cel), Paragraph(f"{100*status_geo.get('endereco_estruturado',0)/total_base:.1f}%", cel)],
    [Paragraph('CEP aproximado (fallback)', cel), Paragraph(fmt(status_geo.get('cep_aproximado',0)), cel), Paragraph(f"{100*status_geo.get('cep_aproximado',0)/total_base:.1f}%", cel)],
    [Paragraph('Endereço livre (fallback)', cel), Paragraph(fmt(status_geo.get('endereco_livre',0)), cel), Paragraph(f"{100*status_geo.get('endereco_livre',0)/total_base:.1f}%", cel)],
    [Paragraph('Falhou (sem coordenada)', cel), Paragraph(fmt(status_geo.get('falhou',0)), cel), Paragraph(pct_falhou, cel)],
    [Paragraph('Fora dos limites de SP (descartado)', cel), Paragraph(fmt(status_geo.get('fora_dos_limites_sp',0)), cel), Paragraph(f"{100*status_geo.get('fora_dos_limites_sp',0)/total_base:.2f}%", cel)],
]
tbl_status = Table(dados_status, colWidths=[9*cm, 3*cm, 3*cm])
tbl_status.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, 4), (-1, 4), VERMELHO_CLARO),
    ('ROWBACKGROUNDS', (0, 1), (-1, 3), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(tbl_status)
SP_(8)
P(f'O padrão de falha (<b>{pct_falhou}</b>) concentra-se em cidades pequenas do interior, em ruas '
  'nomeadas por pessoa que o OpenStreetMap ainda não mapeou — não é erro de processamento, é '
  'lacuna real de cobertura do OSM em municípios menores.')
P(f'A <b>cobertura territorial</b> (municípios com ao menos uma iniciativa mapeada) é de '
  f'<b>{pct_cobertura}</b> ({N_COBERTOS} de {N_MUN_TOTAL} municípios). Os {N_SEM_COB} restantes não têm nenhuma '
  'iniciativa identificada nesta etapa — o que reflete a fonte usada, não necessariamente ausência '
  'real de atividade econômica de resíduos ali.')
P('<b>Geocodificação em duas passadas</b>', h2)
P('A primeira passada usou o Nominatim/OpenStreetMap e localizou 8.719 dos 10.509 endereços '
  '(83%). Os 1.790 restantes eram de cidades pequenas do interior, que o OSM mapeia mal — e a '
  'falha não era uniforme, indo de 4,3% na 2ª Registro a 27,3% na 11ª Marília, concentrada '
  'justamente nas regiões que o mapa aponta como vazias:')
dados_vies = [[Paragraph('Região Administrativa', cel_b), Paragraph('Empresas', cel_b),
               Paragraph('Sem coordenada', cel_b), Paragraph('% de falha', cel_b)]]
for _ra, _d in FALHA_RA:
    dados_vies.append([Paragraph(_ra, cel), Paragraph(fmt(_d['total']), cel),
                       Paragraph(fmt(_d['sem_coord']), cel), Paragraph(num(_d['pct']) + '%', cel)])
tbl_vies = Table(dados_vies, colWidths=[6.4*cm, 3*cm, 3.6*cm, 3*cm])
tbl_vies.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, 1), (-1, 4), VERMELHO_CLARO),
    ('BACKGROUND', (0, -2), (-1, -1), VERDE_CLARO),
    ('ROWBACKGROUNDS', (0, 5), (-1, -3), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_vies)
SP_(8)
P('<b>A segunda passada fechou essa lacuna.</b> Todos os 1.790 endereços têm CEP de 8 dígitos '
  '(1.602 distintos), e o CEP tem coordenada em bases que não dependem do OpenStreetMap. Foram '
  'testadas quatro: a <b>BrasilAPI v2</b> devolveu coordenada para 97% dos CEPs de uma amostra, '
  'todas dentro do município correto; a AwesomeAPI respondeu 100% mas errou 8% (acerta o nome da '
  'cidade e devolve um ponto na Grande SP); ViaCEP não devolve coordenada; e o Photon erra o '
  'município. A BrasilAPI ficou como fonte principal e a AwesomeAPI como reserva.')
P('<b>Toda coordenada é validada contra o polígono do município declarado no CNPJ</b> e descartada '
  'se cair fora. É essa checagem que torna a reserva utilizável sem injetar erro grosseiro. '
  'Resultado: <b>1.785 dos 1.790 recuperados</b>, 5 descartados. Estabelecimentos sem coordenada '
  f'caíram de 1.790 para {fmt(TOTAL_SEM_COORD)}, municípios sem nenhum ponto no mapa de 33 para '
  f'{N_ZEROS_FALSOS}, e a pior taxa de falha regional de 27,3% para 0,2%.')
P(f'<b>O índice não mudou com isso</b> — a distribuição continua {dist_mun} e a média '
  f'{media_estadual}. É o esperado: o índice é calculado por município, e o município sempre '
  'esteve preenchido em 100% dos registros. A segunda passada corrigiu o <b>mapa</b>, não a '
  'medida. (A correção da medida veio antes, ao deixar de filtrar o índice por coordenada: '
  f'municípios sem infraestrutura caíram de 125 para {fmt(mun_sem_registro)} e a média subiu de '
  f'1,62 para {media_estadual}.)')
P('<b>Ressalva de precisão:</b> os 2.487 pontos vindos de CEP têm precisão de logradouro, não de '
  'número; em CEP geral de município caem no centro da cidade. O popup os marca como aproximados.')

P('<b>Casamento de nomes entre fontes</b>: as três fontes grafam o mesmo município de formas '
  'diferentes — a Receita Federal em maiúsculas sem acento, a ANEEL com acento e capitalização '
  'normal, o IBGE com a grafia oficial. Duas delas ainda divergem entre si em dois municípios '
  '(Luis/Luiz Antônio e São João do Pau d\'Alho, com e sem hífen), e a ANEEL usa acento agudo '
  'solto no lugar do apóstrofo em Santa Bárbara d\'Oeste. Todo cruzamento passa por uma única '
  'chave canônica; normalizar só um dos lados faz o cruzamento falhar em silêncio, sem erro e sem '
  'linha faltando — apenas com um número menor. Foi o que aconteceu numa versão anterior deste '
  'índice: 105 das 239 usinas de energia (44%, todas em municípios acentuados) ficavam fora do '
  'cálculo de maturidade. Corrigido, o índice passou a casar 238 das 239 usinas — a única que '
  'sobra tem "Não Informado" no campo de município na origem.')
P('<b>Limitação estrutural mais importante</b>: das 6 categorias circulares do escopo, <b>Reuso, '
  'Remanufatura e Logística reversa não aparecem</b> na base (0%). Isso não é uma falha de coleta — '
  'nenhuma dessas 3 categorias tem CNAE próprio na Receita Federal. Reuso e remanufatura não são '
  'atividades economicamente segregadas no cadastro nacional; logística reversa é uma <i>função</i> '
  'prevista na PNRS (Lei 12.305/2010), não uma atividade-fim, exercida por empresas já classificadas '
  'em outros CNAEs (varejo, transporte, ou os próprios CNAEs de resíduos já mapeados).')

# ============ 5. CONTEUDO DOS MAPAS ============
story.append(PageBreak())
P('5. Conteúdo dos mapas publicados', h1)
P('As visualizações foram unificadas em <b>uma única aplicação com quatro temas</b>, navegáveis '
  'por abas. Os dados são carregados uma vez só e o que muda entre os temas é filtro, cor e '
  'visibilidade de camada — por isso a troca é instantânea e o enquadramento do mapa é '
  'preservado. Os temas:')

P('5.1 Hub Circular por Região Administrativa', h2)
P('É o mapa mais estratégico dos três, e nasceu da reformulação proposta na reunião de produto de '
  f'07/09/2026: em vez de despejar {fmt(total_mapa)} pontos na tela, olhar primeiro a infraestrutura de cada '
  'região. O estado aparece dividido nas 16 Regiões Administrativas, coloridas por maturidade. '
  'Clicando numa região, ela se abre nos seus municípios, também coloridos; clicando num município, '
  'aparecem os pinos de cada empresa e usina. A navegação tem trilha (Estado - Região - Município) '
  'e botão de voltar.')
P('<b>O índice tem duas leituras, e a escala acompanha o nível de navegação</b> — média '
  'municipal no estado, escada nomeada no município. Não é preferência estética; é o que os '
  'dados sustentam, pelos motivos abaixo.')
P(f'— <b>Nível do município</b>: quantos dos 4 serviços existem ali. Dos {n_mun_total} municípios do '
  f'estado, {dist_mun[0]} estão no nível 0, {dist_mun[1]} no nível 1, {dist_mun[2]} no nível 2, '
  f'{dist_mun[3]} no nível 3 e apenas {dist_mun[4]} no nível 4 — média estadual de {media_estadual} '
  f'serviço por município.', item)
P('— <b>Classe da região</b>: a média dos seus municípios, arredondada. Não é a contagem de serviços '
  'da região, e por isso os dois rótulos são escritos de formas diferentes no mapa — a região fala em '
  '"média por município", o município fala em "N de 4 serviços". A leitura literal (quais serviços '
  'existem em algum ponto da região) continua disponível no popup, em linha própria.', item)
P('<b>A escada composicional no município.</b> A reunião descreveu a maturidade pelo que o '
  'lugar TEM, não por quantos itens tem: básico é coleta + reciclagem, estruturado acrescenta '
  'tratamento, circular acrescenta orgânicos. Essa leitura é melhor no município porque prioriza '
  f'o tratamento/disposição, que é o elo escasso do estado — {fmt(conta_camada["tratamento"])} '
  f'estabelecimentos, contra {fmt(conta_camada["coleta"])} de coleta e {fmt(conta_camada["triagem"])} '
  'de triagem. Tratar "orgânicos" e "tratamento" como equivalentes, que é o que a contagem faz, '
  'apaga justamente a escassez que importa.')
P(f'Aplicada aos {n_mun_total} municípios, a escada mostra {fmt(dist_estagio["circular"])} circulares, '
  f'{fmt(dist_estagio["estruturado"])} estruturados, {fmt(dist_estagio["basico"])} básicos, '
  f'<b>{fmt(dist_estagio["incipiente"])} incipientes</b> e {fmt(dist_estagio["sem"])} sem nenhuma '
  'infraestrutura. Os "incipientes" — quase um terço do estado — têm algum serviço mas não fecham '
  'nem coleta + reciclagem; a contagem simples os misturava com quem já tem a base montada. '
  'As duas escalas discordam em 120 municípios: 82 que a contagem chama de "quase completo" a '
  'escada mantém em "básico" por falta de tratamento, e 36 que a contagem chama de "intermediário" '
  'ela rebaixa a "incipiente" por falta de coleta.')
P('<b>Por que a escada NÃO serve para a região.</b> Agregada por Região Administrativa, ela volta '
  'a medir presença "em algum ponto do território" — exatamente o defeito que a média veio '
  'corrigir. Por ela, 12 das 16 regiões seriam "circulares", incluindo a 9ª Araçatuba, que tem '
  '<b>um único</b> estabelecimento de tratamento e 34,9% dos municípios sem nenhum registro; e a '
  '2ª Santos, sem nenhum município zerado, cairia para "estruturado". No app, forçar a escada no '
  'nível estadual exibe um aviso explicando o que aquela leitura esconde.')
P('A escolha da média em vez da presença regional é o que dá sentido ao mapa. Pela regra anterior, '
  'bastava um único município ter tratamento para a região inteira ser pintada como "circular '
  'completa", e 12 das 16 regiões apareciam no nível máximo. O caso mais claro era a 8ª São José do '
  'Rio Preto, pintada de verde-escuro tendo 38,5% dos seus municípios sem nenhum registro, enquanto '
  'a 2ª Santos, sem nenhum município zerado, aparecia abaixo dela.')
P('Uma <b>hachura diagonal</b> sobre o polígono codifica a fatia de municípios sem nenhum registro — '
  'um segundo canal, independente da cor, e o único que sobrevive à impressão em preto-e-branco. '
  f"Hoje {len(ras_por_hachura.get('liso', []))} regiões saem lisas, "
  f"{len(ras_por_hachura.get('leve', []))} com hachura leve e {len(ras_por_hachura.get('forte', []))} "
  'com hachura forte. Há ainda uma trava que rebaixa a classe de regiões muito vazias; vale registrar '
  'que, com os dados atuais, <b>ela não chega a ser acionada em nenhuma das 16 regiões</b> — é uma '
  'salvaguarda para o caso de uma região com média alta concentrada em poucos municípios, situação '
  'que hoje não ocorre.')

P('5.2 Tratamento de resíduos — cinco camadas combináveis', h2)
P('Atende ao pedido de sair da visão ponto-a-ponto e olhar a cadeia por função. As cinco '
  'camadas podem ser ligadas e desligadas independentemente e vistas em conjunto — dá para '
  f'cruzar coleta ({fmt(conta_camada["coleta"])} estabelecimentos) com triagem '
  f'({fmt(conta_camada["triagem"])}), ou isolar descontaminação ({fmt(conta_camada["descontaminacao"])}), '
  f'tratamento e disposição ({fmt(conta_camada["tratamento"])}) e orgânicos ({fmt(conta_camada["organicos"])}).')
P('O tema alterna ainda entre colorir os pontos por <b>camada da cadeia</b> ou por '
  '<b>categoria circular da ISO 59000</b> — que é o item 4 do escopo formal. Nessa segunda '
  f'leitura, Reciclagem soma {fmt(por_categoria.get("Reciclagem", 0))} iniciativas, Valorização '
  f'energética {fmt(por_categoria.get("Valorização energética", 0))}, Tratamento/disposição '
  f'{fmt(por_categoria.get("Tratamento/disposição", 0))} e Bioeconomia '
  f'{fmt(por_categoria.get("Bioeconomia", 0))}. Reuso, Remanufatura e Logística reversa aparecem '
  'na legenda com zero de propósito: a ausência delas é o achado, não uma omissão da '
  'visualização (ver seção 4).')
P('Dentro de "triagem e recuperação" há a sub-camada de <b>material recuperado</b>. Aqui o '
  'documento precisa ser honesto sobre um limite da fonte: a reunião pediu metal, plástico, '
  'papel, vidro, orgânico e construção civil, mas <b>só metal e plástico têm CNAE próprio</b> '
  f'na Receita Federal — metal ({fmt(conta_material["metal"])} estabelecimentos, CNAEs 3831-9/01 '
  f'e 3831-9/99) e plástico ({fmt(conta_material["plastico"])}, CNAE 3832-7/00). Papel, vidro e '
  f'construção civil caem todos no código genérico 3839-4/99 ({fmt(conta_material["outros"])} '
  'estabelecimentos) e são indistinguíveis entre si por esta fonte. Em vez de simular uma '
  'separação que o dado não sustenta, o terceiro balde é rotulado pelo que ele realmente é.')

P('5.3 Ciclo biológico', h2)
P(f'Reúne as {fmt(conta_ciclo["compostagem"] + conta_ciclo["biogas"] + conta_ciclo["biomassa"])} '
  f'unidades do ciclo orgânico: compostagem ({fmt(conta_ciclo["compostagem"])} usinas, via CNPJ), '
  f'biogás ({fmt(conta_ciclo["biogas"])} usinas, {num(mw_ciclo["biogas"])} MW) e biomassa '
  f'energética ({fmt(conta_ciclo["biomassa"])} usinas, {num(mw_ciclo["biomassa"])} MW). O raio de '
  'cada círculo é proporcional à potência outorgada, porque uma usina de 300 MW e uma de 0,5 MW '
  'não podem ter o mesmo peso visual. O padrão que salta é a concentração da biomassa no '
  'cinturão canavieiro — o oposto geográfico da concentração de resíduos sólidos.')

P('5.4 Contexto socioeconômico', h2)
P('Cruza o índice de maturidade com <b>população</b> (estimativa IBGE) e <b>IDHM</b> (base do '
  'Atlas do Desenvolvimento Humano, via Ipeadata), por município. O IDHM municipal disponível é '
  'o de <b>2010</b> — não por escolha de fonte, mas porque é o mais recente que existe: depois do '
  'Censo 2010 o índice passou a ser calculado com a PNAD Contínua, que só tem representatividade '
  'estadual, e a versão com o Censo 2022 ainda não foi publicada. O app declara essa defasagem '
  'na própria legenda. O cruzamento das duas camadas é o achado da seção 6.6.')

P('5.5 Mapa de pontos e mapa de calor', h2)
P('<b>Mapa de pontos</b> — cada iniciativa é um ponto individual no mapa, colorido por categoria. '
  'Ao clicar em um ponto, um popup mostra nome, CNAE ou tipo de combustível, endereço/município e, '
  'se aplicável, um aviso de localização aproximada. Painel lateral com contadores em tempo real, '
  'checkboxes por categoria e um seletor "colorir por": Atividade (10 CNAEs de resíduos + 2 tipos '
  'de energia) ou Categoria circular (as 4 categorias mapeadas).', item)
P('<b>Mapa de calor</b> — mostra densidade de iniciativas por região, útil para identificar '
  'concentrações e vazios sem a poluição visual de milhares de pontos sobrepostos. Ao aproximar o '
  'zoom (a partir do nível 10), os pontos individuais coloridos aparecem por cima do mapa de calor, '
  'com transição suave.', item)
P('Os três mapas têm: filtro por <b>Região Administrativa</b> (dropdown com as 16 RAs do estado), '
  'link cruzado entre as visualizações, e — em telas de celular (largura até 720px) — um botão '
  'para recolher o painel lateral e ver o mapa em tela cheia. No Hub Circular, como em tela sem '
  'hover o popup nunca apareceria, o primeiro toque numa região mostra os dados e o segundo entra '
  'nela.')
P('Tecnicamente, os mapas são arquivos HTML autocontidos (MapLibre GL JS via CDN, sem servidor '
  'próprio necessário) publicados como GitHub Pages, com todos os dados embutidos no próprio '
  'arquivo.')

# ============ 6. INSIGHTS ============
story.append(PageBreak())
P('6. Insights extraídos da base atual', h1)

P('6.1 Distribuição por atividade (resíduos)', h2)
dados_cnae = [[Paragraph('CNAE', cel_b), Paragraph('Descrição', cel_b), Paragraph('Empresas', cel_b)]]
for cod, desc in CNAE_DESC.items():
    dados_cnae.append([Paragraph(f'{cod[:4]}-{cod[4]}/{cod[5:]}', cel), Paragraph(desc, cel), Paragraph(fmt(por_cnae.get(cod,0)), cel)])
tbl_cnae = Table(dados_cnae, colWidths=[2.5*cm, 10.5*cm, 3*cm])
tbl_cnae.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_cnae)
SP_(6)
P('Coleta de resíduos não-perigosos e recuperação de plásticos/sucata metálica dominam — coerente '
  'com um estado altamente urbanizado e industrializado.')

P('6.2 Energia: concentração geográfica clara', h2)
P(f'Das {fmt(total_energia)} usinas, {fmt(226)} são de biomassa propriamente dita '
  f'({mw_biomassa} MW, majoritariamente bagaço de cana) e {fmt(13)} de biogás ({mw_biogas} MW, '
  'aterro/dejetos). A distribuição geográfica no mapa mostra concentração quase total no cinturão '
  'canavieiro do interior (Ribeirão Preto, São José do Rio Preto, Franca) — o oposto do padrão de '
  'resíduos sólidos, que se concentra na Grande SP. Isso sugere que <b>diagnósticos regionais de '
  'economia circular precisam necessariamente olhar setor por setor</b>, já que um único ranking '
  'geral esconderia essa divisão.')

P('6.3 Concentração regional e "desertos circulares"', h2)
dados_ra = [[Paragraph('Região Administrativa', cel_b), Paragraph('Iniciativas', cel_b), Paragraph('Municípios', cel_b), Paragraph('Iniciativas/Município', cel_b)]]
for ra, n, qtd, norm in por_ra:
    norm_fmt = f'{norm}'.replace('.', ',')
    dados_ra.append([Paragraph(ra, cel), Paragraph(fmt(n), cel), Paragraph(str(qtd), cel), Paragraph(norm_fmt, cel)])
tbl_ra = Table(dados_ra, colWidths=[6*cm, 3*cm, 3*cm, 4*cm])
tbl_ra.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, 1), (-1, 3), VERMELHO_CLARO),
    ('BACKGROUND', (0, -1), (-1, -1), VERDE_CLARO),
    ('ROWBACKGROUNDS', (0, 4), (-1, -2), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_ra)
SP_(6)
P('Em vermelho, as 3 RAs com menor densidade de iniciativas por município: <b>Itapeva (2,5)</b>, '
  '<b>Registro (3,1)</b> e <b>Araçatuba (3,4)</b>. Registro (Vale do Ribeira) é historicamente a '
  'região mais pobre e menos industrializada do estado — o achado bate com o que já se sabe da '
  'região, o que dá credibilidade à leitura. Em verde, a <b>Grande SP</b>, com <b>93,8</b> '
  'iniciativas por município — quase 40× a região mais carente.')

P('6.4 Categoria circular: desequilíbrio estrutural', h2)
dados_circ = [[Paragraph('Categoria', cel_b), Paragraph('Iniciativas', cel_b), Paragraph('%', cel_b)]]
ordem_circ = ['Reciclagem', 'Valorização energética', 'Tratamento/disposição', 'Bioeconomia', 'Reuso', 'Remanufatura', 'Logística reversa']
for cat in ordem_circ:
    n = por_categoria.get(cat, 0)
    dados_circ.append([Paragraph(cat, cel), Paragraph(fmt(n) if n else '0', cel), Paragraph(f'{100*n/total_mapa:.1f}%' if n else '—', cel)])
tbl_circ = Table(dados_circ, colWidths=[7*cm, 4*cm, 3*cm])
tbl_circ.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, -3), (-1, -1), VERMELHO_CLARO),
    ('ROWBACKGROUNDS', (0, 1), (-1, -4), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_circ)
SP_(6)
P('94,4% da base cai em "Reciclagem" — um resultado esperado dado que a fonte primária (CNPJ) '
  'captura sobretudo empresas formais desse tipo de atividade, não iniciativas de reuso, '
  'remanufatura ou logística reversa propriamente ditas (ver seção 4).')

P('6.5 Maturidade: o vazio está dentro das regiões, não entre elas', h2)
dados_mat = [[Paragraph('Nível do município', cel_b), Paragraph('Municípios', cel_b),
              Paragraph('%', cel_b), Paragraph('Leitura', cel_b)]]
leitura_nivel = {
    0: 'Nenhum dos 4 serviços mapeado',
    1: 'Apenas um serviço (quase sempre coleta ou reciclagem)',
    2: 'Dois serviços',
    3: 'Três serviços — falta um elo',
    4: 'Cadeia completa no próprio município',
}
for k in range(4, -1, -1):
    dados_mat.append([Paragraph(f'{k} — {NIVEL_INFO[k][0].split(" (")[0]}', cel),
                      Paragraph(fmt(dist_mun[k]), cel),
                      Paragraph(f'{100*dist_mun[k]/n_mun_total:.1f}%', cel),
                      Paragraph(leitura_nivel[k], cel)])
tbl_mat = Table(dados_mat, colWidths=[4.6*cm, 2.4*cm, 1.8*cm, 7.2*cm])
tbl_mat.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, 1), (-1, 1), VERDE_CLARO),
    ('BACKGROUND', (0, -1), (-1, -1), VERMELHO_CLARO),
    ('ROWBACKGROUNDS', (0, 2), (-1, -2), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_mat)
SP_(6)
P(f'Este é o achado mais forte do Hub Circular, e ele só aparece quando se desce ao município. '
  f'Apenas <b>{dist_mun[4]} municípios em {n_mun_total}</b> ({100*dist_mun[4]/n_mun_total:.1f}%) têm a '
  f'cadeia completa, enquanto <b>{mun_sem_registro}</b> ({pct_sem_registro}) não têm nenhum dos quatro '
  f'serviços. A média estadual é de {media_estadual} serviço por município.')
P('No agregado por região o quadro parece muito melhor do que é: <b>todas as 16 Regiões '
  'Administrativas têm pelo menos 3 dos 4 serviços presentes em algum ponto do seu território</b>, e '
  '12 delas têm os 4. Ou seja, olhando só a região, o estado inteiro pareceria resolvido. A distância '
  'entre essas duas leituras — região aparentemente completa, municípios majoritariamente incompletos '
  '— é a informação útil: <b>o problema em São Paulo não é a ausência de infraestrutura circular na '
  'região, é a distância até ela dentro da própria região.</b>')
P('<b>Ressalva:</b> estes números já incluem as empresas sem coordenada, contadas pelo município '
  '(ver seção 4). A leitura correta de "sem infraestrutura" é "nenhum estabelecimento dos 4 '
  'serviços registrado na Receita Federal com sede naquele município" — o que não exclui operação '
  'informal, cooperativa não formalizada ou atendimento por município vizinho.')
P('Isso muda o tipo de política que faz sentido. Se o vazio fosse entre regiões, a resposta seria '
  'levar infraestrutura para as regiões desassistidas. Como o vazio é interno, a resposta passa mais '
  'por consórcios intermunicipais, logística de transbordo e escala compartilhada do que por novas '
  'instalações em cada município — algo que a leitura por região, sozinha, esconderia.')

P('6.6 O que prevê a infraestrutura circular não é a renda, é a escala', h2)
P('A reunião levantou a hipótese de que o vazio circular acompanharia o IDH baixo — a região de '
  'Registro foi citada como exemplo. Com os dados agora cruzados, a hipótese se confirma em '
  'direção, mas não em força, e o que aparece no lugar é mais acionável.')
dados_cruz = [
    [Paragraph('Nível do município', cel_b), Paragraph('Municípios', cel_b),
     Paragraph('IDHM médio', cel_b), Paragraph('População mediana', cel_b)],
]
for k in range(4, -1, -1):
    _sub = [x for x in _l if x[2] == k]
    dados_cruz.append([
        Paragraph(f'{k} — {NIVEL_INFO[k][0].split(" (")[0]}', cel),
        Paragraph(fmt(len(_sub)), cel),
        Paragraph(num(_st.mean([x[0] for x in _sub]), 3), cel),
        Paragraph(fmt(int(_st.median([x[1] for x in _sub]))), cel)])
tbl_cruz = Table(dados_cruz, colWidths=[5.4*cm, 2.6*cm, 3*cm, 5*cm])
tbl_cruz.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, 1), (-1, 1), VERDE_CLARO),
    ('BACKGROUND', (0, -1), (-1, -1), VERMELHO_CLARO),
    ('ROWBACKGROUNDS', (0, 2), (-1, -2), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_cruz)
SP_(6)
P(f'A correlação entre maturidade e <b>tamanho da população</b> é de <b>{num(R_POP, 2)}</b>; '
  f'entre maturidade e <b>IDHM</b>, de <b>{num(R_IDHM, 2)}</b>. A população mediana salta de '
  f'<b>{fmt(POP_N0)}</b> habitantes nos municípios sem nenhum serviço para <b>{fmt(POP_N4)}</b> '
  f'nos que têm os quatro — um fator de {round(POP_N4/POP_N0)} vezes. No mesmo intervalo o IDHM '
  f'médio mal se move: {num(IDHM_N0, 3)} contra {num(IDHM_N4, 3)}.')
P('A leitura prática muda com isso. Se o determinante fosse a renda, a resposta seria política '
  'de desenvolvimento regional. Como o determinante é a <b>escala</b>, a resposta é arranjo '
  'intermunicipal: um município de 4 mil habitantes não sustenta um aterro licenciado nem uma '
  'usina de triagem, por mais rico que seja. Combinado com o achado da seção 6.5 — o vazio está '
  'dentro das regiões, não entre elas — isso aponta para consórcios, transbordo e escala '
  'compartilhada como o instrumento central, não para instalação nova em cada município.')
P('Vale registrar a ressalva metodológica: o IDHM é de 2010 e a população é estimativa atual. '
  'A defasagem não invalida a comparação (a hierarquia de IDH entre municípios é bastante '
  'estável no tempo), mas precisa estar declarada.')

# ============ 7. CONCLUSOES ============
story.append(PageBreak())
P('7. Conclusões possíveis com os dados atuais', h1)
P('— A <b>economia circular formal e registrada em SP</b>, no recorte resíduos + energia, está '
  'fortemente concentrada na <b>Grande São Paulo</b> (41% de toda a base) e no <b>eixo Campinas–'
  'Sorocaba</b>, refletindo o padrão geral de industrialização e urbanização do estado.', item)
P('— Existe uma <b>divisão setorial nítida por geografia</b>: resíduos sólidos concentram-se nos '
  'polos urbanos/metropolitanos, enquanto energia (biogás/biomassa) concentra-se no interior '
  'agrícola — nenhuma política pública única serviria igualmente bem aos dois padrões.', item)
P('— Há <b>evidência concreta de "desertos circulares"</b> (Itapeva, Registro, Araçatuba) que — '
  'cruzada com o fato de Registro ser historicamente a região mais pobre do estado — sugere uma '
  'correlação entre desenvolvimento econômico regional e presença de infraestrutura formal de '
  'economia circular, não necessariamente uma escolha de política ambiental.', item)
P('— A <b>base atual mede a formalização</b> da economia circular (empresas registradas, usinas '
  'outorgadas), não a atividade circular em si. Iniciativas informais, cooperativas de catadores, '
  'programas públicos e ações de reuso/remanufatura/logística reversa não aparecem — qualquer '
  'leitura sobre "onde a economia circular é fraca" precisa ser lida como "onde a economia circular '
  '<i>formal e mensurável por CNPJ</i> é fraca", que é uma pergunta mais restrita do que a do '
  'escopo original.', item)

# ============ 8. O QUE FALTA ============
story.append(PageBreak())
P('8. O que falta dentro do escopo do projeto', h1)
P('Comparando o que foi construído com os 11 itens do escopo formal:')

status_escopo = [
    [Paragraph('Item do escopo', cel_b), Paragraph('Status', cel_b), Paragraph('Observação', cel_b)],
    [Paragraph('1. Objetivo integrado (diagnóstico, políticas, benchmarking)', cel), Paragraph('Parcial', cel_parcial), Paragraph('Base de dados e mapas prontos; análise formal de políticas públicas ainda não escrita como documento à parte', cel)],
    [Paragraph('2. Escopo geográfico por Região Administrativa', cel), Paragraph('Feito', cel_feito), Paragraph('16 RAs mapeadas e filtráveis', cel)],
    [Paragraph('3. Três setores (resíduos, energia, logística reversa)', cel), Paragraph('2 de 3', cel_parcial), Paragraph('Logística reversa sem fonte de dado própria (não tem CNAE)', cel)],
    [Paragraph('4. Seis categorias circulares (ISO 59000)', cel), Paragraph('4 de 6', cel_parcial), Paragraph('Reuso, Remanufatura e Logística reversa estruturalmente ausentes', cel)],
    [Paragraph('5. Matriz de classificação (tipo, escala, maturidade, impacto)', cel), Paragraph('Não feito', cel_naofeito), Paragraph('Só temos: nome, CNAE, endereço, RA, categoria. Falta tipo (pública/ONG/academia), escala, maturidade, impacto', cel)],
    [Paragraph('6. Múltiplas fontes', cel), Paragraph('2 de 8+', cel_parcial), Paragraph('CETESB, SNIS e cooperativas de catadores bloqueados até 25/10/2026 (apagão eleitoral); FIESP/CIESP e academia sem dado estruturado público', cel)],
    [Paragraph('7. Limpeza e padronização', cel), Paragraph('Feito', cel_feito), Paragraph('Filtro de ativas, normalização de município, categorização circular', cel)],
    [Paragraph('8. Georreferenciamento + Região Administrativa', cel), Paragraph('Feito', cel_feito), Paragraph('', cel)],
    [Paragraph('9. Construção do mapa (pontos, cores, filtros, camadas extras)', cel), Paragraph('Parcial', cel_parcial), Paragraph('Pontos, calor, Hub Circular por RA com drill-down e filtros prontos; faltam camadas de densidade populacional, IDH e polos industriais', cel)],
    [Paragraph('10. Análise estratégica', cel), Paragraph('Feito', cel_feito), Paragraph('Documento em separado + seções 6-7 deste documento', cel)],
    [Paragraph('11. Indicadores e KPIs', cel), Paragraph('Parcial', cel_parcial), Paragraph('Cobertura territorial, % por categoria, concentração regional e índice de maturidade de infraestrutura prontos. Atenção: o escopo pede maturidade DA INICIATIVA (ideia, piloto, operação), que é outra coisa e não existe em CNPJ/ANEEL; impacto estimado também não', cel)],
]
tbl_escopo = Table(status_escopo, colWidths=[6*cm, 2.3*cm, 8*cm])
tbl_escopo.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(tbl_escopo)
SP_(8)

P('Reformulação pedida na reunião de 07/09/2026', h2)
P('Além dos 11 itens do escopo formal, a reunião de produto definiu uma reformulação em três mapas '
  'temáticos. O quadro abaixo é o estado real dessa reformulação:')

reuniao = [
    [Paragraph('O que foi pedido na reunião', cel_b), Paragraph('Status', cel_b), Paragraph('Observação', cel_b)],
    [Paragraph('<b>Mapa 1</b> — Hub Circular por Região Administrativa, com indicador de maturidade da regional', cel),
     Paragraph('Feito', cel_feito),
     Paragraph('Publicado, com drill-down até a empresa. A escada nomeada da reunião (básico / estruturado / circular) foi implementada como leitura composicional e é o padrão no nível município; a escala 0-4 por média municipal é o padrão no nível estado, porque a escada agregada por região volta a esconder o vazio interno.', cel)],
    [Paragraph('<b>Mapa 2</b> — Tratamento de resíduos com 5 camadas (coleta, triagem, orgânicos, tratamento, descontaminação)', cel),
     Paragraph('Feito', cel_feito),
     Paragraph('Tema próprio no app, com as 5 camadas e alternância entre pontos e densidade', cel)],
    [Paragraph('Camadas do Mapa 2 combináveis entre si', cel),
     Paragraph('Feito', cel_feito),
     Paragraph('Cada camada liga e desliga independentemente; o contador do painel acompanha a seleção em tempo real', cel)],
    [Paragraph('Sub-camada de materiais (metal, plástico, papel, vidro, orgânico, construção civil)', cel),
     Paragraph('Parcial', cel_parcial),
     Paragraph('Feito para metal e plástico, que têm CNAE próprio. Papel, vidro e construção civil caem todos no genérico 3839-4/99 e ficam num terceiro balde rotulado como tal — a fonte não permite separá-los. Precisaria de outra fonte para as 6 categorias pedidas.', cel)],
    [Paragraph('<b>Mapa 3</b> — Ciclo biológico (compostagem, biodigestão, biogás, biomassa, açúcar e álcool)', cel),
     Paragraph('Feito', cel_feito),
     Paragraph('Tema próprio, com o raio do círculo proporcional à potência outorgada', cel)],
    [Paragraph('Cruzamento com IDH e densidade populacional por região', cel),
     Paragraph('Feito', cel_feito),
     Paragraph('Tema "Contexto", com população (IBGE) e IDHM (Ipeadata/Atlas) nos 645 municípios. Ver a análise na seção 6.6', cel)],
    [Paragraph('Pesquisar alcance/raio de atendimento das empresas', cel),
     Paragraph('Não feito', cel_naofeito),
     Paragraph('Levantado na reunião como possibilidade exploratória, não como requisito. Não há fonte pública estruturada; exigiria pesquisa empresa a empresa.', cel)],
]
tbl_reuniao = Table(reuniao, colWidths=[5.4*cm, 2.4*cm, 8.5*cm])
tbl_reuniao.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(tbl_reuniao)
SP_(8)
P('Em resumo: <b>os 3 mapas temáticos estão entregues</b>, mais o cruzamento socioeconômico e a '
  'escada nomeada. Resta um único ponto em aberto, e ele é de fonte e não de execução: a '
  '<b>sub-camada de materiais</b>, que o CNAE só comporta para metal e plástico.')

SP_(8)
P('Bloqueio externo — apagão eleitoral', h2)
P('CETESB, SNIS e o cadastro de cooperativas de catadores (SINIR) estão indisponíveis até '
  '<b>25/10/2026</b>, por força do período de defeso eleitoral (Lei 9.504/1997, art. 73 VI "b", '
  'Resolução TSE 23.735/2024), que suspende atualizações/publicidade em sites institucionais do '
  'governo. Não é uma limitação técnica nossa — é uma restrição legal temporária que afeta '
  'qualquer tentativa de acessar essas 3 fontes até a data.')

P('Próximos passos recomendados', h2)
P('— <b>Construir os Mapas 2 e 3</b> da reformulação. Nenhum dos dois depende de fonte bloqueada: '
  'os dados já estão na base e o trabalho é de visualização. O Mapa 3 (ciclo biológico) é o mais '
  'rápido.', item)
P('— <b>Alinhar a nomenclatura do índice de maturidade</b> com a especialista: 5 classes numéricas '
  '(atual) ou os 3 níveis nomeados propostos na reunião (básico / estruturado / circular).', item)
P('— <b>Cruzar com população e IDH municipal</b>, que é o que permite ler o vazio interno das '
  'regiões como desigualdade e não só como ausência de empresa.', item)
P('— Aguardar 25/10/2026 e então integrar CETESB (Inventário Estadual de Resíduos, requer '
  'extração de tabelas de PDF), SNIS (série histórica de saneamento) e o cadastro de cooperativas '
  'de catadores (SINIR/CATAsampa).', item)
P('— Buscar contato direto com FIESP/CIESP e universidades (USP/Unicamp/Unesp/SENAC) para dados '
  'que não existem em formato aberto.', item)
P('— Desenhar e aplicar uma pesquisa primária (questionário) para obter tipo de organização, '
  'escala e estágio de maturidade — dados que nenhuma fonte administrativa aberta contém.', item)
P('— Adicionar camadas de densidade populacional e polos industriais ao mapa (dados IBGE, sem '
  'depender das fontes bloqueadas).', item)
P('— Reavaliar se logística reversa pode ser aproximada por outros proxies (ex: empresas com '
  'CNAE de comércio atacadista de resíduos/sucata, ou parcerias com sistemas de logística reversa '
  'existentes por lei, como pneus e eletroeletrônicos).', item)

SP_(14)
linha()
P('Documento gerado automaticamente a partir da base georreferenciada do projeto. '
  'Acompanha os mapas publicados e o repositório de código.', rodape)

doc = SimpleDocTemplate(SAIDA, pagesize=A4, topMargin=1.8*cm, bottomMargin=1.6*cm,
                        leftMargin=2*cm, rightMargin=2*cm,
                        title='Mapa de Economia Circular SP — Documento Técnico Completo',
                        author='SENAC SP')
doc.build(story)
print(f'PDF gerado: {SAIDA}')
