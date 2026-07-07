#!/usr/bin/env python3
"""
Gera uma versão do mapa em mapa de calor (heatmap) do MapLibre GL JS: densidade de
iniciativas por zona, com transição suave para pontos individuais coloridos ao
aproximar o zoom (padrão recomendado pela própria biblioteca). Mesmos dados e
filtros (Região Administrativa, setor) do mapa de pontos.
"""
import re
import json
import duckdb

CSV_RESIDUOS = 'empresas_sp_circular_enriquecido.csv'
CSV_ENERGIA = 'energia_biomassa_biogas_enriquecido.csv'
SAIDA = 'mapa_calor.html'

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

con = duckdb.connect()

t_res = f"read_csv('{CSV_RESIDUOS}', header=true, all_varchar=true)"
rows_res = con.sql(f"""
    SELECT cnpj, nome_fantasia, cnae_principal, tipo_logradouro, logradouro, numero,
           bairro, municipio, latitude, longitude, geocode_status, regiao_administrativa
    FROM {t_res}
    WHERE latitude IS NOT NULL AND latitude != '' AND longitude IS NOT NULL AND longitude != ''
""").fetchall()
cols_res = ['cnpj', 'nome_fantasia', 'cnae_principal', 'tipo_logradouro', 'logradouro', 'numero',
            'bairro', 'municipio', 'latitude', 'longitude', 'geocode_status', 'regiao_administrativa']

t_en = f"read_csv('{CSV_ENERGIA}', header=true, all_varchar=true)"
rows_en = con.sql(f"""
    SELECT nome, categoria_energia, combustivel_detalhe, municipio,
           latitude, longitude, potencia_outorgada_kw, proprietario, regiao_administrativa
    FROM {t_en}
""").fetchall()
cols_en = ['nome', 'categoria_energia', 'combustivel_detalhe', 'municipio',
           'latitude', 'longitude', 'potencia_outorgada_kw', 'proprietario', 'regiao_administrativa']

features = []
ras_vistas = set()
for r in rows_res:
    d = dict(zip(cols_res, r))
    if d['regiao_administrativa']:
        ras_vistas.add(d['regiao_administrativa'])
    nome = d['nome_fantasia'] or '(sem nome fantasia)'
    endereco = f"{d['tipo_logradouro']} {d['logradouro']}, {d['numero']} - {d['bairro']}, {d['municipio']}"
    features.append({
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [float(d['longitude']), float(d['latitude'])]},
        'properties': {
            'setor': 'residuos', 'categoria': d['cnae_principal'], 'nome': nome, 'endereco': endereco,
            'aprox': d['geocode_status'] == 'cep_aproximado', 'ra': d['regiao_administrativa'] or '',
        },
    })
for r in rows_en:
    d = dict(zip(cols_en, r))
    if d['regiao_administrativa']:
        ras_vistas.add(d['regiao_administrativa'])
    cat = 'biogas' if d['categoria_energia'] == 'Biogás' else 'biomassa'
    mw = round(float(d['potencia_outorgada_kw']) / 1000, 1)
    features.append({
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [float(d['longitude']), float(d['latitude'])]},
        'properties': {
            'setor': 'energia', 'categoria': cat, 'nome': d['nome'],
            'combustivel': d['combustivel_detalhe'], 'municipio': d['municipio'],
            'potencia_mw': mw, 'proprietario': d['proprietario'] or '', 'ra': d['regiao_administrativa'] or '',
        },
    })

geojson = {'type': 'FeatureCollection', 'features': features}
n_residuos = len(rows_res)
n_energia = len(rows_en)
n_total = n_residuos + n_energia


def ra_sort_key(ra):
    m = re.match(r'(\d+)([A-Za-z]?)', ra)
    return (int(m.group(1)), m.group(2)) if m else (99, '')


ras_ordenadas = sorted(ras_vistas, key=ra_sort_key)
opcoes_ra = ''.join(f'<option value="{ra}">{ra}</option>' for ra in ras_ordenadas)

match_atividade = ['match', ['get', 'categoria']]
for cod, (desc, cor) in CNAE_INFO.items():
    match_atividade += [cod, cor]
for cod, (desc, cor) in ENERGIA_INFO.items():
    match_atividade += [cod, cor]
match_atividade.append('#999999')

html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Mapa de Economia Circular — Mapa de calor — SENAC SP</title>
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
  .stats {{ display: flex; gap: 8px; margin-bottom: 14px; }}
  .stat {{ flex: 1; background: #E8F5E9; border-radius: 8px; padding: 8px 10px; }}
  .stat .n {{ font-size: 18px; font-weight: 700; color: #1B5E20; line-height: 1.1; }}
  .stat .l {{ font-size: 10.5px; color: #555; }}
  .campo {{ margin-bottom: 12px; }}
  .campo label.rotulo {{
    display: block; font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.03em; color: #888; margin-bottom: 5px;
  }}
  select#filtro-ra {{
    width: 100%; padding: 6px 8px; font-size: 12.5px; border: 1px solid #ccc; border-radius: 6px;
    background: #fff;
  }}
  .legenda-item {{
    display: flex; align-items: center; gap: 8px; padding: 5px 2px;
    font-size: 12px; cursor: pointer; border-bottom: 1px solid #f0f0f0;
  }}
  .legenda-item:last-child {{ border-bottom: none; }}
  .count {{ color: #888; margin-left: auto; font-variant-numeric: tabular-nums; }}
  .escala {{
    display: flex; height: 10px; border-radius: 4px; overflow: hidden; margin: 6px 0 4px;
    background: linear-gradient(to right, rgba(33,102,172,0.2), rgb(103,169,207), rgb(209,229,240),
                rgb(253,219,199), rgb(239,138,98), rgb(178,24,43));
  }}
  .escala-rotulos {{ display: flex; justify-content: space-between; font-size: 10px; color: #888; }}
  .aviso {{
    font-size: 11px; color: #666; background: #FFF8E1; border-radius: 6px; padding: 8px 10px;
    margin-top: 10px; line-height: 1.4;
  }}
  .nav-link {{
    display: block; text-align: center; font-size: 11.5px; margin-top: 10px; padding: 7px;
    border: 1px solid #ccc; border-radius: 6px; color: #1B5E20; text-decoration: none;
  }}
  .nav-link:hover {{ background: #f0f0f0; }}
  .maplibregl-popup-content {{ font-family: inherit; font-size: 13px; padding: 10px 12px; }}
  .popup-nome {{ font-weight: 700; margin: 0 0 4px; }}
  .popup-cnae {{ color: #1B5E20; font-size: 11.5px; margin: 0 0 4px; }}
  .popup-end {{ color: #555; font-size: 12px; margin: 0; }}
  .popup-aprox {{ color: #b26a00; font-size: 10.5px; margin-top: 4px; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="painel">
  <div class="painel-header">
    <div>
      <h1>Mapa de calor</h1>
      <p class="sub">Densidade de iniciativas de economia circular — SP · SENAC</p>
    </div>
    <button id="toggle-painel" title="Recolher/expandir menu">✕</button>
  </div>
  <div id="painel-conteudo">
  <div class="stats">
    <div class="stat"><div class="n">{n_total:,}</div><div class="l">no mapa</div></div>
    <div class="stat"><div class="n">{n_residuos:,}</div><div class="l">resíduos</div></div>
    <div class="stat"><div class="n">{n_energia:,}</div><div class="l">energia</div></div>
  </div>
  <div class="campo">
    <label class="rotulo">Região Administrativa</label>
    <select id="filtro-ra">
      <option value="">Todas</option>
      {opcoes_ra}
    </select>
  </div>
  <div class="campo">
    <label class="rotulo">Setor</label>
    <label class="legenda-item">
      <input type="checkbox" checked id="chk-residuos"> Resíduos sólidos urbanos
      <span class="count">{n_residuos:,}</span>
    </label>
    <label class="legenda-item">
      <input type="checkbox" checked id="chk-energia"> Energia (biogás/biomassa)
      <span class="count">{n_energia:,}</span>
    </label>
  </div>
  <div class="campo">
    <label class="rotulo">Densidade</label>
    <div class="escala"></div>
    <div class="escala-rotulos"><span>baixa</span><span>alta</span></div>
  </div>
  <div class="aviso">Dê zoom para ver os pontos individuais coloridos por atividade — o mapa de calor mostra a concentração geral.</div>
  <a class="nav-link" href="mapa_economia_circular.html">Ver versão com pontos individuais →</a>
  </div>
</div>
<script>
const geojson = {json.dumps(geojson, ensure_ascii=False)};
const matchAtividade = {json.dumps(match_atividade)};
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
if (window.matchMedia('(max-width: 720px)').matches) {{
  painelEl.classList.add('recolhido');
}}
atualizarBotaoPainel();

function iniciarMapa() {{
  map.addSource('iniciativas', {{ type: 'geojson', data: geojson }});

  map.addLayer({{
    id: 'calor',
    type: 'heatmap',
    source: 'iniciativas',
    maxzoom: 13,
    paint: {{
      'heatmap-weight': 1,
      'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 5, 0.6, 9, 1.4, 13, 2.5],
      'heatmap-color': [
        'interpolate', ['linear'], ['heatmap-density'],
        0, 'rgba(33,102,172,0)',
        0.2, 'rgb(103,169,207)',
        0.4, 'rgb(209,229,240)',
        0.6, 'rgb(253,219,199)',
        0.8, 'rgb(239,138,98)',
        1, 'rgb(178,24,43)',
      ],
      'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 5, 6, 9, 22, 13, 34],
      'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.9, 12, 0.75, 13, 0],
    }},
  }});

  map.addLayer({{
    id: 'pontos',
    type: 'circle',
    source: 'iniciativas',
    minzoom: 10,
    paint: {{
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 16, 8],
      'circle-color': matchAtividade,
      'circle-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0, 11, 0.85],
      'circle-stroke-width': 0.6,
      'circle-stroke-color': '#ffffff',
    }},
  }});

  const bounds = new maplibregl.LngLatBounds();
  geojson.features.forEach(f => bounds.extend(f.geometry.coordinates));
  if (!bounds.isEmpty()) map.fitBounds(bounds, {{ padding: 40, maxZoom: 9 }});
  map.resize();
  map.triggerRepaint();
  setTimeout(() => {{ map.resize(); map.triggerRepaint(); }}, 150);
  setTimeout(() => map.triggerRepaint(), 500);

  const popup = new maplibregl.Popup({{ closeButton: true, closeOnClick: true, maxWidth: '280px' }});
  map.on('click', 'pontos', (e) => {{
    const p = e.features[0].properties;
    let html;
    if (p.setor === 'energia') {{
      html = `<p class="popup-nome">${{p.nome}}</p>`
           + `<p class="popup-cnae">${{p.combustivel}} · ${{p.potencia_mw}} MW</p>`
           + `<p class="popup-end">${{p.municipio}}</p>`
           + (p.proprietario ? `<p class="popup-end">${{p.proprietario}}</p>` : '');
    }} else {{
      const aprox = p.aprox ? '<p class="popup-aprox">Localização aproximada (centro do CEP)</p>' : '';
      html = `<p class="popup-nome">${{p.nome}}</p><p class="popup-cnae">CNAE ${{p.categoria}}</p>`
           + `<p class="popup-end">${{p.endereco}}</p>${{aprox}}`;
    }}
    popup.setLngLat(e.features[0].geometry.coordinates).setHTML(html).addTo(map);
  }});
  map.on('mouseenter', 'pontos', () => map.getCanvas().style.cursor = 'pointer');
  map.on('mouseleave', 'pontos', () => map.getCanvas().style.cursor = '');

  function aplicarFiltro() {{
    const setores = [];
    if (document.getElementById('chk-residuos').checked) setores.push('residuos');
    if (document.getElementById('chk-energia').checked) setores.push('energia');
    const ra = document.getElementById('filtro-ra').value;
    const condicoes = [['in', ['get', 'setor'], ['literal', setores]]];
    if (ra) condicoes.push(['==', ['get', 'ra'], ra]);
    const filtro = condicoes.length > 1 ? ['all', ...condicoes] : condicoes[0];
    map.setFilter('calor', filtro);
    map.setFilter('pontos', filtro);
  }}
  document.getElementById('filtro-ra').addEventListener('change', aplicarFiltro);
  document.getElementById('chk-residuos').addEventListener('change', aplicarFiltro);
  document.getElementById('chk-energia').addEventListener('change', aplicarFiltro);
}}
if (map.isStyleLoaded()) {{ iniciarMapa(); }} else {{ map.once('style.load', iniciarMapa); }}
</script>
</body>
</html>
'''

with open(SAIDA, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"{n_total} pins ({n_residuos} residuos + {n_energia} energia) -> {SAIDA}")
