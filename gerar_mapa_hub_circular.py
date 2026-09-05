#!/usr/bin/env python3
"""
Mapa 1 — "Hub Circular" com drill-down em 3 níveis (proposta da Mayara + refinamento
do Helan, reunião de 07/09/2026 e follow-up):

  Estado (16 Regiões Administrativas, coloridas por maturidade)
    -> clica numa RA -> Região expandida (municípios da RA, coloridos por maturidade)
      -> clica num município -> Município expandido (pins de cada empresa)

Índice de maturidade (4 elementos, presença/ausência), calculado tanto por RA quanto
por município:
  Coleta -> Reciclagem/Recuperação -> Tratamento/Disposição -> Orgânicos (compostagem + energia)
  Nível 4 Circular completo / 3 Quase completo / 2 Intermediário / 1 Básico / 0 Sem infraestrutura

Requer:
  geo_cache/regioes_administrativas.geojson       (16 poligonos de RA, ver preparo anterior)
  geo_cache/municipios_sp_malha_com_ra.json        (645 poligonos de municipio + nome + RA)
"""
import re
import json
import duckdb

GEOJSON_RA = 'geo_cache/regioes_administrativas.geojson'
GEOJSON_MUN = 'geo_cache/municipios_sp_malha_com_ra.json'
SAIDA = 'mapa_hub_circular.html'

ELEMENTOS = {
    'coleta': ('3811400', '3812200'),
    'reciclagem': ('3831901', '3831999', '3832700', '3839499'),
    'tratamento_disposicao': ('3821100', '3822000', '3900500'),
    'organicos_cnpj': ('3839401',),
}
CNAE_DESC = {
    '3811400': 'Coleta de resíduos não-perigosos', '3812200': 'Coleta de resíduos perigosos',
    '3821100': 'Tratamento/disposição não-perigosos', '3822000': 'Tratamento/disposição perigosos',
    '3831901': 'Recuperação de sucata de alumínio', '3831999': 'Recuperação de sucata metálica',
    '3832700': 'Recuperação de materiais plásticos', '3839401': 'Usinas de compostagem',
    '3839499': 'Recuperação de materiais (outros)', '3900500': 'Descontaminação',
}
# paleta das classes 0..4 — escolhida para sobreviver a impressao em preto-e-branco
# (luminancia crescente) e a deuteranopia (o par laranja/verde-claro nao colide)
PALETA = ['#B00020', '#E65100', '#F5C518', '#8BC34A', '#1B5E20']
NIVEL_INFO = {
    4: ('Circular completo (4 de 4 serviços)', PALETA[4]),
    3: ('Quase completo (3 de 4 serviços)', PALETA[3]),
    2: ('Intermediário (2 de 4 serviços)', PALETA[2]),
    1: ('Básico (1 de 4 serviços)', PALETA[1]),
    0: ('Sem infraestrutura mapeada', PALETA[0]),
}
ATIVIDADE_COR = {
    '3811400': '#4E79A7', '3812200': '#F28E2B', '3821100': '#E15759', '3822000': '#76B7B2',
    '3831901': '#59A14F', '3831999': '#EDC948', '3832700': '#B07AA1', '3839401': '#FF9DA7',
    '3839499': '#9C755F', '3900500': '#BAB0AC', 'biomassa': '#1D3557', 'biogas': '#2A9D8F',
}

con = duckdb.connect()
t_res = "read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true)"
t_en = "read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true)"


def calcula_nivel(coleta, reciclagem, tratamento, organicos):
    return sum([coleta > 0, reciclagem > 0, tratamento > 0, organicos > 0])


def pinta(niveis):
    """Define a cor de uma unidade (RA ou municipio) a partir dos niveis dos municipios dela.

    A MESMA funcao pinta os dois casos: um municipio e simplesmente o caso N=1.

    A classe e a media municipal arredondada (cortes em 0,5 / 1,5 / 2,5 / 3,5) e sofre uma
    TRAVA DE LACUNA: quanto maior a fatia de municipios sem nenhum registro, mais baixo o
    teto da classe. A trava so rebaixa, nunca promove.

    E isso que corrige o problema apontado: antes a RA era pintada pela presenca do servico
    "em algum lugar da regiao", entao a 8a Sao Jose do Rio Preto aparecia verde-escuro com
    40,6% dos seus municipios zerados, acima da 2a Santos, que nao tem nenhum municipio
    zerado. Com a media + trava, Santos (media 2,11) fica classe 2 e Rio Preto
    (media 1,10, 40,6% vazios) fica classe 1 e ainda ganha hachura forte.
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
        'classe_desc': NIVEL_INFO[classe][0],
        'media': round(media, 2),
        'pct_vazio': round(pct_vazio * 100, 1),
        'n_mun': n,
        'n_vazios': sum(1 for v in niveis if v == 0),
        'dist': [sum(1 for v in niveis if v == k) for k in range(5)],
        'listras': listras,
        'travada': classe < classe_base,
    }


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


# ---------- base: nivel de maturidade de CADA MUNICIPIO ----------
# calculado antes das RAs de proposito: a cor da RA e agregada a partir dos municipios dela,
# nunca de presenca "em algum lugar da regiao" (que fazia RA com 40% de municipios zerados
# aparecer como 'circular completo').
import sys
sys.path.insert(0, '.')
from enriquece import normaliza

_mun_rows = con.sql(f"""
    SELECT municipio,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['coleta']} THEN 1 ELSE 0 END) coleta,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['reciclagem']} THEN 1 ELSE 0 END) reciclagem,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['tratamento_disposicao']} THEN 1 ELSE 0 END) tratamento,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['organicos_cnpj']} THEN 1 ELSE 0 END) organicos_compost,
      count(*) total_residuos
    FROM {t_res} WHERE latitude != '' GROUP BY 1
""").fetchall()
dados_mun = {r[0]: dict(zip(['coleta', 'reciclagem', 'tratamento', 'organicos_compost', 'total_residuos'], r[1:])) for r in _mun_rows}
energia_por_mun = dict(con.sql(f"SELECT upper(municipio), count(*) FROM {t_en} GROUP BY 1").fetchall())

geojson_mun = json.load(open(GEOJSON_MUN, encoding='utf-8'))
niveis_por_ra = {}
for feat in geojson_mun['features']:
    nome_norm = normaliza(feat['properties']['nome'])
    d = dados_mun.get(nome_norm, {'coleta': 0, 'reciclagem': 0, 'tratamento': 0, 'organicos_compost': 0, 'total_residuos': 0})
    n_energia = energia_por_mun.get(nome_norm, 0)
    organicos = d['organicos_compost'] + n_energia
    nivel = calcula_nivel(d['coleta'], d['reciclagem'], d['tratamento'], organicos)
    feat['properties'].update({
        'nivel': nivel,
        'coleta': d['coleta'], 'reciclagem': d['reciclagem'], 'tratamento': d['tratamento'],
        'organicos': organicos, 'total_iniciativas': d['total_residuos'] + n_energia,
        'faltando': elementos_faltando(d['coleta'], d['reciclagem'], d['tratamento'], organicos),
        'municipio_norm': nome_norm,
        **pinta([nivel]),  # municipio = caso N=1 da mesma regra de cor da RA
    })
    niveis_por_ra.setdefault(feat['properties']['regiao_administrativa'], []).append(nivel)


# ---------- nivel 1: Regioes Administrativas ----------
por_elemento_ra = con.sql(f"""
    SELECT regiao_administrativa,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['coleta']} THEN 1 ELSE 0 END) coleta,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['reciclagem']} THEN 1 ELSE 0 END) reciclagem,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['tratamento_disposicao']} THEN 1 ELSE 0 END) tratamento,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['organicos_cnpj']} THEN 1 ELSE 0 END) organicos_compost,
      count(*) total_residuos
    FROM {t_res} WHERE latitude != '' AND regiao_administrativa != '' GROUP BY 1
""").fetchall()
dados_ra = {r[0]: dict(zip(['coleta', 'reciclagem', 'tratamento', 'organicos_compost', 'total_residuos'], r[1:])) for r in por_elemento_ra}
energia_por_ra = dict(con.sql(f"SELECT regiao_administrativa, count(*) FROM {t_en} WHERE regiao_administrativa != '' GROUP BY 1").fetchall())
n_municipios_ra = dict(con.sql("SELECT regiao_administrativa, count(*) FROM read_csv('municipios_regiao_administrativa.csv', header=true) GROUP BY 1").fetchall())

geojson_ra = json.load(open(GEOJSON_RA, encoding='utf-8'))
for feat in geojson_ra['features']:
    ra = feat['properties']['regiao_administrativa']
    d = dados_ra.get(ra, {'coleta': 0, 'reciclagem': 0, 'tratamento': 0, 'organicos_compost': 0, 'total_residuos': 0})
    n_energia = energia_por_ra.get(ra, 0)
    organicos = d['organicos_compost'] + n_energia
    # a cor da RA vem dos municipios dela (media + trava de lacuna), NAO da presenca
    # do servico "em algum lugar da regiao" — ver docstring de pinta()
    cor_ra = pinta(niveis_por_ra.get(ra, [0]))
    total_iniciativas = d['total_residuos'] + n_energia
    feat['properties'].update({
        'coleta': d['coleta'], 'reciclagem': d['reciclagem'], 'tratamento': d['tratamento'],
        'organicos': organicos, 'total_iniciativas': total_iniciativas,
        'densidade': round(total_iniciativas / cor_ra['n_mun'], 1),
        'faltando': elementos_faltando(d['coleta'], d['reciclagem'], d['tratamento'], organicos),
        **cor_ra,
    })

# ---------- nivel 3: pontos (empresas + energia) ----------
rows_res = con.sql(f"""
    SELECT cnpj, nome_fantasia, cnae_principal, tipo_logradouro, logradouro, numero,
           bairro, municipio, latitude, longitude, geocode_status, regiao_administrativa
    FROM {t_res} WHERE latitude != '' AND longitude != ''
""").fetchall()
cols_res = ['cnpj', 'nome_fantasia', 'cnae_principal', 'tipo_logradouro', 'logradouro', 'numero',
            'bairro', 'municipio', 'latitude', 'longitude', 'geocode_status', 'regiao_administrativa']
rows_en = con.sql(f"""
    SELECT nome, categoria_energia, combustivel_detalhe, municipio, latitude, longitude,
           potencia_outorgada_kw, proprietario, regiao_administrativa
    FROM {t_en}
""").fetchall()
cols_en = ['nome', 'categoria_energia', 'combustivel_detalhe', 'municipio', 'latitude', 'longitude',
           'potencia_outorgada_kw', 'proprietario', 'regiao_administrativa']

pontos_features = []
for r in rows_res:
    d = dict(zip(cols_res, r))
    nome = d['nome_fantasia'] or '(sem nome fantasia)'
    endereco = f"{d['tipo_logradouro']} {d['logradouro']}, {d['numero']} - {d['bairro']}, {d['municipio']}"
    pontos_features.append({
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [float(d['longitude']), float(d['latitude'])]},
        'properties': {
            'setor': 'residuos', 'categoria': d['cnae_principal'], 'nome': nome, 'endereco': endereco,
            'aprox': d['geocode_status'] == 'cep_aproximado', 'ra': d['regiao_administrativa'] or '',
            'municipio_norm': normaliza(d['municipio']),
        },
    })
for r in rows_en:
    d = dict(zip(cols_en, r))
    cat = 'biogas' if d['categoria_energia'] == 'Biogás' else 'biomassa'
    mw = round(float(d['potencia_outorgada_kw']) / 1000, 1)
    pontos_features.append({
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [float(d['longitude']), float(d['latitude'])]},
        'properties': {
            'setor': 'energia', 'categoria': cat, 'nome': d['nome'],
            'combustivel': d['combustivel_detalhe'], 'municipio': d['municipio'],
            'potencia_mw': mw, 'proprietario': d['proprietario'] or '', 'ra': d['regiao_administrativa'] or '',
            'municipio_norm': normaliza(d['municipio']),
        },
    })
geojson_pontos = {'type': 'FeatureCollection', 'features': pontos_features}

print(f"RAs: {len(geojson_ra['features'])} | Municipios: {len(geojson_mun['features'])} | Pontos: {len(pontos_features)}")

match_nivel = ['match', ['get', 'classe']]
for nivel, (desc, cor) in NIVEL_INFO.items():
    match_nivel += [nivel, cor]
match_nivel.append('#999999')

dist_estado = [0] * 5
for niveis in niveis_por_ra.values():
    for v in niveis:
        dist_estado[v] += 1
print('Municipios por nivel 0..4:', dist_estado)
print('Classe das RAs:', sorted(
    ((f['properties']['classe'], f['properties']['listras'], round(f['properties']['media'], 2),
      f['properties']['pct_vazio'], f['properties']['regiao_administrativa'])
     for f in geojson_ra['features']), reverse=True))

match_ativ = ['match', ['get', 'categoria']]
for cod, cor in ATIVIDADE_COR.items():
    match_ativ += [cod, cor]
match_ativ.append('#999999')

legenda_html = ''.join(f'''
<div class="legenda-item">
  <span class="swatch" style="background:{cor}"></span>
  <span class="desc"><b>{nivel}</b> · {desc}</span>
</div>''' for nivel, (desc, cor) in sorted(NIVEL_INFO.items(), reverse=True))

legenda_cobertura = '''
<div class="legenda-item">
  <span class="swatch hach-liso"></span>
  <span class="desc">Menos de 15% dos municípios sem registro</span>
</div>
<div class="legenda-item">
  <span class="swatch hach-leve"></span>
  <span class="desc">15% a 30% sem registro — classe limitada a 2</span>
</div>
<div class="legenda-item">
  <span class="swatch hach-forte"></span>
  <span class="desc">30% ou mais sem registro — classe limitada a 1 (ou 0 acima de 50%)</span>
</div>'''

html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Hub Circular por Região Administrativa — SENAC SP</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; height: 100%; font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }}
  #map {{ position: absolute; inset: 0; }}
  #painel {{
    position: absolute; top: 16px; left: 16px; z-index: 1;
    background: rgba(255,255,255,0.97); border-radius: 12px; padding: 16px 18px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15); width: 320px; max-height: calc(100% - 32px);
    overflow-y: auto;
  }}
  #painel h1 {{ font-size: 16px; margin: 0 0 2px; color: #1B5E20; }}
  #painel .sub {{ font-size: 12px; color: #666; margin: 0 0 10px; }}
  .painel-header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }}
  #toggle-painel {{
    display: none; background: none; border: 1px solid #ccc; border-radius: 6px;
    width: 30px; height: 30px; font-size: 15px; line-height: 1; cursor: pointer;
    color: #1B5E20; flex-shrink: 0;
  }}
  @media (max-width: 720px) {{
    #toggle-painel {{ display: block; }}
    #painel.recolhido {{ padding: 10px 14px; width: auto; max-width: calc(100% - 32px); }}
    #painel.recolhido .sub {{ margin-bottom: 0; }}
    #painel.recolhido #painel-conteudo {{ display: none; }}
  }}
  #btn-voltar {{
    display: none; width: 100%; margin-bottom: 10px; padding: 8px 10px; font-size: 12.5px;
    border: 1px solid #1B5E20; border-radius: 6px; background: #E8F5E9; color: #1B5E20;
    cursor: pointer; font-weight: 700; text-align: left;
  }}
  #btn-voltar:hover {{ background: #C8E6C9; }}
  #breadcrumb {{ display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-bottom: 12px; font-size: 12.5px; }}
  #breadcrumb .crumb {{ color: #1B5E20; cursor: pointer; text-decoration: underline; }}
  #breadcrumb .crumb.atual {{ color: #333; font-weight: 700; text-decoration: none; cursor: default; }}
  #breadcrumb .sep {{ color: #aaa; }}
  .setor-titulo {{
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em;
    color: #888; margin: 14px 0 6px; padding-top: 8px; border-top: 1px solid #eee;
  }}
  .setor-titulo:first-of-type {{ margin-top: 0; padding-top: 0; border-top: none; }}
  .legenda-item {{ display: flex; align-items: center; gap: 8px; padding: 4px 2px; font-size: 12px; }}
  .swatch {{ width: 13px; height: 13px; border-radius: 3px; flex-shrink: 0; }}
  .swatch.hach-liso {{ background: #8a8a8a; }}
  .swatch.hach-leve {{ background: repeating-linear-gradient(-45deg, #8a8a8a 0 4px, #ffffff 4px 5.5px); }}
  .swatch.hach-forte {{ background: repeating-linear-gradient(-45deg, #8a8a8a 0 2px, #ffffff 2px 3.5px); }}
  .desc {{ color: #333; }}
  .barra {{ display: flex; height: 9px; border-radius: 4px; overflow: hidden; margin: 8px 0 5px; background: #eee; }}
  .barra span {{ display: block; }}
  .popup-cobertura {{ font-size: 11px; color: #555; margin: 0 0 8px; }}
  .popup-cobertura b {{ color: #B00020; }}
  .aviso {{ font-size: 11px; color: #666; background: #FFF8E1; border-radius: 6px; padding: 8px 10px; margin-top: 12px; line-height: 1.4; }}
  .vazio {{ font-size: 12.5px; color: #C62828; background: #FFEBEE; border-radius: 6px; padding: 10px 12px; margin-top: 8px; line-height: 1.4; }}
  .nav-link {{ display: block; text-align: center; font-size: 11.5px; margin-top: 10px; padding: 7px; border: 1px solid #ccc; border-radius: 6px; color: #1B5E20; text-decoration: none; }}
  .nav-link:hover {{ background: #f0f0f0; }}
  .maplibregl-popup-content {{ font-family: inherit; font-size: 12.5px; padding: 12px 14px; }}
  .popup-nome {{ font-weight: 700; margin: 0 0 2px; font-size: 14px; }}
  .popup-sub {{ font-size: 11px; color: #888; margin: 0 0 4px; }}
  .popup-nivel {{ font-size: 12px; margin: 0 0 8px; font-weight: 700; }}
  .popup-tabela {{ width: 100%; border-collapse: collapse; }}
  .popup-tabela td {{ padding: 2px 0; border-bottom: 1px solid #eee; }}
  .popup-tabela td:last-child {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .popup-faltando {{ color: #C62828; font-size: 11px; margin-top: 8px; }}
  .popup-cnae {{ color: #1B5E20; font-size: 11.5px; margin: 0 0 4px; }}
  .popup-end {{ color: #555; font-size: 12px; margin: 0; }}
  .popup-aprox {{ color: #b26a00; font-size: 10.5px; margin-top: 4px; }}
  .dica {{ font-size: 11px; color: #888; margin-top: 6px; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="painel">
  <div class="painel-header">
    <div>
      <h1>Hub Circular</h1>
      <p class="sub">Estado → Região Administrativa → Município → empresas</p>
    </div>
    <button id="toggle-painel" title="Recolher/expandir menu">✕</button>
  </div>
  <div id="painel-conteudo">
    <button id="btn-voltar">← Voltar</button>
    <div id="breadcrumb"></div>
    <div id="legenda-niveis">
      <div class="setor-titulo">Nível de maturidade</div>
      {legenda_html}
      <div class="setor-titulo">Cobertura (hachura)</div>
      {legenda_cobertura}
      <p class="dica">Clique numa região para ver os municípios; clique num município para ver as empresas.</p>
    </div>
    <div id="area-vazia" style="display:none"></div>
    <div class="aviso">
      O <b>nível do município</b> conta quantos dos 4 serviços ele tem: Coleta, Reciclagem,
      Tratamento/Disposição e Orgânicos (compostagem + usinas de biogás/biomassa).
      A <b>classe da região</b> é a média dos seus municípios, arredondada — e é rebaixada
      quando muitos municípios da região não têm nenhum registro (a hachura mostra o quanto).
    </div>
    <a class="nav-link" href="mapa_economia_circular.html">Ver mapa de pontos (estado todo) →</a>
    <a class="nav-link" href="mapa_calor.html">Ver mapa de calor →</a>
  </div>
</div>
<script>
const geojsonRA = {json.dumps(geojson_ra, ensure_ascii=False)};
const geojsonMun = {json.dumps(geojson_mun, ensure_ascii=False)};
const geojsonPontos = {json.dumps(geojson_pontos, ensure_ascii=False)};
const matchNivel = {json.dumps(match_nivel)};
const matchAtividade = {json.dumps(match_ativ)};
const PALETA = {json.dumps(PALETA)};

const map = new maplibregl.Map({{
  container: 'map',
  style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  center: [-48.5, -22.2],
  zoom: 6,
}});
map.addControl(new maplibregl.NavigationControl(), 'top-right');

const painelEl = document.getElementById('painel');
const btnTogglePainel = document.getElementById('toggle-painel');
function atualizarBotaoPainel() {{
  btnTogglePainel.textContent = painelEl.classList.contains('recolhido') ? '☰' : '✕';
}}
btnTogglePainel.addEventListener('click', () => {{
  painelEl.classList.toggle('recolhido');
  atualizarBotaoPainel();
}});
if (window.matchMedia('(max-width: 720px)').matches) painelEl.classList.add('recolhido');
atualizarBotaoPainel();

document.getElementById('btn-voltar').addEventListener('click', () => {{
  if (nivelAtual === 'municipio') irParaRegiao(raSelecionada);
  else if (nivelAtual === 'regiao') irParaEstado();
}});

let nivelAtual = 'estado'; // 'estado' | 'regiao' | 'municipio'
let raSelecionada = null;
let municipioSelecionado = null;

function limitesDaFeature(feat) {{
  // percorre recursivamente as coordenadas (Polygon/MultiPolygon, qualquer aninhamento).
  // NAO usar regex sobre o JSON: quebra quando alguma coordenada nao tem decimal.
  const bounds = new maplibregl.LngLatBounds();
  (function percorre(coords) {{
    if (typeof coords[0] === 'number') {{ bounds.extend(coords); return; }}
    coords.forEach(percorre);
  }})(feat.geometry.coordinates);
  return bounds;
}}

function enquadrarEstado() {{
  map.resize();
  const bounds = new maplibregl.LngLatBounds();
  geojsonRA.features.forEach(f => bounds.extend(limitesDaFeature(f)));
  map.fitBounds(bounds, {{ padding: 40, maxZoom: 9, duration: 0 }});
}}

function atualizarBotaoVoltar() {{
  const btn = document.getElementById('btn-voltar');
  if (nivelAtual === 'estado') {{
    btn.style.display = 'none';
  }} else {{
    btn.style.display = 'block';
    btn.textContent = nivelAtual === 'municipio'
      ? `← Voltar para ${{raSelecionada}}`
      : '← Voltar para o estado';
  }}
}}

function atualizarBreadcrumb() {{
  atualizarBotaoVoltar();
  const el = document.getElementById('breadcrumb');
  let html = nivelAtual === 'estado'
    ? '<span class="crumb atual">Estado de SP</span>'
    : '<span class="crumb" data-ir="estado">Estado de SP</span>';
  if (raSelecionada) {{
    html += ' <span class="sep">›</span> ';
    html += nivelAtual === 'regiao'
      ? `<span class="crumb atual">${{raSelecionada}}</span>`
      : `<span class="crumb" data-ir="regiao">${{raSelecionada}}</span>`;
  }}
  if (municipioSelecionado) {{
    html += ` <span class="sep">›</span> <span class="crumb atual">${{municipioSelecionado}}</span>`;
  }}
  el.innerHTML = html;
  el.querySelectorAll('.crumb[data-ir]').forEach(elCrumb => {{
    elCrumb.addEventListener('click', () => {{
      if (elCrumb.dataset.ir === 'estado') irParaEstado();
      else if (elCrumb.dataset.ir === 'regiao') irParaRegiao(raSelecionada);
    }});
  }});
}}

const OPACIDADE_CHEIA = 0.75;
const OPACIDADE_ESMAECIDA = 0.28;

function aplicarVisibilidade() {{
  const vis = (id, v) => {{ if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', v ? 'visible' : 'none'); }};
  const noEstado = nivelAtual === 'estado';
  const naRegiao = nivelAtual === 'regiao';
  const noMunicipio = nivelAtual === 'municipio';

  vis('ra-fill', noEstado); vis('ra-linha', noEstado);
  // no nivel municipio o poligono do municipio continua visivel, porem esmaecido, como contexto
  vis('municipios-fill', naRegiao || noMunicipio);
  vis('municipios-linha', naRegiao || noMunicipio);
  vis('pontos', noMunicipio);

  vis('ra-hachura', noEstado);
  vis('municipios-hachura', naRegiao || noMunicipio);

  if (map.getLayer('municipios-fill')) {{
    map.setPaintProperty('municipios-fill', 'fill-opacity', noMunicipio ? OPACIDADE_ESMAECIDA : OPACIDADE_CHEIA);
  }}
  if (map.getLayer('municipios-hachura')) {{
    map.setPaintProperty('municipios-hachura', 'fill-opacity', noMunicipio ? 0.3 : 0.85);
  }}
  if (map.getLayer('municipios-linha')) {{
    map.setPaintProperty('municipios-linha', 'line-opacity', noMunicipio ? 0.5 : 1);
  }}
}}

function irParaEstado() {{
  nivelAtual = 'estado'; raSelecionada = null; municipioSelecionado = null;
  document.getElementById('legenda-niveis').style.display = '';
  document.getElementById('area-vazia').style.display = 'none';
  aplicarVisibilidade();
  enquadrarEstado();
  atualizarBreadcrumb();
}}

function irParaRegiao(ra) {{
  nivelAtual = 'regiao'; raSelecionada = ra; municipioSelecionado = null;
  document.getElementById('legenda-niveis').style.display = '';
  document.getElementById('area-vazia').style.display = 'none';
  // carrega na fonte SOMENTE os municipios desta RA (em vez dos 645) -> muito menos
  // carga de render/GPU, o que mantem o mapa fluido inclusive no celular
  const feats = geojsonMun.features.filter(f => f.properties.regiao_administrativa === ra);
  map.getSource('municipios').setData({{ type: 'FeatureCollection', features: feats }});
  aplicarVisibilidade();
  const bounds = new maplibregl.LngLatBounds();
  feats.forEach(f => bounds.extend(limitesDaFeature(f)));
  if (!bounds.isEmpty()) map.fitBounds(bounds, {{ padding: 30, maxZoom: 11 }});
  atualizarBreadcrumb();
}}

function irParaMunicipio(municipioNorm, municipioNome) {{
  nivelAtual = 'municipio'; municipioSelecionado = municipioNome;
  const pontosDoMunicipio = geojsonPontos.features.filter(f => f.properties.municipio_norm === municipioNorm);
  const feat = geojsonMun.features.find(f => f.properties.municipio_norm === municipioNorm);
  const vazio = document.getElementById('area-vazia');

  // mantem so o poligono deste municipio na fonte: ele fica visivel por baixo dos pins,
  // esmaecido (ver aplicarVisibilidade), preservando a cor de maturidade como contexto
  if (feat) map.getSource('municipios').setData({{ type: 'FeatureCollection', features: [feat] }});
  map.getSource('pontos').setData({{ type: 'FeatureCollection', features: pontosDoMunicipio }});
  aplicarVisibilidade();

  if (pontosDoMunicipio.length === 0) {{
    document.getElementById('legenda-niveis').style.display = 'none';
    vazio.style.display = '';
    vazio.innerHTML = `<div class="vazio">Nenhuma empresa ou usina mapeada em <b>${{municipioNome}}</b> nesta base de dados.</div>`;
  }} else {{
    document.getElementById('legenda-niveis').style.display = '';
    vazio.style.display = 'none';
  }}
  if (feat) map.fitBounds(limitesDaFeature(feat), {{ padding: 40, maxZoom: 14 }});
  atualizarBreadcrumb();
}}

// A hachura codifica a fatia de municipios sem NENHUM registro. Sem ela a cor sozinha
// esconderia a diferenca entre uma regiao homogenea e uma regiao com metade dos municipios
// zerada — e ela e o unico canal que sobrevive a impressao em preto-e-branco.
function registraHachura(nome, tile, largura, alpha, passos) {{
  const c = document.createElement('canvas');
  c.width = c.height = tile;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, tile, tile);
  ctx.strokeStyle = `rgba(255,255,255,${{alpha}})`;
  ctx.lineWidth = largura;
  // retas y = -x + k varrendo 0..2*tile; o passo divide `tile` exatamente, entao o
  // ladrilho encaixa sem emenda visivel
  const passo = (2 * tile) / passos;
  for (let k = 0; k <= 2 * tile; k += passo) {{
    ctx.beginPath();
    ctx.moveTo(k - tile - 1, tile + 1);
    ctx.lineTo(k + 1, -1);
    ctx.stroke();
  }}
  map.addImage(nome, ctx.getImageData(0, 0, tile, tile), {{ pixelRatio: 2 }});
}}

function camadaHachura(id, source) {{
  return {{
    id, type: 'fill', source,
    filter: ['!=', ['get', 'listras'], 'liso'],
    paint: {{
      'fill-pattern': ['match', ['get', 'listras'], 'forte', 'hachura-forte', 'hachura-leve'],
      'fill-opacity': 0.85,
    }},
    layout: {{ visibility: 'none' }},
  }};
}}

function iniciarMapa() {{
  const VAZIO = {{ type: 'FeatureCollection', features: [] }};
  registraHachura('hachura-leve', 32, 3, 0.6, 2);
  registraHachura('hachura-forte', 32, 4, 0.9, 4);
  map.addSource('ra', {{ type: 'geojson', data: geojsonRA }});
  // municipios e pontos comecam vazios e sao preenchidos sob demanda (ver irParaRegiao/irParaMunicipio)
  map.addSource('municipios', {{ type: 'geojson', data: VAZIO }});
  map.addSource('pontos', {{ type: 'geojson', data: VAZIO }});

  map.addLayer({{ id: 'ra-fill', type: 'fill', source: 'ra', paint: {{ 'fill-color': matchNivel, 'fill-opacity': 0.75 }} }});
  map.addLayer(camadaHachura('ra-hachura', 'ra'));
  map.addLayer({{ id: 'ra-linha', type: 'line', source: 'ra', paint: {{ 'line-color': '#ffffff', 'line-width': 1.5 }} }});

  map.addLayer({{
    id: 'municipios-fill', type: 'fill', source: 'municipios',
    paint: {{ 'fill-color': matchNivel, 'fill-opacity': 0.75 }},
    layout: {{ visibility: 'none' }},
  }});
  map.addLayer(camadaHachura('municipios-hachura', 'municipios'));
  map.addLayer({{
    id: 'municipios-linha', type: 'line', source: 'municipios',
    paint: {{ 'line-color': '#ffffff', 'line-width': 1 }},
    layout: {{ visibility: 'none' }},
  }});

  map.addLayer({{
    id: 'pontos', type: 'circle', source: 'pontos',
    paint: {{
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 3, 15, 9],
      'circle-color': matchAtividade, 'circle-opacity': 0.85,
      'circle-stroke-width': 0.6, 'circle-stroke-color': '#ffffff',
    }},
    layout: {{ visibility: 'none' }},
  }});

  aplicarVisibilidade();
  enquadrarEstado();

  const popupRegiao = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, maxWidth: '300px' }});
  // ATENCAO: features de municipio TAMBEM tem 'regiao_administrativa' preenchido, entao o titulo
  // precisa vir do tipo de camada, nunca de um fallback `regiao_administrativa || nome`.
  const num1 = v => Number(v).toFixed(1).replace('.', ',');
  // MapLibre devolve propriedades nao-primitivas (o array `dist`) como string JSON
  const lista = d => (typeof d === 'string' ? JSON.parse(d) : d);

  function barraDistribuicao(dist, n) {{
    const fatias = dist.map((c, i) => c
      ? `<span style="width:${{(100 * c / n).toFixed(2)}}%;background:${{PALETA[i]}}" title="${{c}} município(s) no nível ${{i}}"></span>`
      : '').join('');
    return `<div class="barra">${{fatias}}</div>`;
  }}

  function popupRegiaoHTML(p, tipo) {{
    const ehMunicipio = tipo === 'municipio';
    const titulo = ehMunicipio ? p.nome : p.regiao_administrativa;
    const subtitulo = ehMunicipio
      ? `<p class="popup-sub">${{p.regiao_administrativa}}</p>`
      : `<p class="popup-sub">${{p.n_mun}} municípios · média ${{num1(p.media)}} de 4 serviços</p>`;
    const rotulo = ehMunicipio ? 'Nível' : 'Classe';
    // `travada` chega como boolean ou como a string "true", dependendo do caminho da propriedade
    const trava = (!ehMunicipio && String(p.travada) === 'true')
      ? ` <span style="color:#555;font-weight:400">(rebaixada pela cobertura)</span>` : '';
    const cobertura = ehMunicipio ? '' : `
      ${{barraDistribuicao(lista(p.dist), p.n_mun)}}
      <p class="popup-cobertura"><b>${{p.n_vazios}} de ${{p.n_mun}} municípios (${{num1(p.pct_vazio)}}%)</b> sem nenhum registro</p>`;
    const tituloTabela = ehMunicipio ? '' : '<tr><td colspan="2" class="popup-sub">Total de estabelecimentos na região</td></tr>';
    return `
      <p class="popup-nome">${{titulo}}</p>
      ${{subtitulo}}
      <p class="popup-nivel" style="color:${{PALETA[p.classe]}}">${{rotulo}} ${{p.classe}} — ${{p.classe_desc}}${{trava}}</p>
      ${{cobertura}}
      <table class="popup-tabela">
        ${{tituloTabela}}
        <tr><td>Coleta</td><td>${{p.coleta}}</td></tr>
        <tr><td>Reciclagem</td><td>${{p.reciclagem}}</td></tr>
        <tr><td>Tratamento/Disposição</td><td>${{p.tratamento}}</td></tr>
        <tr><td>Orgânicos (compost. + energia)</td><td>${{p.organicos}}</td></tr>
        <tr><td>Total de iniciativas</td><td>${{p.total_iniciativas}}</td></tr>
      </table>
      ${{p.faltando !== 'nenhum elemento' ? `<p class="popup-faltando">Nenhum registro em toda a área: ${{p.faltando}}</p>` : ''}}
    `;
  }}

  // hover mostra os dados; clique simples entra no proximo nivel
  map.on('mousemove', 'ra-fill', (e) => {{
    const p = e.features[0].properties;
    popupRegiao.setLngLat(e.lngLat)
      .setHTML(popupRegiaoHTML(p, 'ra') + '<p class="dica">Clique para abrir esta região →</p>').addTo(map);
  }});
  map.on('mouseleave', 'ra-fill', () => popupRegiao.remove());
  map.on('click', 'ra-fill', (e) => {{
    popupRegiao.remove();
    irParaRegiao(e.features[0].properties.regiao_administrativa);
  }});

  // no nivel 'municipio' o poligono fica so como contexto esmaecido: nao mostra popup nem re-entra
  map.on('mousemove', 'municipios-fill', (e) => {{
    if (nivelAtual !== 'regiao') return;
    const p = e.features[0].properties;
    popupRegiao.setLngLat(e.lngLat)
      .setHTML(popupRegiaoHTML(p, 'municipio') + '<p class="dica">Clique para ver as empresas →</p>').addTo(map);
  }});
  map.on('mouseleave', 'municipios-fill', () => popupRegiao.remove());
  map.on('click', 'municipios-fill', (e) => {{
    if (nivelAtual !== 'regiao') return;
    popupRegiao.remove();
    const p = e.features[0].properties;
    irParaMunicipio(p.municipio_norm, p.nome);
  }});

  const popupPonto = new maplibregl.Popup({{ closeButton: true, closeOnClick: true, maxWidth: '280px' }});
  map.on('click', 'pontos', (e) => {{
    const p = e.features[0].properties;
    let html;
    if (p.setor === 'energia') {{
      html = `<p class="popup-nome">${{p.nome}}</p><p class="popup-cnae">${{p.combustivel}} · ${{p.potencia_mw}} MW</p>`
           + `<p class="popup-end">${{p.municipio}}</p>` + (p.proprietario ? `<p class="popup-end">${{p.proprietario}}</p>` : '');
    }} else {{
      const aprox = p.aprox ? '<p class="popup-aprox">Localização aproximada (centro do CEP)</p>' : '';
      html = `<p class="popup-nome">${{p.nome}}</p><p class="popup-cnae">CNAE ${{p.categoria}}</p><p class="popup-end">${{p.endereco}}</p>${{aprox}}`;
    }}
    popupPonto.setLngLat(e.features[0].geometry.coordinates).setHTML(html).addTo(map);
  }});

  ['ra-fill', 'municipios-fill', 'pontos'].forEach(id => {{
    map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', id, () => map.getCanvas().style.cursor = '');
  }});

  atualizarBreadcrumb();
  map.resize();
  map.triggerRepaint();

  // O container costuma ainda NAO ter o tamanho final quando o estilo carrega (aba nova,
  // iframe, painel lateral), e o fitBounds inicial sai com o zoom errado — o mapa abria
  // desenquadrado. Nao da para esperar o evento 'idle': ele nao dispara enquanto algum
  // tile do mapa-base estiver pendente. O ResizeObserver reage ao tamanho real do
  // container, que e exatamente o que o fitBounds precisa saber.
  let ultimaL = 0, ultimaA = 0, usuarioMexeu = false;
  map.on('dragstart', () => {{ usuarioMexeu = true; }});
  map.on('zoomstart', (e) => {{ if (e.originalEvent) usuarioMexeu = true; }});
  new ResizeObserver(() => {{
    const el = map.getContainer();
    if (el.clientWidth === ultimaL && el.clientHeight === ultimaA) return;
    ultimaL = el.clientWidth; ultimaA = el.clientHeight;
    map.resize();
    if (nivelAtual === 'estado' && !usuarioMexeu) enquadrarEstado();
    map.triggerRepaint();
  }}).observe(map.getContainer());
}}
if (map.isStyleLoaded()) {{ iniciarMapa(); }} else {{ map.once('style.load', iniciarMapa); }}
</script>
</body>
</html>
'''

with open(SAIDA, 'w', encoding='utf-8') as f:
    f.write(html)
import os
print(f"-> {SAIDA} ({round(os.path.getsize(SAIDA)/1024/1024, 2)} MB)")
