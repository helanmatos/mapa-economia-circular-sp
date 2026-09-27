#!/usr/bin/env python3
"""Relatório de entrega para o cliente — o que foi feito, em linguagem não técnica.

Diferente do documento técnico completo (processo, pipeline, método), este é o
documento que vai por e-mail para quem encomendou o mapa: o que ele faz, como
usar, o que revela, de onde vêm os dados e o que ainda não é possível.

Todos os números são calculados na hora a partir dos mesmos módulos que geram o
mapa, para o relatório nunca divergir do que está publicado. As capturas de tela
vêm de capturas_documento.py.
"""
import csv
import math
import os
import statistics as st
import tempfile

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

import dados_app
import maturidade as m

# Fontes EMBUTIDAS no PDF. As base-14 (Helvetica) não são embutidas pelo reportlab:
# o leitor precisa ter uma substituta, e há leitores que não têm e mostram a página
# sem texto nenhum. Para um documento que vai por e-mail a terceiros, isso é risco.
_DIR_FONTES = '/System/Library/Fonts/Supplemental'
for _nome, _arq in [('Corpo', 'Arial.ttf'), ('Corpo-Negrito', 'Arial Bold.ttf'),
                    ('Corpo-Italico', 'Arial Italic.ttf'), ('Corpo-NegritoItalico', 'Arial Bold Italic.ttf')]:
    pdfmetrics.registerFont(TTFont(_nome, f'{_DIR_FONTES}/{_arq}'))
# liga <b> e <i> dentro de Paragraph às variantes certas
addMapping('Corpo', 0, 0, 'Corpo')
addMapping('Corpo', 1, 0, 'Corpo-Negrito')
addMapping('Corpo', 0, 1, 'Corpo-Italico')
addMapping('Corpo', 1, 1, 'Corpo-NegritoItalico')

SAIDA = 'relatorio_entrega_mapa_economia_circular.pdf'
DATA = '18/09/2026'
URL_MAPA = 'https://helanmatos.github.io/mapa-economia-circular-sp/'
URL_REPO = 'https://github.com/helanmatos/mapa-economia-circular-sp'
CAPTURAS = 'docs/capturas'

VERDE = colors.HexColor('#1B5E20')
VERDE_MED = colors.HexColor('#2E7D32')
VERDE_CLARO = colors.HexColor('#E8F5E9')
AMBAR_CLARO = colors.HexColor('#FFF8E1')
AMBAR_TXT = colors.HexColor('#7a5c1e')
CINZA = colors.HexColor('#5f6368')
CINZA_CLARO = colors.HexColor('#F4F6F4')
LINHA = colors.HexColor('#D9DED9')

LARGURA_UTIL = A4[0] - 4 * cm


# ---------------------------------------------------------------- números
def milhar(n):
    return f'{n:,}'.replace(',', '.')


def dec(v, casas=1):
    # formatado isolado: nunca encadear .replace numa frase inteira. Troca em duas
    # etapas para o separador de milhar (6,951.3 -> 6.951,3) não colidir com o decimal.
    return f'{v:,.{casas}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


D = dados_app.carrega()
A = D['maturidade']
N_PONTOS = len(D['pontos']['features'])
N_USINAS = sum(1 for f in D['pontos']['features'] if f['properties']['setor'] == 'energia')
N_EMPRESAS_MAPA = N_PONTOS - N_USINAS
N_EMPRESAS_BASE = N_EMPRESAS_MAPA + len(D['sem_coordenada'])
N_SEM_COORD = len(D['sem_coordenada'])
DIST = A['dist_municipal']
EST = A['dist_estagio']
CAM = D['conta_camada']
MAT = D['conta_material']
CIC = D['conta_ciclo']
MW = round(sum(D['mw_ciclo'].values()), 1)
N_APROX = sum(1 for f in D['pontos']['features'] if f['properties'].get('aprox') is True)
CLASSES = A['classes_ra']
RAS_CL1 = sorted([r for r, c in CLASSES.items() if c['classe'] == 1])
RAS_CL2 = [r for r, c in CLASSES.items() if c['classe'] == 2]

_ctx = {r['cod_ibge']: r for r in csv.DictReader(open('contexto_municipios.csv', encoding='utf-8'))}
_L = []
for _f in A['geojson_mun']['features']:
    _c = _ctx.get(_f['properties']['codarea'])
    if _c and _c['idhm'] and _c['populacao']:
        _L.append((float(_c['idhm']), int(_c['populacao']), _f['properties']['nivel']))


def _pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return num / (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5


R_POP = _pearson([math.log10(x[1]) for x in _L], [x[2] for x in _L])
R_IDHM = _pearson([x[0] for x in _L], [x[2] for x in _L])
POP0 = int(st.median([x[1] for x in _L if x[2] == 0]))
POP4 = int(st.median([x[1] for x in _L if x[2] == 4]))
IDHM0 = st.mean([x[0] for x in _L if x[2] == 0])
IDHM4 = st.mean([x[0] for x in _L if x[2] == 4])

_bauru = next(f['properties'] for f in A['geojson_mun']['features']
              if f['properties']['nome'] == 'Bauru')

# ---------------------------------------------------------------- estilos
ss = getSampleStyleSheet()
h1 = ParagraphStyle('h1', parent=ss['Heading1'], fontName='Corpo-Negrito', fontSize=17,
                    leading=21, textColor=VERDE, spaceBefore=4, spaceAfter=10)
h2 = ParagraphStyle('h2', parent=ss['Heading2'], fontName='Corpo-Negrito', fontSize=12.5,
                    leading=16, textColor=VERDE_MED, spaceBefore=12, spaceAfter=5)
corpo = ParagraphStyle('corpo', parent=ss['Normal'], fontName='Corpo', fontSize=10.3,
                       leading=15.2, textColor=colors.HexColor('#222222'), spaceAfter=7)
item = ParagraphStyle('item', parent=corpo, leftIndent=13, firstLineIndent=-9, spaceAfter=4)
legenda = ParagraphStyle('legenda', parent=corpo, fontSize=8.8, leading=12.2, textColor=CINZA,
                         spaceBefore=4, spaceAfter=12)
cel = ParagraphStyle('cel', parent=corpo, fontSize=9.2, leading=12.4, spaceAfter=0)
cel_b = ParagraphStyle('cel_b', parent=cel, fontName='Corpo-Negrito', textColor=colors.white)
cel_ok = ParagraphStyle('cel_ok', parent=cel, fontName='Corpo-Negrito', textColor=VERDE_MED)
cel_parc = ParagraphStyle('cel_parc', parent=cel, fontName='Corpo-Negrito',
                          textColor=colors.HexColor('#B26A00'))
card_num = ParagraphStyle('card_num', parent=corpo, fontName='Corpo-Negrito', fontSize=20,
                          leading=23, textColor=VERDE, alignment=TA_CENTER, spaceAfter=0)
card_rot = ParagraphStyle('card_rot', parent=corpo, fontSize=8.6, leading=11, textColor=CINZA,
                          alignment=TA_CENTER, spaceAfter=0)
caixa = ParagraphStyle('caixa', parent=corpo, backColor=VERDE_CLARO, borderPadding=(9, 11, 9, 11),
                       spaceBefore=6, spaceAfter=12, leading=15.5)
alerta = ParagraphStyle('alerta', parent=corpo, backColor=AMBAR_CLARO, textColor=AMBAR_TXT,
                        borderPadding=(9, 11, 9, 11), spaceBefore=6, spaceAfter=12, fontSize=9.8,
                        leading=14.5)

story = []


def P(txt, estilo=corpo):
    story.append(Paragraph(txt, estilo))


def topico(txt):
    story.append(Paragraph('– ' + txt, item))


def espaco(h=8):
    story.append(Spacer(1, h))


_tmp = tempfile.mkdtemp()


def figura(arquivo, texto_legenda, largura=LARGURA_UTIL):
    """Embute a captura reduzida (a original tem 2800px; 1800 bastam para impressão)."""
    origem = os.path.join(CAPTURAS, arquivo)
    reduzida = os.path.join(_tmp, arquivo)
    im = PILImage.open(origem)
    im.thumbnail((1800, 1800))
    im.save(reduzida, 'JPEG', quality=82, optimize=True)
    w, h = im.size
    img = Image(reduzida, width=largura, height=largura * h / w)
    moldura = Table([[img]], colWidths=[largura])
    moldura.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, LINHA),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([moldura, Paragraph(texto_legenda, legenda)]))


def cards(itens):
    """Linha de números em destaque."""
    n = len(itens)
    celulas = [[Paragraph(num, card_num), Paragraph(rot, card_rot)] for num, rot in itens]
    t = Table([[c for c in celulas]], colWidths=[LARGURA_UTIL / n] * n)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CINZA_CLARO),
        ('LINEBEFORE', (1, 0), (-1, -1), 3, colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t)
    espaco(10)


def tabela(linhas, larguras, destaque_cab=True, zebra=True):
    t = Table(linhas, colWidths=larguras, repeatRows=1)
    estilo = [
        ('GRID', (0, 0), (-1, -1), 0.4, LINHA),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    if destaque_cab:
        estilo.append(('BACKGROUND', (0, 0), (-1, 0), VERDE_MED))
    if zebra:
        estilo.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CINZA_CLARO]))
    t.setStyle(TableStyle(estilo))
    story.append(t)
    espaco(10)


# ================================================================ 1. RESUMO
P('Em resumo', h1)
P(f'O <b>Mapa da Economia Circular do Estado de São Paulo</b> reúne, num único endereço na '
  f'internet, <b>{milhar(N_EMPRESAS_MAPA)} empresas</b> de coleta, triagem, reciclagem, tratamento e '
  f'descontaminação de resíduos e <b>{milhar(N_USINAS)} usinas</b> de energia a partir de biomassa e '
  f'biogás, distribuídas pelos 645 municípios e pelas 16 Regiões Administrativas do estado.')
P('Mais do que localizar empresas, o mapa mede <b>o quanto cada lugar tem da cadeia completa</b> — '
  'coleta, reciclagem, tratamento e orgânicos — e permite enxergar onde ela se fecha, onde se '
  'interrompe e onde simplesmente não existe.')
cards([
    (milhar(N_EMPRESAS_MAPA + N_USINAS), 'estabelecimentos<br/>no mapa'),
    ('645', 'municípios<br/>analisados'),
    ('16', 'Regiões<br/>Administrativas'),
    ('4', 'temas de<br/>leitura'),
])
P(f'<b>Acesse:</b> <link href="{URL_MAPA}" color="#1B5E20"><u>{URL_MAPA}</u></link><br/>'
  'Funciona em qualquer navegador, no computador ou no celular, sem instalação e sem login.', caixa)

P('Os três achados principais', h2)
topico(f'<b>O vazio está dentro das regiões, não entre elas.</b> Todas as 16 regiões têm pelo menos '
       f'três dos quatro serviços em algum ponto do território — mas só {DIST[4]} dos 645 municípios '
       f'têm a cadeia completa, e {DIST[0]} não têm nenhum serviço registrado.')
topico(f'<b>O que prevê a infraestrutura é o tamanho do município, não a renda.</b> A presença de '
       f'serviços acompanha a população muito mais de perto (correlação de {dec(R_POP, 2)}) do que o '
       f'IDH (correlação de {dec(R_IDHM, 2)}). O desafio é de escala.')
topico('<b>Resíduos e energia ocupam geografias opostas.</b> A gestão de resíduos se concentra na '
       'Grande São Paulo; a energia de biomassa, no cinturão canavieiro do interior.')

story.append(PageBreak())

# ================================================================ 2. COMO USAR
P('Como navegar', h1)
P('O mapa é organizado em <b>quatro abas</b> no topo da tela. Cada uma responde a uma pergunta '
  'diferente, e a troca entre elas é instantânea — nada é recarregado, e o mapa mantém o '
  'enquadramento onde você estava.')
tabela([
    [Paragraph('Aba', cel_b), Paragraph('Pergunta que responde', cel_b)],
    [Paragraph('<b>Hub Circular</b>', cel),
     Paragraph('Qual o nível de maturidade de cada região e de cada município?', cel)],
    [Paragraph('<b>Tratamento de resíduos</b>', cel),
     Paragraph('Onde estão as empresas de cada etapa da cadeia de resíduos?', cel)],
    [Paragraph('<b>Ciclo biológico</b>', cel),
     Paragraph('Onde estão a compostagem e a geração de energia a partir de resíduos orgânicos?', cel)],
    [Paragraph('<b>Contexto</b>', cel),
     Paragraph('Como a infraestrutura circular se relaciona com população e desenvolvimento humano?', cel)],
], [4.3 * cm, LARGURA_UTIL - 4.3 * cm])
P('Recursos em todas as abas', h2)
topico('<b>Painel lateral</b> com legenda, filtros e números que se atualizam conforme a seleção. '
       'No celular ele começa recolhido e abre pelo botão no canto.')
topico('<b>Clique em qualquer ponto</b> para ver nome, atividade e endereço do estabelecimento.')
topico('<b>Barra de escala</b> em quilômetros, no canto inferior esquerdo, e <b>indicação do norte</b> '
       'no canto superior direito.')
topico('<b>Mapa de localização</b> abaixo do norte, que mostra sempre o nível geográfico acima do que '
       'está na tela: o Brasil quando você vê o estado, o estado quando vê uma região, a região '
       'quando vê um município.')
topico('<b>Filtro por Região Administrativa</b> e alternância entre pontos e mapa de densidade, nas '
       'abas de Tratamento e Ciclo biológico.')

story.append(PageBreak())

# ================================================================ 3. OS TEMAS
P('1. Hub Circular — maturidade por região', h1)
P('É o mapa estratégico, e a porta de entrada. O estado aparece dividido nas 16 Regiões '
  'Administrativas, coloridas pelo seu nível de maturidade. <b>Clicando numa região, ela se abre '
  'nos seus municípios; clicando num município, aparecem os estabelecimentos um a um.</b> Uma '
  'trilha no painel mostra onde você está e permite voltar a qualquer nível.')
figura('01_hub_estado.jpg',
       'Visão do estado. A cor de cada região é a média dos seus municípios; as listras diagonais '
       'indicam regiões com muitos municípios sem nenhum serviço. No canto superior direito, o '
       'mapa de localização mostra o estado dentro do Brasil.')
P('Duas formas de medir maturidade', h2)
P('O mapa usa duas escalas, e troca entre elas automaticamente conforme o nível de navegação:')
topico('<b>No município</b>, a escada proposta na reunião de 07/09: <b>básico</b> (coleta e '
       'reciclagem), <b>estruturado</b> (mais tratamento) e <b>circular</b> (mais orgânicos). Ela '
       'olha <i>quais</i> serviços existem, não quantos — e por isso separa quem tem a base da '
       'cadeia de quem tem serviços soltos, que o mapa chama de <b>incipiente</b>.')
topico('<b>Na região</b>, a média dos seus municípios, de 0 a 4. Aplicada a uma região inteira, a '
       'escada mediria apenas se o serviço existe "em algum lugar", e esconderia o vazio interno.')
figura('02_hub_regiao.jpg',
       'A 9ª Região de Araçatuba aberta nos seus municípios. Pela escada, a região inteira seria '
       '"circular", porque tem os quatro serviços em algum ponto. Aberta, ela revela municípios '
       'sem nenhum serviço (vermelho) ao lado da sede regional (verde-escuro). É por isso que a '
       'região é medida pela média, e o município pela escada.')
figura('03_hub_municipio.jpg',
       f'O município de Bauru, com cada estabelecimento marcado e colorido pela sua atividade. '
       f'Bauru tem {_bauru["total_iniciativas"]} estabelecimentos de coleta e reciclagem, mas '
       f'nenhum de tratamento ou compostagem com sede no município — por isso aparece como '
       f'"básico". Isso não significa que Bauru não tenha aterro; ver "Limites que é importante '
       f'conhecer".')

story.append(PageBreak())
P('2. Tratamento de resíduos — as cinco etapas', h1)
P('Mostra onde está cada etapa da cadeia de resíduos. As cinco camadas pedidas na reunião podem '
  'ser <b>ligadas e desligadas independentemente e vistas em conjunto</b> — dá para cruzar coleta '
  'com triagem, ou isolar só a descontaminação.')
tabela([
    [Paragraph('Camada', cel_b), Paragraph('Estabelecimentos', cel_b)],
    [Paragraph('Coleta e movimentação', cel), Paragraph(milhar(CAM['coleta']), cel)],
    [Paragraph('Triagem e recuperação', cel), Paragraph(milhar(CAM['triagem']), cel)],
    [Paragraph('Orgânicos (compostagem e usinas)', cel), Paragraph(milhar(CAM['organicos']), cel)],
    [Paragraph('Tratamento e disposição final', cel), Paragraph(milhar(CAM['tratamento']), cel)],
    [Paragraph('Descontaminação', cel), Paragraph(milhar(CAM['descontaminacao']), cel)],
], [LARGURA_UTIL - 4.2 * cm, 4.2 * cm])
P(f'Dentro de <b>triagem e recuperação</b> há o filtro por material recuperado: '
  f'<b>metal</b> ({milhar(MAT["metal"])}), <b>plástico</b> ({milhar(MAT["plastico"])}) e um terceiro '
  f'grupo com papel, vidro, construção civil e outros ({milhar(MAT["outros"])}). O mapa também pode '
  f'colorir os pontos pelas <b>categorias circulares da ISO 59000</b>.')
figura('04_tratamento.jpg',
       'Todas as cinco camadas ligadas. O número de estabelecimentos visíveis no painel acompanha '
       'cada combinação escolhida.')

story.append(PageBreak())
P('3. Ciclo biológico — compostagem, biogás e biomassa', h1)
P(f'Reúne as {milhar(sum(CIC.values()))} unidades do ciclo orgânico: {milhar(CIC["compostagem"])} '
  f'usinas de compostagem, {milhar(CIC["biogas"])} de biogás e {milhar(CIC["biomassa"])} de '
  f'biomassa energética, somando <b>{dec(MW)} MW</b> de potência. O tamanho de cada círculo é '
  f'proporcional à potência da usina, porque uma de 300 MW e uma de 0,5 MW não podem ter o '
  f'mesmo peso visual.')
figura('05_ciclo.jpg',
       'A biomassa (amarelo) se concentra no cinturão canavieiro do interior — quase toda a '
       'potência vem de bagaço de cana. O biogás (verde-azulado) aparece em torno dos aterros '
       'da Grande São Paulo.')

story.append(PageBreak())
P('4. Contexto — população e desenvolvimento humano', h1)
P('Cruza a maturidade circular com a <b>população</b> (IBGE) e o <b>IDH municipal</b> (Atlas do '
  'Desenvolvimento Humano), atendendo ao pedido da reunião de relacionar o vazio circular com '
  'indicadores sociais. Passando o mouse sobre um município, aparecem os dois dados junto com o '
  'estágio da cadeia ali.')
figura('06_contexto.jpg',
       'IDH municipal. O Vale do Ribeira, no sul do estado, concentra os índices mais baixos — '
       'como antecipado na reunião a respeito da região de Registro.')

story.append(PageBreak())

# ================================================================ 4. REUNIÃO
P('O que foi pedido e o que foi entregue', h1)
P('A reunião de produto de 07/09/2026 propôs reorganizar o mapa em três temas, com um cruzamento '
  'socioeconômico. O quadro abaixo mostra a situação de cada pedido.')
tabela([
    [Paragraph('Pedido da reunião', cel_b), Paragraph('Situação', cel_b), Paragraph('Observação', cel_b)],
    [Paragraph('Mapa 1 — Hub Circular por região, com índice de maturidade', cel),
     Paragraph('Entregue', cel_ok),
     Paragraph('Com navegação até o estabelecimento e a escada básico / estruturado / circular', cel)],
    [Paragraph('Mapa 2 — Tratamento de resíduos em cinco camadas', cel),
     Paragraph('Entregue', cel_ok), Paragraph('Coleta, triagem, orgânicos, tratamento, descontaminação', cel)],
    [Paragraph('Camadas combináveis entre si', cel),
     Paragraph('Entregue', cel_ok), Paragraph('Cada camada liga e desliga de forma independente', cel)],
    [Paragraph('Sub-camada de materiais', cel),
     Paragraph('Parcial', cel_parc),
     Paragraph('Metal e plástico separados. Papel, vidro e construção civil ficam juntos — ver limites', cel)],
    [Paragraph('Mapa 3 — Ciclo biológico', cel),
     Paragraph('Entregue', cel_ok), Paragraph('Com o tamanho proporcional à potência de cada usina', cel)],
    [Paragraph('Cruzamento com IDH e população', cel),
     Paragraph('Entregue', cel_ok), Paragraph('Nos 645 municípios, com a análise na próxima seção', cel)],
    [Paragraph('Reduzir a poluição visual dos pontos', cel),
     Paragraph('Entregue', cel_ok),
     Paragraph('A visão inicial é por região; os pontos só aparecem ao descer até o município', cel)],
], [5.6 * cm, 2.2 * cm, LARGURA_UTIL - 7.8 * cm])

# ================================================================ 5. ACHADOS
story.append(PageBreak())
P('O que o mapa revela', h1)
P('O vazio está dentro das regiões', h2)
P(f'Olhando região por região, o estado parece bem servido: todas as 16 têm pelo menos três dos '
  f'quatro serviços em algum ponto do seu território. Descendo ao município, o quadro muda. '
  f'Apenas <b>{DIST[4]} municípios</b> têm a cadeia completa, e <b>{DIST[0]}</b> não têm nenhum dos '
  f'quatro serviços registrados. Pela escada: {EST["circular"]} circulares, {EST["estruturado"]} '
  f'estruturados, {EST["basico"]} básicos, <b>{EST["incipiente"]} incipientes</b> — que têm algum '
  f'serviço mas não fecham nem coleta e reciclagem — e {EST["sem"]} sem infraestrutura.')
P('A infraestrutura existe; o que falta é <b>distância curta até ela</b>. Isso muda o tipo de '
  'política que faz sentido.')

P('O desafio é de escala, não de renda', h2)
P(f'A hipótese levantada na reunião era que o vazio circular acompanharia o IDH baixo. Os dados '
  f'confirmam a direção, mas não a força. A população mediana salta de <b>{milhar(POP0)}</b> '
  f'habitantes nos municípios sem nenhum serviço para <b>{milhar(POP4)}</b> nos que têm os quatro, '
  f'enquanto o IDH médio mal se move ({dec(IDHM0, 3)} contra {dec(IDHM4, 3)}).')
P('Na prática: um município de 4 mil habitantes não sustenta sozinho um aterro licenciado ou uma '
  'usina de triagem, por mais que tenha renda. Somado ao achado anterior, isso aponta para '
  '<b>consórcios intermunicipais, transbordo e escala compartilhada</b> como o caminho mais '
  'promissor — mais do que instalar estrutura nova em cada município.', caixa)

P('Resíduos e energia em geografias opostas', h2)
P('A gestão de resíduos se concentra na Grande São Paulo e no eixo Campinas–Sorocaba, seguindo '
  'a urbanização. A energia de biomassa se concentra no interior agrícola. Nenhuma política única '
  'serve igualmente bem aos dois padrões.')

story.append(PageBreak())

# ================================================================ 6. DADOS
P('De onde vêm os dados', h1)
tabela([
    [Paragraph('Fonte', cel_b), Paragraph('O que fornece', cel_b), Paragraph('Referência', cel_b)],
    [Paragraph('Receita Federal — Dados Abertos do CNPJ', cel),
     Paragraph('Empresas ativas de resíduos em SP, por atividade econômica (CNAE)', cel),
     Paragraph('junho/2026', cel)],
    [Paragraph('ANEEL — Sistema de Informações de Geração', cel),
     Paragraph('Usinas de biogás e biomassa em operação, com localização oficial', cel),
     Paragraph('julho/2026', cel)],
    [Paragraph('IBGE', cel),
     Paragraph('Limites dos municípios e estimativa de população', cel), Paragraph('2026', cel)],
    [Paragraph('Atlas do Desenvolvimento Humano (via Ipeadata)', cel),
     Paragraph('IDH municipal', cel), Paragraph('2010', cel)],
], [5.3 * cm, LARGURA_UTIL - 7.9 * cm, 2.6 * cm])
P('Qualidade da localização', h2)
P(f'Dos {milhar(N_EMPRESAS_BASE)} estabelecimentos da base, <b>{milhar(N_EMPRESAS_MAPA)} estão '
  f'posicionados no mapa</b>; os {N_SEM_COORD} restantes não puderam ser localizados em nenhuma fonte.')
P('Chegar a esse resultado exigiu duas etapas. A primeira localizou os endereços pelo '
  'OpenStreetMap, que mapeia mal as ruas de cidades pequenas — e cerca de 17% ficaram sem '
  'localização, concentrados justamente no interior. A segunda localizou esses endereços pelo '
  'CEP, e <b>cada coordenada foi conferida contra o limite do município declarado</b>, descartando '
  'as que caíam fora dele.')
P(f'Os {milhar(N_APROX)} pontos localizados pelo CEP têm <b>precisão de rua, não de número</b>. '
  'Para a leitura do mapa isso não faz diferença; para conferir um endereço específico, sim. '
  'Esses pontos aparecem marcados como aproximados ao clicar.')

# ================================================================ 7. LIMITES
P('Limites que é importante conhecer', h1)
P('Estes limites vêm das fontes de dados disponíveis, não da construção do mapa. Conhecê-los evita '
  'leituras equivocadas — especialmente em apresentações públicas.', alerta)
P('O mapa mostra onde a empresa tem sede, não onde o serviço é prestado', h2)
P('A base é o cadastro de empresas da Receita Federal. Um município aparece sem tratamento de '
  'resíduos quando nenhuma empresa desse tipo tem <b>sede</b> nele — o que não quer dizer que ele '
  'não seja atendido. É o caso de <b>Bauru</b>: aparece como "básico" porque nenhuma empresa de '
  'tratamento ou compostagem está registrada lá, mas o aterro pode ser operado pela prefeitura ou '
  'por uma empresa de outra cidade. Da mesma forma, serviços públicos e informais não aparecem.')
P('Três das seis categorias circulares não existem no cadastro', h2)
P('<b>Reuso, remanufatura e logística reversa</b> não têm atividade econômica própria na Receita '
  'Federal: são exercidas por empresas registradas em outras atividades. Por isso aparecem com zero '
  'no mapa. A ausência é da fonte, não da realidade.')
P('Papel, vidro e construção civil não se separam', h2)
P('Só metal e plástico têm código de atividade próprio. Os demais materiais caem num código '
  'genérico e não podem ser distinguidos por esta fonte.')
P('O IDH municipal mais recente é de 2010', h2)
P('Não por escolha: é o dado municipal mais recente que existe. Depois do Censo 2010, o índice '
  'passou a ser calculado com uma pesquisa que só tem representatividade estadual, e a versão com '
  'o Censo 2022 ainda não foi publicada.')
P('Fontes do governo estadual temporariamente indisponíveis', h2)
P('CETESB, SNIS e o cadastro de cooperativas de catadores estão fora do ar até <b>25/10/2026</b>, '
  'por força do período eleitoral, que restringe a publicação em sites institucionais. São '
  'justamente as fontes que permitiriam incluir serviços públicos, cooperativas e separar os '
  'materiais.')

# ================================================================ 8. PRÓXIMOS
P('Próximos passos sugeridos', h1)
topico('<b>Após 25/10/2026</b>, integrar a CETESB (que pode separar os materiais recicláveis), o SNIS '
       '(serviços públicos de limpeza urbana) e o cadastro de cooperativas de catadores — o que '
       'reduziria diretamente o limite "sede não é serviço prestado".')
topico('<b>Levar o achado de escala para a discussão de política</b>: se o desafio é escala e não '
       'renda, os consórcios intermunicipais passam a ser o eixo da recomendação.')
topico('<b>Coleta primária</b>, por questionário, para o que nenhuma fonte pública contém: tipo de '
       'organização, porte, estágio de maturidade de cada iniciativa e impacto.')
espaco(14)
P(f'O código, os dados e o documento técnico completo — com o detalhamento de método, fontes e '
  f'decisões — estão disponíveis em <link href="{URL_REPO}" color="#1B5E20"><u>{URL_REPO}</u></link>.',
  ParagraphStyle('rod', parent=corpo, fontSize=9, textColor=CINZA))


# ---------------------------------------------------------------- capa e rodapé
def capa(canvas, doc):
    w, h = A4
    canvas.saveState()
    canvas.setFillColor(VERDE)
    canvas.rect(0, h - 11.5 * cm, w, 11.5 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor('#8BC34A'))
    canvas.rect(0, h - 11.5 * cm, w, 0.28 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont('Corpo', 11)
    canvas.drawString(2 * cm, h - 3 * cm, 'Revolução Circular  ·  Geração 2027  ·  SENAC SP')
    canvas.setFont('Corpo-Negrito', 30)
    canvas.drawString(2 * cm, h - 5.4 * cm, 'Mapa da Economia Circular')
    canvas.setFont('Corpo', 20)
    canvas.drawString(2 * cm, h - 6.5 * cm, 'do Estado de São Paulo')
    canvas.setFont('Corpo', 12.5)
    canvas.drawString(2 * cm, h - 8.6 * cm, 'Relatório de entrega')
    canvas.setFont('Corpo', 10.5)
    canvas.drawString(2 * cm, h - 9.4 * cm, DATA)
    # captura do mapa ocupando a metade inferior da capa, recortada no quadro
    img = PILImage.open(os.path.join(CAPTURAS, '01_hub_estado.jpg'))
    img.thumbnail((1800, 1800))
    capa_img = os.path.join(_tmp, 'capa.jpg')
    img.save(capa_img, 'JPEG', quality=84, optimize=True)
    iw, ih = img.size
    larg = w - 4 * cm
    alt = larg * ih / iw
    # centraliza verticalmente entre a faixa verde e a linha do endereço no rodapé
    topo_livre = h - 11.5 * cm - 1.0 * cm
    fundo_livre = 2.6 * cm
    base = (topo_livre + fundo_livre) / 2 - alt / 2
    canvas.setStrokeColor(LINHA)
    canvas.setLineWidth(0.6)
    canvas.drawImage(capa_img, 2 * cm, base, width=larg, height=alt)
    canvas.rect(2 * cm, base, larg, alt, stroke=1, fill=0)
    canvas.setFillColor(CINZA)
    canvas.setFont('Corpo', 9)
    canvas.drawString(2 * cm, 1.9 * cm, 'Acesse: ' + URL_MAPA)
    canvas.restoreState()


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINHA)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 1.45 * cm, A4[0] - 2 * cm, 1.45 * cm)
    canvas.setFont('Corpo', 8)
    canvas.setFillColor(CINZA)
    canvas.drawString(2 * cm, 1.05 * cm, 'Mapa da Economia Circular do Estado de São Paulo  ·  SENAC SP')
    canvas.drawRightString(A4[0] - 2 * cm, 1.05 * cm, f'{doc.page}')
    canvas.restoreState()


# a capa ocupa a primeira página inteira; o conteúdo começa na segunda
story.insert(0, PageBreak())
story.insert(0, Spacer(1, 1))

# checagem de encoding ANTES de gerar: fonte base-14 só tem cp1252, e fora disso o
# caractere vira outro glifo em silêncio (seta vira "fi", emoji vira "n")
_ruins = set()
for fl in story:
    if isinstance(fl, Paragraph):
        for ch in fl.text:
            try:
                ch.encode('cp1252')
            except UnicodeEncodeError:
                _ruins.add(ch)
if _ruins:
    raise SystemExit(f'caracteres fora de cp1252 no texto: {sorted(_ruins)}')

doc = SimpleDocTemplate(SAIDA, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                        topMargin=1.9 * cm, bottomMargin=2 * cm,
                        title='Mapa da Economia Circular do Estado de São Paulo — Relatório de entrega',
                        author='Helan Matos', subject='SENAC SP · Revolução Circular')
doc.build(story, onFirstPage=capa, onLaterPages=rodape)
print(f'-> {SAIDA} ({os.path.getsize(SAIDA) / 1024 / 1024:.2f} MB)')
