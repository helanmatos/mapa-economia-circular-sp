#!/usr/bin/env python3
"""
Gera um mapa HTML standalone (MapLibre GL JS) com um pin por iniciativa de economia
circular em SP. Duas formas de colorir/filtrar (item 9 do escopo formal):
  - Por atividade: setor Resíduos sólidos urbanos (CNAE) + setor Energia (biogás/biomassa)
  - Por categoria circular (ISO 59000, item 4 do escopo): Reciclagem, Bioeconomia,
    Valorização energética, Tratamento/disposição
Mais um filtro por Região Administrativa (item 2/8 do escopo).
Fontes: empresas_sp_circular_enriquecido.csv + energia_biomassa_biogas_enriquecido.csv
(geradas por enriquece.py).
"""
import re
import json
import duckdb

CSV_RESIDUOS = 'empresas_sp_circular_enriquecido.csv'
CSV_ENERGIA = 'energia_biomassa_biogas_enriquecido.csv'
SAIDA = 'mapa_economia_circular.html'

CNAE_INFO = {
    '3811400': ('Coleta de resíduos não-perigosos', '#4E79A7'),
    '3812200': ('Coleta de resíduos perigosos', '#F28E2B'),
    '3821100': ('Tratamento/disposição não-perigosos', '#E15759'),
    '3822000': ('Tratamento/disposição perigosos', '#76B7B2'),
    '3831901': ('Recuperação de sucata de alumínio', '#59A14F'),
    '3831999': ('Recuperação de sucata metálica', '#EDC948'),
    '3832700': ('Recuperação de materiais plásticos', '#B07AA1'),
    '3839401': ('Usinas de compostagem', '#FF9DA7'),
    '3839499': ('Recuperação de materiais (outros)', '#9C755F'),
    '3900500': ('Descontaminação', '#BAB0AC'),
}
ENERGIA_INFO = {
    'biomassa': ('Biomassa (bagaço de cana, floresta)', '#1D3557'),
    'biogas': ('Biogás (aterro, dejetos)', '#2A9D8F'),
}
CIRCULAR_INFO = {
    'Reciclagem': '#2E7D32',
    'Bioeconomia': '#8D6E63',
    'Valorização energética': '#F9A825',
    'Tratamento/disposição': '#757575',
}

con = duckdb.connect()

t_res = f"read_csv('{CSV_RESIDUOS}', header=true, all_varchar=true)"
rows_res = con.sql(f"""
    SELECT cnpj, nome_fantasia, cnae_principal, tipo_logradouro, logradouro, numero,
           bairro, municipio, latitude, longitude, geocode_status,
           regiao_administrativa, categoria_circular
    FROM {t_res}
    WHERE latitude IS NOT NULL AND latitude != '' AND longitude IS NOT NULL AND longitude != ''
""").fetchall()
cols_res = ['cnpj', 'nome_fantasia', 'cnae_principal', 'tipo_logradouro', 'logradouro', 'numero',
            'bairro', 'municipio', 'latitude', 'longitude', 'geocode_status',
            'regiao_administrativa', 'categoria_circular']
total_residuos = con.sql(f"SELECT count(*) FROM {t_res}").fetchone()[0]

t_en = f"read_csv('{CSV_ENERGIA}', header=true, all_varchar=true)"
rows_en = con.sql(f"""
    SELECT nome, categoria_energia, fonte_combustivel, combustivel_detalhe, municipio,
           latitude, longitude, potencia_outorgada_kw, proprietario,
           regiao_administrativa, categoria_circular
    FROM {t_en}
""").fetchall()
cols_en = ['nome', 'categoria_energia', 'fonte_combustivel', 'combustivel_detalhe', 'municipio',
           'latitude', 'longitude', 'potencia_outorgada_kw', 'proprietario',
           'regiao_administrativa', 'categoria_circular']

features = []
por_cnae = {}
por_circular = {}
ras_vistas = set()

for r in rows_res:
    d = dict(zip(cols_res, r))
    cnae = d['cnae_principal']
    por_cnae[cnae] = por_cnae.get(cnae, 0) + 1
    por_circular[d['categoria_circular']] = por_circular.get(d['categoria_circular'], 0) + 1
    if d['regiao_administrativa']:
        ras_vistas.add(d['regiao_administrativa'])
    nome = d['nome_fantasia'] or '(sem nome fantasia)'
    endereco = f"{d['tipo_logradouro']} {d['logradouro']}, {d['numero']} - {d['bairro']}, {d['municipio']}"
    features.append({
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [float(d['longitude']), float(d['latitude'])]},
        'properties': {
            'setor': 'residuos', 'categoria': cnae, 'nome': nome, 'endereco': endereco,
            'aprox': d['geocode_status'] == 'cep_aproximado',
            'ra': d['regiao_administrativa'] or '', 'circular': d['categoria_circular'] or '',
        },
    })

por_energia = {}
for r in rows_en:
    d = dict(zip(cols_en, r))
    cat = 'biogas' if d['categoria_energia'] == 'Biogás' else 'biomassa'
    por_energia[cat] = por_energia.get(cat, 0) + 1
    por_circular[d['categoria_circular']] = por_circular.get(d['categoria_circular'], 0) + 1
    if d['regiao_administrativa']:
        ras_vistas.add(d['regiao_administrativa'])
    mw = float(d['potencia_outorgada_kw']) / 1000
    features.append({
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [float(d['longitude']), float(d['latitude'])]},
        'properties': {
            'setor': 'energia', 'categoria': cat, 'nome': d['nome'],
            'combustivel': d['combustivel_detalhe'], 'municipio': d['municipio'],
            'potencia_mw': round(mw, 1), 'proprietario': d['proprietario'] or '',
            'ra': d['regiao_administrativa'] or '', 'circular': d['categoria_circular'] or '',
        },
    })

geojson = {'type': 'FeatureCollection', 'features': features}
n_residuos_mapa = len(rows_res)
n_energia_mapa = len(rows_en)
n_total_mapa = n_residuos_mapa + n_energia_mapa


def ra_sort_key(ra):
    m = re.match(r'(\d+)([A-Za-z]?)', ra)
    return (int(m.group(1)), m.group(2)) if m else (99, '')


ras_ordenadas = sorted(ras_vistas, key=ra_sort_key)

match_atividade = ['match', ['get', 'categoria']]
for cod, (desc, cor) in CNAE_INFO.items():
    match_atividade += [cod, cor]
for cod, (desc, cor) in ENERGIA_INFO.items():
    match_atividade += [cod, cor]
match_atividade.append('#999999')

match_circular = ['match', ['get', 'circular']]
for cat, cor in CIRCULAR_INFO.items():
    match_circular += [cat, cor]
match_circular.append('#999999')


def linha_legenda(chave, desc, cor, n):
    return f'''
<label class="legenda-item">
  <input type="checkbox" checked data-cat="{chave}">
  <span class="swatch" style="background:{cor}"></span>
  <span class="desc">{desc}</span>
  <span class="count">{n:,}</span>
</label>'''.replace(',', '.')


legenda_residuos = ''.join(
    linha_legenda(cod, f"{cod[:4]}-{cod[4]}/{cod[5:]} · {desc}", cor, por_cnae.get(cod, 0))
    for cod, (desc, cor) in CNAE_INFO.items()
)
legenda_energia = ''.join(
    linha_legenda(cod, desc, cor, por_energia.get(cod, 0))
    for cod, (desc, cor) in ENERGIA_INFO.items()
)
legenda_circular = ''.join(
    linha_legenda(cat, cat, cor, por_circular.get(cat, 0))
    for cat, cor in CIRCULAR_INFO.items()
)
opcoes_ra = ''.join(f'<option value="{ra}">{ra}</option>' for ra in ras_ordenadas)

html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Mapa de Economia Circular — SENAC SP</title>
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
  #painel .sub {{ font-size: 12px; color: #666; margin: 0 0 12px; }}
  .stats {{ display: flex; gap: 8px; margin-bottom: 14px; }}
  .stat {{ flex: 1; background: #E8F5E9; border-radius: 8px; padding: 8px 10px; }}
  .stat .n {{ font-size: 18px; font-weight: 700; color: #1B5E20; line-height: 1.1; }}
  .stat .l {{ font-size: 10.5px; color: #555; }}
  .campo {{ margin-bottom: 12px; }}
  .campo label.rotulo {{
    display: block; font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.03em; color: #888; margin-bottom: 5px;
  }}
  .modo-toggle {{ display: flex; border: 1px solid #ccc; border-radius: 8px; overflow: hidden; }}
  .modo-toggle button {{
    flex: 1; padding: 6px 4px; font-size: 11.5px; border: none; background: #fafafa; cursor: pointer;
  }}
  .modo-toggle button.ativo {{ background: #2E7D32; color: #fff; }}
  select#filtro-ra {{
    width: 100%; padding: 6px 8px; font-size: 12.5px; border: 1px solid #ccc; border-radius: 6px;
    background: #fff;
  }}
  .setor-titulo {{
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em;
    color: #888; margin: 14px 0 4px; padding-top: 8px; border-top: 1px solid #eee;
  }}
  .setor-titulo:first-of-type {{ margin-top: 0; padding-top: 0; border-top: none; }}
  .legenda-item {{
    display: flex; align-items: center; gap: 8px; padding: 5px 2px;
    font-size: 12px; cursor: pointer; border-bottom: 1px solid #f0f0f0;
  }}
  .legenda-item:last-child {{ border-bottom: none; }}
  .swatch {{ width: 11px; height: 11px; border-radius: 3px; flex-shrink: 0; }}
  .desc {{ flex: 1; color: #333; }}
  .count {{ color: #888; font-variant-numeric: tabular-nums; }}
  .toolbar {{ display: flex; gap: 6px; margin-top: 10px; }}
  .toolbar button {{
    flex: 1; font-size: 11.5px; padding: 6px; border: 1px solid #ccc; border-radius: 6px;
    background: #fafafa; cursor: pointer;
  }}
  .toolbar button:hover {{ background: #eee; }}
  .maplibregl-popup-content {{ font-family: inherit; font-size: 13px; padding: 10px 12px; }}
  .popup-nome {{ font-weight: 700; margin: 0 0 4px; }}
  .popup-cnae {{ color: #1B5E20; font-size: 11.5px; margin: 0 0 4px; }}
  .popup-end {{ color: #555; font-size: 12px; margin: 0; }}
  .popup-aprox {{ color: #b26a00; font-size: 10.5px; margin-top: 4px; }}
  .popup-ra {{ color: #888; font-size: 10.5px; margin-top: 4px; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="painel">
  <h1>Mapa de Economia Circular</h1>
  <p class="sub">Resíduos e energia (biogás/biomassa) — SP · SENAC</p>
  <div class="stats">
    <div class="stat"><div class="n">{n_total_mapa:,}</div><div class="l">no mapa</div></div>
    <div class="stat"><div class="n">{n_residuos_mapa:,}</div><div class="l">resíduos</div></div>
    <div class="stat"><div class="n">{n_energia_mapa:,}</div><div class="l">energia</div></div>
  </div>
  <div class="campo">
    <label class="rotulo">Região Administrativa</label>
    <select id="filtro-ra">
      <option value="">Todas</option>
      {opcoes_ra}
    </select>
  </div>
  <div class="campo">
    <label class="rotulo">Colorir por</label>
    <div class="modo-toggle">
      <button id="modo-atividade" class="ativo">Atividade</button>
      <button id="modo-circular">Categoria circular</button>
    </div>
  </div>
  <div id="legenda-atividade">
    <div class="setor-titulo">Resíduos sólidos urbanos</div>
    {legenda_residuos}
    <div class="setor-titulo">Energia (biogás/biomassa)</div>
    {legenda_energia}
  </div>
  <div id="legenda-circular" style="display:none">
    <div class="setor-titulo">Categoria circular (ISO 59000)</div>
    {legenda_circular}
  </div>
  <div class="toolbar">
    <button id="btn-todos">Marcar todos</button>
    <button id="btn-nenhum">Desmarcar todos</button>
  </div>
</div>
<script>
const geojson = {json.dumps(geojson, ensure_ascii=False)};
const matchAtividade = {json.dumps(match_atividade)};
const matchCircular = {json.dumps(match_circular)};
const map = new maplibregl.Map({{
  container: 'map',
  style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  center: [-48.5, -22.2],
  zoom: 6,
}});
map.addControl(new maplibregl.NavigationControl(), 'top-right');

let modo = 'atividade'; // 'atividade' | 'circular'

map.on('load', () => {{
  map.addSource('iniciativas', {{ type: 'geojson', data: geojson }});
  map.addLayer({{
    id: 'pontos',
    type: 'circle',
    source: 'iniciativas',
    paint: {{
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 2.5, 10, 5, 14, 8],
      'circle-color': matchAtividade,
      'circle-opacity': 0.8,
      'circle-stroke-width': 0.6,
      'circle-stroke-color': '#ffffff',
    }},
  }});

  const bounds = new maplibregl.LngLatBounds();
  geojson.features.forEach(f => bounds.extend(f.geometry.coordinates));
  if (!bounds.isEmpty()) map.fitBounds(bounds, {{ padding: 40, maxZoom: 9 }});

  const popup = new maplibregl.Popup({{ closeButton: true, closeOnClick: true, maxWidth: '280px' }});
  map.on('click', 'pontos', (e) => {{
    const p = e.features[0].properties;
    const ra = p.ra ? `<p class="popup-ra">${{p.ra}} · ${{p.circular}}</p>` : '';
    let html;
    if (p.setor === 'energia') {{
      html = `<p class="popup-nome">${{p.nome}}</p>`
           + `<p class="popup-cnae">${{p.combustivel}} · ${{p.potencia_mw}} MW</p>`
           + `<p class="popup-end">${{p.municipio}}</p>`
           + (p.proprietario ? `<p class="popup-end">${{p.proprietario}}</p>` : '') + ra;
    }} else {{
      const aprox = p.aprox ? '<p class="popup-aprox">Localização aproximada (centro do CEP)</p>' : '';
      html = `<p class="popup-nome">${{p.nome}}</p><p class="popup-cnae">CNAE ${{p.categoria}}</p>`
           + `<p class="popup-end">${{p.endereco}}</p>${{aprox}}${{ra}}`;
    }}
    popup.setLngLat(e.features[0].geometry.coordinates).setHTML(html).addTo(map);
  }});
  map.on('mouseenter', 'pontos', () => map.getCanvas().style.cursor = 'pointer');
  map.on('mouseleave', 'pontos', () => map.getCanvas().style.cursor = '');

  function legendaAtiva() {{
    return modo === 'atividade'
      ? document.querySelectorAll('#legenda-atividade input')
      : document.querySelectorAll('#legenda-circular input');
  }}

  function aplicarFiltro() {{
    const campo = modo === 'atividade' ? 'categoria' : 'circular';
    const ativos = [...legendaAtiva()].filter(el => el.checked).map(el => el.dataset.cat);
    const ra = document.getElementById('filtro-ra').value;
    const condicoes = [['in', ['get', campo], ['literal', ativos]]];
    if (ra) condicoes.push(['==', ['get', 'ra'], ra]);
    map.setFilter('pontos', condicoes.length > 1 ? ['all', ...condicoes] : condicoes[0]);
  }}

  document.querySelectorAll('#legenda-atividade input, #legenda-circular input')
    .forEach(el => el.addEventListener('change', aplicarFiltro));
  document.getElementById('filtro-ra').addEventListener('change', aplicarFiltro);

  document.getElementById('btn-todos').onclick = () => {{
    legendaAtiva().forEach(el => el.checked = true);
    aplicarFiltro();
  }};
  document.getElementById('btn-nenhum').onclick = () => {{
    legendaAtiva().forEach(el => el.checked = false);
    aplicarFiltro();
  }};

  function trocarModo(novoModo) {{
    modo = novoModo;
    const ehAtividade = modo === 'atividade';
    document.getElementById('modo-atividade').classList.toggle('ativo', ehAtividade);
    document.getElementById('modo-circular').classList.toggle('ativo', !ehAtividade);
    document.getElementById('legenda-atividade').style.display = ehAtividade ? '' : 'none';
    document.getElementById('legenda-circular').style.display = ehAtividade ? 'none' : '';
    map.setPaintProperty('pontos', 'circle-color', ehAtividade ? matchAtividade : matchCircular);
    aplicarFiltro();
  }}
  document.getElementById('modo-atividade').onclick = () => trocarModo('atividade');
  document.getElementById('modo-circular').onclick = () => trocarModo('circular');
}});
</script>
</body>
</html>
'''

with open(SAIDA, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"{n_total_mapa} pins ({n_residuos_mapa} residuos + {n_energia_mapa} energia) -> {SAIDA}")
print(f"{len(ras_ordenadas)} Regioes Administrativas no filtro")
