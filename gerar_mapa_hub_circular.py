#!/usr/bin/env python3
"""
Mapa 1 — "Hub Circular das Regiões Administrativas" (proposta da Mayara, reunião de
07/09/2026): em vez de um pin por empresa, mostra a INFRAESTRUTURA de cada uma das 16
Regiões Administrativas de SP como um polígono colorido por índice de maturidade.

Índice de maturidade (4 elementos, presença/ausência):
  Coleta -> Reciclagem/Recuperação -> Tratamento/Disposição -> Orgânicos (compostagem + energia)
  Nível 3 Circular completo:     tem os 4
  Nível 2 Sem tratamento local:  tem Coleta+Reciclagem+Orgânicos, falta Tratamento/Disposição
  Nível 1 Básico:                só Coleta+Reciclagem
  Nível 0 Incipiente:            falta Coleta ou Reciclagem

Requer geo_cache/regioes_administrativas.geojson (gerado por preparar_malha_ra.py).
"""
import json
import duckdb

GEOJSON_RA = 'geo_cache/regioes_administrativas.geojson'
SAIDA = 'mapa_hub_circular.html'

ELEMENTOS = {
    'coleta': ('3811400', '3812200'),
    'reciclagem': ('3831901', '3831999', '3832700', '3839499'),
    'tratamento_disposicao': ('3821100', '3822000', '3900500'),
    'organicos_cnpj': ('3839401',),
}

NIVEL_INFO = {
    4: ('Circular completo (4 de 4 elementos)', '#1B5E20'),
    3: ('Quase completo (3 de 4 elementos)', '#66A61E'),
    2: ('Intermediário (2 de 4 elementos)', '#F9A825'),
    1: ('Básico (1 de 4 elementos)', '#EF6C00'),
    0: ('Sem infraestrutura mapeada', '#C62828'),
}

con = duckdb.connect()
t_res = "read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true)"
t_en = "read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true)"

por_elemento = con.sql(f"""
    SELECT regiao_administrativa,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['coleta']} THEN 1 ELSE 0 END) coleta,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['reciclagem']} THEN 1 ELSE 0 END) reciclagem,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['tratamento_disposicao']} THEN 1 ELSE 0 END) tratamento,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['organicos_cnpj']} THEN 1 ELSE 0 END) organicos_compost,
      count(*) total_residuos
    FROM {t_res}
    WHERE latitude != '' AND regiao_administrativa != ''
    GROUP BY 1
""").fetchall()
cols = ['regiao_administrativa', 'coleta', 'reciclagem', 'tratamento', 'organicos_compost', 'total_residuos']
dados_ra = {r[0]: dict(zip(cols, r)) for r in por_elemento}

energia_por_ra = dict(con.sql(f"""
    SELECT regiao_administrativa, count(*) FROM {t_en} WHERE regiao_administrativa != '' GROUP BY 1
""").fetchall())

n_municipios_ra = dict(con.sql("""
    SELECT regiao_administrativa, count(*) FROM read_csv('municipios_regiao_administrativa.csv', header=true) GROUP BY 1
""").fetchall())


def calcula_nivel(d, n_energia):
    """Nivel = quantos dos 4 elementos a regiao tem (contagem direta, sem hierarquia
    implicita) -> evita rotular errado uma regiao que tem tratamento mas nao organicos,
    ou vice-versa, como se fosse "basica"."""
    organicos = d['organicos_compost'] + n_energia
    elementos = [d['coleta'] > 0, d['reciclagem'] > 0, d['tratamento'] > 0, organicos > 0]
    nivel = sum(elementos)
    return nivel, organicos


geojson = json.load(open(GEOJSON_RA, encoding='utf-8'))
resumo = []
for feat in geojson['features']:
    ra = feat['properties']['regiao_administrativa']
    d = dados_ra.get(ra, {'coleta': 0, 'reciclagem': 0, 'tratamento': 0, 'organicos_compost': 0, 'total_residuos': 0})
    n_energia = energia_por_ra.get(ra, 0)
    nivel, organicos = calcula_nivel(d, n_energia)
    n_mun = n_municipios_ra.get(ra, 1)
    total_iniciativas = d['total_residuos'] + n_energia
    densidade = round(total_iniciativas / n_mun, 1)
    nivel_desc, nivel_cor = NIVEL_INFO[nivel]
    faltando = []
    if d['coleta'] == 0:
        faltando.append('Coleta')
    if d['reciclagem'] == 0:
        faltando.append('Reciclagem')
    if d['tratamento'] == 0:
        faltando.append('Tratamento/Disposição')
    if organicos == 0:
        faltando.append('Orgânicos')
    feat['properties'].update({
        'nivel': nivel, 'nivel_desc': nivel_desc,
        'coleta': d['coleta'], 'reciclagem': d['reciclagem'], 'tratamento': d['tratamento'],
        'organicos': organicos, 'organicos_compost': d['organicos_compost'], 'organicos_energia': n_energia,
        'total_iniciativas': total_iniciativas, 'n_municipios': n_mun, 'densidade': densidade,
        'faltando': ', '.join(faltando) if faltando else 'nenhum elemento',
    })
    resumo.append((ra, nivel, nivel_desc, d['coleta'], d['reciclagem'], d['tratamento'], organicos, densidade))

resumo.sort(key=lambda x: (-x[1], -x[7]))
print(f"{len(resumo)} Regioes Administrativas classificadas:")
for ra, nivel, desc, coleta, reciclagem, tratamento, organicos, dens in resumo:
    print(f"  [{nivel}] {ra:28s} {desc:26s} coleta={coleta:4d} reciclagem={reciclagem:4d} "
          f"tratamento={tratamento:3d} organicos={organicos:3d}  densidade={dens}/municipio")

match_nivel = ['match', ['get', 'nivel']]
for nivel, (desc, cor) in NIVEL_INFO.items():
    match_nivel += [nivel, cor]
match_nivel.append('#999999')

legenda_html = ''.join(f'''
<div class="legenda-item">
  <span class="swatch" style="background:{cor}"></span>
  <span class="desc">{desc}</span>
</div>''' for nivel, (desc, cor) in sorted(NIVEL_INFO.items(), reverse=True))

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
  .setor-titulo {{
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em;
    color: #888; margin: 14px 0 6px; padding-top: 8px; border-top: 1px solid #eee;
  }}
  .setor-titulo:first-of-type {{ margin-top: 0; padding-top: 0; border-top: none; }}
  .legenda-item {{ display: flex; align-items: center; gap: 8px; padding: 4px 2px; font-size: 12px; }}
  .swatch {{ width: 13px; height: 13px; border-radius: 3px; flex-shrink: 0; }}
  .desc {{ color: #333; }}
  .aviso {{
    font-size: 11px; color: #666; background: #FFF8E1; border-radius: 6px; padding: 8px 10px;
    margin-top: 12px; line-height: 1.4;
  }}
  .nav-link {{
    display: block; text-align: center; font-size: 11.5px; margin-top: 10px; padding: 7px;
    border: 1px solid #ccc; border-radius: 6px; color: #1B5E20; text-decoration: none;
  }}
  .nav-link:hover {{ background: #f0f0f0; }}
  .maplibregl-popup-content {{ font-family: inherit; font-size: 12.5px; padding: 12px 14px; }}
  .popup-nome {{ font-weight: 700; margin: 0 0 2px; font-size: 14px; }}
  .popup-nivel {{ font-size: 12px; margin: 0 0 8px; font-weight: 700; }}
  .popup-tabela {{ width: 100%; border-collapse: collapse; }}
  .popup-tabela td {{ padding: 2px 0; border-bottom: 1px solid #eee; }}
  .popup-tabela td:last-child {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .popup-faltando {{ color: #C62828; font-size: 11px; margin-top: 8px; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="painel">
  <div class="painel-header">
    <div>
      <h1>Hub Circular por RA</h1>
      <p class="sub">Índice de maturidade — infraestrutura de economia circular por região</p>
    </div>
    <button id="toggle-painel" title="Recolher/expandir menu">✕</button>
  </div>
  <div id="painel-conteudo">
    <div class="setor-titulo">Nível de maturidade</div>
    {legenda_html}
    <div class="aviso">
      Clique numa região para ver o detalhamento (coleta, reciclagem, tratamento, orgânicos e densidade por município).
      Nível calculado pela presença de 4 elementos: Coleta, Reciclagem, Tratamento/Disposição e Orgânicos
      (compostagem + usinas de biogás/biomassa).
    </div>
    <a class="nav-link" href="mapa_economia_circular.html">Ver mapa de pontos →</a>
    <a class="nav-link" href="mapa_calor.html">Ver mapa de calor →</a>
  </div>
</div>
<script>
const geojson = {json.dumps(geojson, ensure_ascii=False)};
const matchNivel = {json.dumps(match_nivel)};
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
  map.addSource('regioes', {{ type: 'geojson', data: geojson }});

  map.addLayer({{
    id: 'regioes-fill',
    type: 'fill',
    source: 'regioes',
    paint: {{ 'fill-color': matchNivel, 'fill-opacity': 0.75 }},
  }});
  map.addLayer({{
    id: 'regioes-linha',
    type: 'line',
    source: 'regioes',
    paint: {{ 'line-color': '#ffffff', 'line-width': 1.5 }},
  }});

  const bounds = new maplibregl.LngLatBounds();
  geojson.features.forEach(f => {{
    const coords = JSON.stringify(f.geometry.coordinates).match(/-?\\d+\\.\\d+/g).map(Number);
    for (let i = 0; i < coords.length; i += 2) bounds.extend([coords[i], coords[i+1]]);
  }});
  if (!bounds.isEmpty()) map.fitBounds(bounds, {{ padding: 40, maxZoom: 9 }});

  const popup = new maplibregl.Popup({{ closeButton: true, closeOnClick: true, maxWidth: '300px' }});
  map.on('click', 'regioes-fill', (e) => {{
    const p = e.features[0].properties;
    const html = `
      <p class="popup-nome">${{p.regiao_administrativa}}</p>
      <p class="popup-nivel">Nível ${{p.nivel}} — ${{p.nivel_desc}}</p>
      <table class="popup-tabela">
        <tr><td>Coleta</td><td>${{p.coleta}}</td></tr>
        <tr><td>Reciclagem</td><td>${{p.reciclagem}}</td></tr>
        <tr><td>Tratamento/Disposição</td><td>${{p.tratamento}}</td></tr>
        <tr><td>Orgânicos (compost. + energia)</td><td>${{p.organicos}}</td></tr>
        <tr><td>Total de iniciativas</td><td>${{p.total_iniciativas}}</td></tr>
        <tr><td>Municípios na região</td><td>${{p.n_municipios}}</td></tr>
        <tr><td>Densidade (iniciativas/município)</td><td>${{p.densidade}}</td></tr>
      </table>
      ${{p.faltando !== 'nenhum elemento' ? `<p class="popup-faltando">Faltando: ${{p.faltando}}</p>` : ''}}
    `;
    popup.setLngLat(e.lngLat).setHTML(html).addTo(map);
  }});
  map.on('mouseenter', 'regioes-fill', () => map.getCanvas().style.cursor = 'pointer');
  map.on('mouseleave', 'regioes-fill', () => map.getCanvas().style.cursor = '');

  map.resize();
  map.triggerRepaint();
  setTimeout(() => {{ map.resize(); map.triggerRepaint(); }}, 150);
  setTimeout(() => map.triggerRepaint(), 500);
}}
if (map.isStyleLoaded()) {{ iniciarMapa(); }} else {{ map.once('style.load', iniciarMapa); }}
</script>
</body>
</html>
'''

with open(SAIDA, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"\n-> {SAIDA}")
