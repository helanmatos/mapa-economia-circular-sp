#!/usr/bin/env python3
"""Gera um PDF de relatório da Entrega 1 do Mapa de Economia Circular (SENAC SP)."""
import duckdb
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)

CSV = 'empresas_sp_circular.csv'
SAIDA = 'relatorio_mapa_economia_circular.pdf'

# Paleta (sustentabilidade / economia circular)
VERDE = colors.HexColor('#1B5E20')
VERDE_MED = colors.HexColor('#2E7D32')
VERDE_CLARO = colors.HexColor('#E8F5E9')
CINZA = colors.HexColor('#555555')

# Descrições oficiais (IBGE/CONCLA) dos CNAEs filtrados
CNAE_DESC = {
    '3811400': ('3811-4/00', 'Coleta de resíduos não-perigosos'),
    '3812200': ('3812-2/00', 'Coleta de resíduos perigosos'),
    '3821100': ('3821-1/00', 'Tratamento e disposição de resíduos não-perigosos'),
    '3822000': ('3822-0/00', 'Tratamento e disposição de resíduos perigosos'),
    '3831901': ('3831-9/01', 'Recuperação de sucatas de alumínio'),
    '3831999': ('3831-9/99', 'Recuperação de materiais metálicos, exceto alumínio'),
    '3832700': ('3832-7/00', 'Recuperação de materiais plásticos'),
    '3839401': ('3839-4/01', 'Usinas de compostagem'),
    '3839499': ('3839-4/99', 'Recuperação de materiais não especificados anteriormente'),
    '3900500': ('3900-5/00', 'Descontaminação e outros serviços de gestão de resíduos'),
}

# ---- números direto do CSV ----
con = duckdb.connect()
t = f"read_csv('{CSV}', header=true, all_varchar=true)"
total = con.sql(f"SELECT count(*) FROM {t}").fetchone()[0]
por_cnae = con.sql(f"SELECT cnae_principal, count(*) n FROM {t} GROUP BY 1").fetchall()
por_cnae = {c: n for c, n in por_cnae}
top_mun = con.sql(f"SELECT municipio, count(*) n FROM {t} GROUP BY 1 ORDER BY 2 DESC LIMIT 10").fetchall()
fill = con.sql(f"""SELECT
  round(100.0*count(nullif(logradouro,''))/count(*),1),
  round(100.0*count(nullif(tel1,''))/count(*),1),
  round(100.0*count(nullif(email,''))/count(*),1),
  round(100.0*count(nullif(nome_fantasia,''))/count(*),1)
  FROM {t}""").fetchone()
n_mun = con.sql(f"SELECT count(DISTINCT municipio) FROM {t}").fetchone()[0]

# ---- estilos ----
ss = getSampleStyleSheet()
h1 = ParagraphStyle('h1', parent=ss['Heading1'], textColor=VERDE, fontSize=14,
                    spaceBefore=14, spaceAfter=6)
titulo = ParagraphStyle('titulo', parent=ss['Title'], textColor=VERDE, fontSize=22, leading=26)
sub = ParagraphStyle('sub', parent=ss['Normal'], textColor=CINZA, fontSize=11,
                     alignment=TA_LEFT, spaceAfter=2)
corpo = ParagraphStyle('corpo', parent=ss['Normal'], fontSize=10.5, leading=15, spaceAfter=6)
item = ParagraphStyle('item', parent=corpo, leftIndent=12, spaceAfter=3)
cel = ParagraphStyle('cel', parent=ss['Normal'], fontSize=9.5, leading=12)
cel_b = ParagraphStyle('cel_b', parent=cel, textColor=colors.white, fontName='Helvetica-Bold')
rodape = ParagraphStyle('rodape', parent=ss['Normal'], fontSize=8, textColor=CINZA, alignment=TA_CENTER)

story = []
def P(txt, st=corpo): story.append(Paragraph(txt, st))
def SP(h=8): story.append(Spacer(1, h))

# ---- cabeçalho ----
P('Mapa de Economia Circular — SENAC SP', titulo)
P('Extração de empresas de resíduos e reciclagem no estado de São Paulo', sub)
P('Entrega 1 — Base de empresas · 30/06/2026', sub)
SP(4)
story.append(HRFlowable(width='100%', thickness=2, color=VERDE_MED, spaceAfter=10))

# ---- objetivo ----
P('Objetivo', h1)
P('Construir a base de empresas que alimenta o Mapa de Economia Circular: '
  'todas as empresas <b>ativas no estado de São Paulo</b> cuja atividade principal (CNAE) '
  'seja de <b>coleta, tratamento, recuperação de resíduos ou reciclagem</b>, com endereço '
  'e município identificados para posterior plotagem no mapa.')

# ---- o que foi feito ----
P('O que foi feito', h1)
P('Os dados foram extraídos diretamente dos <b>Dados Abertos do CNPJ da Receita Federal</b> '
  'e filtrados localmente, sem depender de serviços pagos ou de nuvem. O processo, resumido:')
P('1. Download dos arquivos de Estabelecimentos (10 partes) + tabela de Municípios.', item)
P('2. Filtro por: estado = SP, situação cadastral = <b>Ativa</b>, e CNAE principal '
  'dentro da lista de resíduos/reciclagem.', item)
P('3. Cruzamento do código de município com a tabela oficial para obter o <b>nome da cidade</b>.', item)
P('4. Geração do arquivo final <b>empresas_sp_circular.csv</b>.', item)
P('O processamento foi feito parte por parte (baixar → filtrar → guardar o útil → descartar o bruto), '
  'de forma a não acumular dezenas de GB de arquivos temporários no computador.')

# ---- resultado ----
P('Resultado', h1)
P(f'Foram identificadas <b>{total:,} empresas</b>, distribuídas em <b>{n_mun} municípios</b> '
  'do estado de São Paulo.'.replace(',', '.'))
P('Cada registro traz os seguintes campos:')
P('<b>Identificação:</b> CNPJ, nome fantasia &nbsp;·&nbsp; <b>Atividade:</b> CNAE principal &nbsp;·&nbsp; '
  '<b>Endereço:</b> logradouro, número, complemento, bairro, CEP &nbsp;·&nbsp; '
  '<b>Localização:</b> UF e município &nbsp;·&nbsp; <b>Contato:</b> telefone e e-mail.', item)

# preenchimento
P(f'Cobertura dos campos: endereço <b>{fill[0]}%</b>, telefone <b>{fill[1]}%</b>, '
  f'e-mail <b>{fill[2]}%</b>, nome fantasia <b>{fill[3]}%</b> '
  '(nome fantasia é naturalmente baixo — muitas empresas não registram um).')

# ---- tabela CNAEs ----
P('CNAEs incluídos na busca', h1)
dados = [[Paragraph('CNAE', cel_b), Paragraph('Descrição oficial (IBGE)', cel_b),
          Paragraph('Empresas', cel_b)]]
for cod, (fmt, desc) in CNAE_DESC.items():
    n = por_cnae.get(cod, 0)
    dados.append([Paragraph(f'<b>{fmt}</b>', cel), Paragraph(desc, cel),
                  Paragraph(f'{n:,}'.replace(',', '.'), cel)])
dados.append([Paragraph('<b>Total</b>', cel), Paragraph('', cel),
              Paragraph(f"<b>{total:,}</b>".replace(',', '.'), cel)])
tbl = Table(dados, colWidths=[2.6*cm, 10.4*cm, 2.4*cm])
tbl.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('BACKGROUND', (0, -1), (-1, -1), VERDE_CLARO),
    ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F5F5F5')]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(tbl)

# ---- tabela municípios ----
P('Onde estão (10 maiores concentrações)', h1)
mdata = [[Paragraph('Município', cel_b), Paragraph('Empresas', cel_b)]]
for mun, n in top_mun:
    mdata.append([Paragraph(mun.title(), cel), Paragraph(f'{n:,}'.replace(',', '.'), cel)])
mt = Table(mdata, colWidths=[10*cm, 3*cm])
mt.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), VERDE_MED),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
    ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ('TOPPADDING', (0, 0), (-1, -1), 4),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
]))
story.append(mt)

# ---- decisões ----
P('Decisões metodológicas', h1)
P('—&nbsp;<b>Energia ficou de fora</b> de propósito (CNAEs de geração/distribuição trariam '
  'qualquer usina ou distribuidora e poluiriam a base).', item)
P('—&nbsp;<b>Logística reversa não tem CNAE próprio</b> — é uma função prevista na PNRS, '
  'já coberta pelos códigos do Grupo 38 acima.', item)
P('—&nbsp;O filtro considerou apenas o <b>CNAE principal</b>. É possível estender para quem tem '
  'esses códigos como atividade secundária (amplia a base).', item)

# ---- fonte + próximos passos ----
P('Fonte e próximos passos', h1)
P('<b>Fonte:</b> Dados Abertos do CNPJ da Receita Federal (competência de junho/2026). '
  'Classificação dos CNAEs conforme IBGE/CONCLA.')
P('<b>Próximo passo:</b> geocodificar os endereços (latitude/longitude) para plotar as '
  'empresas no mapa — a base traz endereço, mas ainda não as coordenadas.')

SP(14)
story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#CCCCCC'), spaceAfter=6))
P('Documento gerado automaticamente · acompanha o arquivo empresas_sp_circular.csv', rodape)

doc = SimpleDocTemplate(SAIDA, pagesize=A4, topMargin=1.8*cm, bottomMargin=1.6*cm,
                        leftMargin=2*cm, rightMargin=2*cm,
                        title='Mapa de Economia Circular — SENAC SP',
                        author='Equipe SENAC SP')
doc.build(story)
print(f'PDF gerado: {SAIDA}')
