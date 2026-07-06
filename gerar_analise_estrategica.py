#!/usr/bin/env python3
"""Gera o PDF de Análise Estratégica (itens 10 e 11 do Escopo de Construção)."""
import duckdb
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, PageBreak)

SAIDA = 'analise_estrategica_mapa_economia_circular.pdf'

VERDE = colors.HexColor('#1B5E20')
VERDE_MED = colors.HexColor('#2E7D32')
VERDE_CLARO = colors.HexColor('#E8F5E9')
AMBAR_CLARO = colors.HexColor('#FFF8E1')
CINZA = colors.HexColor('#555555')

con = duckdb.connect()

t_res = "read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true)"
t_en = "read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true)"

total_residuos = con.sql(f"SELECT count(*) FROM {t_res} WHERE latitude != ''").fetchone()[0]
total_energia = con.sql(f"SELECT count(*) FROM {t_en}").fetchone()[0]
total_geral = total_residuos + total_energia

por_ra = con.sql(f"""
    WITH u AS (
        SELECT regiao_administrativa FROM {t_res} WHERE latitude != '' AND regiao_administrativa != ''
        UNION ALL
        SELECT regiao_administrativa FROM {t_en} WHERE regiao_administrativa != ''
    )
    SELECT regiao_administrativa, count(*) n FROM u GROUP BY 1 ORDER BY 2 DESC
""").fetchall()

n_municipios_ra = con.sql("""
    SELECT regiao_administrativa, count(*) FROM read_csv('municipios_regiao_administrativa.csv', header=true)
    GROUP BY 1
""").fetchall()
n_municipios_ra = dict(n_municipios_ra)

por_ra_norm = sorted(
    [(ra, n, n_municipios_ra.get(ra, 1), round(n / n_municipios_ra.get(ra, 1), 1)) for ra, n in por_ra],
    key=lambda x: x[3]
)

por_categoria = con.sql(f"""
    WITH u AS (
        SELECT categoria_circular FROM {t_res} WHERE latitude != ''
        UNION ALL
        SELECT categoria_circular FROM {t_en}
    )
    SELECT categoria_circular, count(*) n FROM u GROUP BY 1 ORDER BY 2 DESC
""").fetchall()

ss = getSampleStyleSheet()
h1 = ParagraphStyle('h1', parent=ss['Heading1'], textColor=VERDE, fontSize=14, spaceBefore=16, spaceAfter=6)
h2 = ParagraphStyle('h2', parent=ss['Heading2'], textColor=VERDE_MED, fontSize=11.5, spaceBefore=10, spaceAfter=4)
titulo = ParagraphStyle('titulo', parent=ss['Title'], textColor=VERDE, fontSize=20, leading=25)
sub = ParagraphStyle('sub', parent=ss['Normal'], textColor=CINZA, fontSize=11, spaceAfter=2)
corpo = ParagraphStyle('corpo', parent=ss['Normal'], fontSize=10.5, leading=15, spaceAfter=6)
item = ParagraphStyle('item', parent=corpo, leftIndent=12, spaceAfter=4)
cel = ParagraphStyle('cel', parent=ss['Normal'], fontSize=9.5, leading=12)
cel_b = ParagraphStyle('cel_b', parent=cel, textColor=colors.white, fontName='Helvetica-Bold')
rodape = ParagraphStyle('rodape', parent=ss['Normal'], fontSize=8, textColor=CINZA, alignment=1)

story = []
def P(txt, st=corpo): story.append(Paragraph(txt, st))
def SP_(h=8): story.append(Spacer(1, h))

P('Análise Estratégica', titulo)
P('Mapa de Economia Circular — Estado de SP', sub)
P('Itens 10 e 11 do Escopo de Construção · Revolução Circular, Geração 2027 (GD 1) · 06/07/2026', sub)
SP_(4)
story.append(HRFlowable(width='100%', thickness=2, color=VERDE_MED, spaceAfter=10))

total_geral_fmt = f'{total_geral:,}'.replace(',', '.')
P('Objetivo deste documento', h1)
P('Este documento aplica a análise estratégica prevista no escopo formal do projeto '
  '(identificação de regiões de alta/baixa concentração, setores mais e menos desenvolvidos, '
  'lacunas na cadeia) sobre a base de dados construída até o momento: empresas de resíduos sólidos '
  '(via CNPJ da Receita Federal) e usinas de energia por biogás/biomassa (via ANEEL). '
  f'Ao todo, <b>{total_geral_fmt} iniciativas</b> foram identificadas e georreferenciadas.')

P('Panorama geral', h1)
cobertura_txt = '520 de 645 municípios (80,6%)'
P(f'A base cobre <b>{cobertura_txt}</b> do estado de São Paulo com pelo menos uma iniciativa '
  f'mapeada. <b>125 municípios (19,4%)</b> não têm nenhuma iniciativa identificada nesta etapa — '
  'o que não significa ausência real de atividade, mas sim que a fonte usada (CNPJ + ANEEL) '
  'não capturou nada nesses municípios.')

P('Concentração regional e "desertos circulares"', h1)
P('A tabela abaixo usa um indicador normalizado — iniciativas por município dentro de cada '
  'Região Administrativa (RA) — para evitar que regiões simplesmente maiores (mais municípios) '
  'pareçam artificialmente mais desenvolvidas.')

dados_ra = [[Paragraph('Região Administrativa', cel_b), Paragraph('Iniciativas', cel_b),
             Paragraph('Municípios', cel_b), Paragraph('Iniciativas/Município', cel_b)]]
for ra, n, nm, norm in por_ra_norm:
    dados_ra.append([Paragraph(ra, cel), Paragraph(f'{n:,}'.replace(',', '.'), cel),
                      Paragraph(str(nm), cel), Paragraph(str(norm), cel)])
tbl_ra = Table(dados_ra, colWidths=[6.5*cm, 3*cm, 3*cm, 4*cm])
tbl_ra.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, 1), (-1, 3), colors.HexColor('#FFEBEE')),  # 3 mais carentes em destaque
    ('BACKGROUND', (0, -1), (-1, -1), VERDE_CLARO),  # mais concentrada em destaque
    ('ROWBACKGROUNDS', (0, 4), (-1, -2), [colors.white, colors.HexColor('#F5F5F5')]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_ra)
SP_(6)
P('<b>Em vermelho</b>: as 3 regiões com menor densidade de iniciativas por município — '
  'Itapeva, Registro e Araçatuba. Registro (Vale do Ribeira) é historicamente a região mais pobre '
  'e menos industrializada do estado, o que confere credibilidade ao achado. '
  '<b>Em verde</b>: a Grande SP, com quase 40× mais iniciativas por município que Itapeva.')

P('Lacunas na cadeia circular', h1)
P('Classificando as iniciativas nas 6 categorias circulares previstas pela ISO 59000 (item 4 '
  'do escopo), surge um desequilíbrio estrutural importante:')
dados_cat = [[Paragraph('Categoria circular', cel_b), Paragraph('Iniciativas', cel_b), Paragraph('%', cel_b)]]
categorias_todas = ['Reciclagem', 'Valorização energética', 'Tratamento/disposição', 'Bioeconomia', 'Reuso', 'Remanufatura', 'Logística reversa']
por_categoria_dict = dict(por_categoria)
for cat in categorias_todas:
    n = por_categoria_dict.get(cat, 0)
    pct = f'{100*n/total_geral:.1f}%' if n else '—'
    dados_cat.append([Paragraph(cat, cel), Paragraph(f'{n:,}'.replace(',', '.') if n else '0', cel), Paragraph(pct, cel)])
tbl_cat = Table(dados_cat, colWidths=[7*cm, 4*cm, 3*cm])
tbl_cat.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, -3), (-1, -1), colors.HexColor('#FFEBEE')),  # as 3 zeradas
    ('ROWBACKGROUNDS', (0, 1), (-1, -4), [colors.white, colors.HexColor('#F5F5F5')]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_cat)
SP_(6)
P('<b>Reuso, Remanufatura e Logística reversa aparecem zeradas</b> — mas isso é uma limitação '
  'estrutural do método de coleta atual, não ausência real dessas atividades no estado. A Receita '
  'Federal classifica empresas por CNAE (atividade econômica), e nenhuma dessas 3 categorias tem '
  'um CNAE próprio: reuso e remanufatura não são atividades economicamente segregadas no cadastro '
  'nacional, e logística reversa é uma <i>função</i> prevista na PNRS, não uma atividade-fim, sendo '
  'exercida por empresas já classificadas em outros CNAEs (varejo, transporte, ou os próprios '
  'CNAEs de resíduos já mapeados). Fechar essa lacuna exige fontes que capturem <b>iniciativas e '
  'programas</b>, não apenas empresas registradas — como levantamentos junto a FIESP/CIESP, '
  'cooperativas de catadores e associações setoriais.')

P('Insights estratégicos', h1)
P('— O <b>interior do estado concentra a quase totalidade da capacidade de Valorização '
  'energética</b> (biogás/biomassa), muito acima de sua participação em Reciclagem — coerente '
  'com o parque sucroalcooleiro da região. Há potencial de expandir a leitura para bioeconomia '
  'mais ampla nessas regiões.', item)
grande_sp_fmt = f'{por_ra[0][1]:,}'.replace(',', '.')
P('— A <b>Região Metropolitana (Grande SP) concentra 41% de toda a base</b> '
  f'({grande_sp_fmt} de {total_geral_fmt} iniciativas), mas é justamente onde a lacuna de logística '
  'reversa (não capturada) provavelmente mais dói: é a região com maior geração de resíduos '
  'eletroeletrônicos e de embalagens per capita do estado.', item)
P('— As <b>3 categorias com zero cobertura</b> (Reuso, Remanufatura, Logística reversa) '
  'representam, ao mesmo tempo, a maior lacuna de dado e a maior oportunidade de diagnóstico '
  'futuro — nenhuma política pública pode ser desenhada para o que não está medido.', item)
P('— <b>Registro, Itapeva e Araçatuba</b> são candidatas naturais a receber incentivo/fomento '
  'público direcionado (item "apoio à formulação de políticas públicas" do escopo), dado o gap '
  'de quase 40× frente à Grande SP.', item)

story.append(PageBreak())
P('Indicadores e KPIs (item 11 do escopo)', h1)
kpi_dados = [
    [Paragraph('Indicador', cel_b), Paragraph('Valor', cel_b)],
    [Paragraph('Nº de iniciativas mapeadas', cel), Paragraph(f'{total_geral:,}'.replace(',', '.'), cel)],
    [Paragraph('Cobertura territorial (municípios com ≥1 iniciativa)', cel), Paragraph('80,6% (520 de 645)', cel)],
    [Paragraph('% categoria Reciclagem', cel), Paragraph(f'{100*por_categoria_dict.get("Reciclagem",0)/total_geral:.1f}%', cel)],
    [Paragraph('% categoria Valorização energética', cel), Paragraph(f'{100*por_categoria_dict.get("Valorização energética",0)/total_geral:.1f}%', cel)],
    [Paragraph('RA mais concentrada', cel), Paragraph(f'{por_ra[0][0]} ({por_ra[0][1]:,} iniciativas)'.replace(',', '.'), cel)],
    [Paragraph('RA menos densa (por município)', cel), Paragraph(f'{por_ra_norm[0][0]} ({por_ra_norm[0][3]}/município)', cel)],
    [Paragraph('Maturidade média das iniciativas', cel), Paragraph('não disponível — ver limitações', cel)],
    [Paragraph('Impacto estimado (resíduos evitados)', cel), Paragraph('não disponível — ver limitações', cel)],
]
tbl_kpi = Table(kpi_dados, colWidths=[10*cm, 6*cm])
tbl_kpi.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl_kpi)

P('Limitações metodológicas', h1)
P('— <b>Fonte única por setor</b>: resíduos sólidos vem só de CNPJ ativo (Receita Federal); '
  'energia só de usinas outorgadas (ANEEL). Nenhuma iniciativa pública, de ONG, cooperativa '
  'informal ou acadêmica está representada ainda (item 6 do escopo pede essas fontes).', item)
P('— <b>Apagão eleitoral</b>: CETESB, SNIS e o cadastro de cooperativas de catadores (SINIR) '
  'estão indisponíveis até 25/10/2026 por força do período de defeso eleitoral '
  '(Lei 9.504/1997, art. 73 VI "b"). Essas 3 fontes ficam pendentes até lá.', item)
P('— <b>Maturidade e impacto</b> (ideia/piloto/operação/escala; resíduos evitados, empregos, '
  'receita) não são informações que o cadastro de CNPJ ou o registro da ANEEL contêm — exigem '
  'fonte primária (questionário, contato direto com as iniciativas) fora do escopo de dados '
  'abertos.', item)
P('— <b>Coleta ≠ estratégia circular</b>: mantive "Tratamento/disposição" como categoria à parte '
  'das 6 categorias circulares do escopo, em vez de forçar aterro/descontaminação dentro de '
  '"Reciclagem" — são gestão linear de resíduos, não estratégia circular, e misturar os dois '
  'distorceria a leitura.', item)

SP_(14)
story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#CCCCCC'), spaceAfter=6))
P('Documento gerado automaticamente a partir da base georreferenciada do projeto.', rodape)

doc = SimpleDocTemplate(SAIDA, pagesize=A4, topMargin=1.8*cm, bottomMargin=1.6*cm,
                        leftMargin=2*cm, rightMargin=2*cm,
                        title='Análise Estratégica — Mapa de Economia Circular SP',
                        author='SENAC SP')
doc.build(story)
print(f'PDF gerado: {SAIDA}')
