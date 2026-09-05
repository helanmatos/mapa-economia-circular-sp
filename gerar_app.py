#!/usr/bin/env python3
"""Gera o app unificado do Mapa da Economia Circular — SP.

Quatro temas numa página só, compartilhando a mesma fonte de dados:
  1. Hub Circular   — maturidade por RA -> município -> empresas (drill-down)
  2. Tratamento     — 5 camadas combináveis + sub-camada de materiais
  3. Ciclo biológico— compostagem, biogás e biomassa, dimensionados por potência
  4. Contexto       — população e IDH por município (quando os dados existem)

Trocar de tema não recarrega dado nenhum: as camadas do MapLibre já estão
montadas sobre as mesmas fontes e o que muda é filtro, cor e visibilidade.
Por isso a transição é instantânea e o enquadramento do mapa é preservado.
"""
import json
import os

import duckdb

from dados_app import CAMADAS, MATERIAIS, CICLOS, carrega
from maturidade import NIVEL_INFO, CLASSE_INFO, ESTAGIO_INFO, ESTAGIOS, PALETA

SAIDA = 'index.html'
GEOJSON_RA = 'geo_cache/regioes_administrativas.geojson'
CONTEXTO_CSV = 'contexto_municipios.csv'

con = duckdb.connect()
D = carrega(con)
mat = D['maturidade']
geojson_mun = mat['geojson_mun']
niveis_por_ra = mat['niveis_por_ra']

# ---------- Regiões Administrativas ----------
from maturidade import ELEMENTOS, calcula_nivel, elementos_faltando, pinta, estagio

T_RES = "read_csv('empresas_sp_circular_enriquecido.csv', header=true, all_varchar=true)"
T_EN = "read_csv('energia_biomassa_biogas_enriquecido.csv', header=true, all_varchar=true)"

por_elemento_ra = con.sql(f"""
    SELECT regiao_administrativa,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['coleta']} THEN 1 ELSE 0 END) coleta,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['reciclagem']} THEN 1 ELSE 0 END) reciclagem,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['tratamento_disposicao']} THEN 1 ELSE 0 END) tratamento,
      sum(CASE WHEN cnae_principal IN {ELEMENTOS['organicos_cnpj']} THEN 1 ELSE 0 END) organicos_compost,
      count(*) total_residuos
    FROM {T_RES} WHERE latitude != '' AND regiao_administrativa != '' GROUP BY 1
""").fetchall()
dados_ra = {r[0]: dict(zip(['coleta', 'reciclagem', 'tratamento', 'organicos_compost',
                            'total_residuos'], r[1:])) for r in por_elemento_ra}
energia_por_ra = dict(con.sql(f"SELECT regiao_administrativa, count(*) FROM {T_EN} "
                              f"WHERE regiao_administrativa != '' GROUP BY 1").fetchall())

geojson_ra = json.load(open(GEOJSON_RA, encoding='utf-8'))
for feat in geojson_ra['features']:
    ra = feat['properties']['regiao_administrativa']
    d = dados_ra.get(ra, {'coleta': 0, 'reciclagem': 0, 'tratamento': 0,
                          'organicos_compost': 0, 'total_residuos': 0})
    n_energia = energia_por_ra.get(ra, 0)
    organicos = d['organicos_compost'] + n_energia
    cor_ra = pinta(niveis_por_ra.get(ra, [0]), ra=True)
    est_ra = estagio(d['coleta'], d['reciclagem'], d['tratamento'], organicos)
    est_mun = mat['estagios_por_ra'].get(ra, [])
    feat['properties'].update({
        'coleta': d['coleta'], 'reciclagem': d['reciclagem'], 'tratamento': d['tratamento'],
        'organicos': organicos, 'total_iniciativas': d['total_residuos'] + n_energia,
        'faltando': elementos_faltando(d['coleta'], d['reciclagem'], d['tratamento'], organicos),
        'servicos_presentes': calcula_nivel(d['coleta'], d['reciclagem'], d['tratamento'], organicos),
        'estagio': est_ra,
        'estagio_nome': ESTAGIO_INFO[est_ra][0],
        'dist_estagio': [sum(1 for e in est_mun if e == k) for k in ESTAGIOS],
        **cor_ra,
    })

# ---------- contexto socioeconômico (opcional) ----------
TEM_CONTEXTO = os.path.exists(CONTEXTO_CSV)
if TEM_CONTEXTO:
    import csv
    # join por CÓDIGO IBGE de 7 dígitos, não por nome: é o mesmo identificador na
    # malha, na API do IBGE e no Ipeadata, então não há como perder município por
    # acento ou grafia — foi assim que 105 usinas sumiram antes
    ctx = {}
    with open(CONTEXTO_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            ctx[row['cod_ibge']] = row

    def _num(v, conv):
        return conv(v) if v not in (None, '') else None

    achou = 0
    for feat in geojson_mun['features']:
        c = ctx.get(feat['properties']['codarea'])
        if c:
            achou += 1
        c = c or {}
        feat['properties']['populacao'] = _num(c.get('populacao'), int)
        feat['properties']['idhm'] = _num(c.get('idhm'), float)
        feat['properties']['idhm_renda'] = _num(c.get('idhm_renda'), float)
        feat['properties']['idhm_educacao'] = _num(c.get('idhm_educacao'), float)
        feat['properties']['idhm_longevidade'] = _num(c.get('idhm_longevidade'), float)
        feat['properties']['ano_populacao'] = c.get('ano_populacao', '')
        feat['properties']['ano_idhm'] = c.get('ano_idhm', '')
    print(f'contexto: {achou} de {len(geojson_mun["features"])} municípios casados')
else:
    for feat in geojson_mun['features']:
        for campo in ('populacao', 'idhm', 'idhm_renda', 'idhm_educacao', 'idhm_longevidade'):
            feat['properties'][campo] = None

print(f"RAs: {len(geojson_ra['features'])} | Municípios: {len(geojson_mun['features'])} "
      f"| Pontos: {len(D['pontos']['features'])} | contexto: {TEM_CONTEXTO}")

# ---------- expressões de cor ----------
match_classe = ['match', ['get', 'classe']]
for n, (_desc, cor) in NIVEL_INFO.items():
    match_classe += [n, cor]
match_classe.append('#999999')

match_estagio = ['match', ['get', 'estagio']]
for k, (_nome, _d, cor) in ESTAGIO_INFO.items():
    match_estagio += [k, cor]
match_estagio.append('#999999')

match_camada = ['match', ['get', 'camada']]
for k, v in CAMADAS.items():
    match_camada += [k, v['cor']]
match_camada.append('#999999')

match_material = ['match', ['get', 'material']]
for k, v in MATERIAIS.items():
    match_material += [k, v['cor']]
match_material.append('#999999')

match_ciclo = ['match', ['get', 'ciclo']]
for k, v in CICLOS.items():
    match_ciclo += [k, v['cor']]
match_ciclo.append('#999999')


def item_legenda(cor, texto, extra=''):
    return (f'<div class="leg-item"><span class="sw" style="background:{cor}"></span>'
            f'<span class="leg-txt">{texto}{extra}</span></div>')


leg_classe = ''.join(item_legenda(cor, f'<b>{n}</b> · {desc}')
                     for n, (desc, cor) in sorted(CLASSE_INFO.items(), reverse=True))
leg_nivel = ''.join(item_legenda(cor, f'<b>{n}</b> · {desc}')
                    for n, (desc, cor) in sorted(NIVEL_INFO.items(), reverse=True))
leg_estagio = ''.join(item_legenda(cor, f'<b>{nome}</b><span class="leg-sub">{desc}</span>')
                      for k, (nome, desc, cor) in
                      sorted(ESTAGIO_INFO.items(), key=lambda x: -ESTAGIOS.index(x[0])))

def milhar(n):
    """Formata o milhar SEM tocar na pontuação do texto ao redor. Encadear
    .replace(',', '.') numa f-string inteira troca também as vírgulas da prosa —
    "Bagaço de cana, resíduos florestais" virava "Bagaço de cana. resíduos florestais"."""
    return f'{n:,}'.replace(',', '.')


def bloco_chk(attr, itens, contagens, com_desc=True):
    saida = []
    for k, v in itens.items():
        desc = (f'<span class="leg-sub">{v["desc"]}</span>'
                if com_desc and v.get('desc') else '')
        saida.append(
            f'<label class="chk"><input type="checkbox" data-{attr}="{k}" checked>'
            f'<span class="sw" style="background:{v["cor"]}"></span>'
            f'<span class="chk-txt"><b>{v["nome"]}</b>{desc}</span>'
            f'<span class="cnt">{milhar(contagens[k])}</span></label>')
    return ''.join(saida)


chk_camadas = bloco_chk('camada', CAMADAS, D['conta_camada'])
chk_materiais = bloco_chk('material', MATERIAIS, D['conta_material'], com_desc=False)
chk_ciclos = bloco_chk('ciclo', CICLOS, D['conta_ciclo'])

# os pins do hub usam a mesma cor das camadas do Mapa 2 — a legenda tem que existir
# tambem no hub, senao o usuario ve pontos coloridos sem saber o que significam
leg_pins = ''.join(item_legenda(v['cor'], v['nome']) for v in CAMADAS.values())

# ---------- cruzamento maturidade x contexto (o pedido da reunião) ----------
import math
import statistics as _st


def _pearson(xs, ys):
    mx, my = _st.mean(xs), _st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0


cruz = None
if TEM_CONTEXTO:
    _l = [(f['properties']['idhm'], f['properties']['populacao'], f['properties']['nivel'])
          for f in geojson_mun['features']
          if f['properties'].get('idhm') and f['properties'].get('populacao')]
    _idhm = [x[0] for x in _l]
    _logpop = [math.log10(max(x[1], 1)) for x in _l]
    _niv = [x[2] for x in _l]
    cruz = {
        'r_idhm': _pearson(_idhm, _niv),
        'r_pop': _pearson(_logpop, _niv),
        'pop_med_n0': int(_st.median([x[1] for x in _l if x[2] == 0])),
        'pop_med_n4': int(_st.median([x[1] for x in _l if x[2] == 4])),
        'idhm_med_n0': _st.mean([x[0] for x in _l if x[2] == 0]),
        'idhm_med_n4': _st.mean([x[0] for x in _l if x[2] == 4]),
    }
    print(f"cruzamento: r(IDHM)={cruz['r_idhm']:+.3f} r(log pop)={cruz['r_pop']:+.3f}")

mw_total = round(sum(D['mw_ciclo'].values()), 1)
opcoes_ra = ''.join(f'<option value="{f["properties"]["regiao_administrativa"]}">'
                    f'{f["properties"]["regiao_administrativa"]}</option>'
                    for f in sorted(geojson_ra['features'],
                                    key=lambda f: f['properties']['regiao_administrativa']))

CSS = r'''
*{box-sizing:border-box}
html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:#1a1a1a}
#app{position:absolute;inset:0;display:flex;flex-direction:column}

/* ---------- cabecalho e abas ---------- */
#topo{background:#fff;border-bottom:1px solid #e3e3e3;box-shadow:0 1px 3px rgba(0,0,0,.05);z-index:3;flex-shrink:0}
#topo-linha{display:flex;align-items:center;gap:14px;padding:10px 16px 0}
#marca{font-size:15px;font-weight:700;color:#1B5E20;letter-spacing:-.01em;white-space:nowrap}
#marca span{display:block;font-size:11px;font-weight:400;color:#777;letter-spacing:0}
#abas-wrap{position:relative}
#abas-wrap::after{content:'';position:absolute;right:0;top:0;bottom:0;width:38px;pointer-events:none;
  background:linear-gradient(to right,rgba(255,255,255,0),#fff 72%);opacity:0;transition:opacity .2s}
#abas-wrap.tem-mais::after{opacity:1}
#abas{display:flex;gap:2px;padding:0 10px;overflow-x:auto;scrollbar-width:none;scroll-behavior:smooth}
#abas::-webkit-scrollbar{display:none}
.aba{appearance:none;background:none;border:0;border-bottom:2.5px solid transparent;padding:11px 14px 9px;
  font-size:13px;font-weight:600;color:#6b6b6b;cursor:pointer;white-space:nowrap;transition:color .15s,border-color .15s}
.aba:hover{color:#1B5E20}
.aba.ativa{color:#1B5E20;border-bottom-color:#1B5E20}
.aba-sub{display:block;font-size:10.5px;font-weight:400;color:#999;margin-top:1px}
.aba.ativa .aba-sub{color:#4c8c50}

/* ---------- corpo ---------- */
#corpo{position:relative;flex:1;min-height:0}
#map{position:absolute;inset:0}
#painel{position:absolute;top:14px;left:14px;z-index:2;width:326px;max-height:calc(100% - 28px);
  background:rgba(255,255,255,.975);border-radius:12px;box-shadow:0 4px 22px rgba(0,0,0,.15);
  display:flex;flex-direction:column;overflow:hidden;transition:width .18s ease}
#painel-topo{display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding:13px 15px 9px;border-bottom:1px solid #eee;flex-shrink:0}
#painel-titulo{font-size:13.5px;font-weight:700;color:#1B5E20}
#painel-corpo{overflow-y:auto;padding:12px 15px 15px}
#recolher{appearance:none;background:none;border:1px solid #d5d5d5;border-radius:7px;width:28px;height:28px;
  font-size:13px;line-height:1;color:#1B5E20;cursor:pointer;flex-shrink:0}
#recolher:hover{background:#f2f2f2}
#painel.recolhido{width:auto}
#painel.recolhido #painel-corpo{display:none}
#painel.recolhido #painel-topo{border-bottom:0;padding-bottom:13px}

.secao{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#8a8a8a;
  margin:15px 0 7px;padding-top:11px;border-top:1px solid #eee}
.secao:first-child{margin-top:0;padding-top:0;border-top:0}
.leg-item{display:flex;align-items:flex-start;gap:8px;padding:3.5px 1px;font-size:12px;line-height:1.35}
.sw{width:13px;height:13px;border-radius:3.5px;flex-shrink:0;margin-top:1px}
.leg-txt{color:#333}
.leg-sub{display:block;font-size:10.5px;color:#8a8a8a;line-height:1.3}
.sw.hach-liso{background:#8a8a8a}
.sw.hach-leve{background:repeating-linear-gradient(-45deg,#8a8a8a 0 4px,#fff 4px 5.5px)}
.sw.hach-forte{background:repeating-linear-gradient(-45deg,#8a8a8a 0 2px,#fff 2px 3.5px)}

.chk{display:flex;align-items:flex-start;gap:8px;padding:6px 7px;border-radius:7px;font-size:12px;
  cursor:pointer;line-height:1.35;transition:background .12s}
.chk:hover{background:#f4f4f4}
.chk input{margin:1px 0 0;flex-shrink:0;accent-color:#1B5E20;cursor:pointer}
.chk .sw{margin-top:2px}
.chk-txt{flex:1}
.cnt{font-size:11px;color:#888;font-variant-numeric:tabular-nums;flex-shrink:0;margin-top:1px}
.chk input:not(:checked)~.chk-txt,.chk input:not(:checked)~.cnt{opacity:.42}
.chk input:not(:checked)~.sw{opacity:.28}

.sub-bloco{margin-left:8px;padding-left:9px;border-left:2px solid #e4e4e4}
.sub-bloco.off{display:none}
.nota{font-size:10.5px;color:#8a6d3b;background:#FFF8E1;border-radius:6px;padding:8px 10px;
  margin:7px 0 0;line-height:1.42}
.dica{font-size:10.8px;color:#8a8a8a;margin:8px 0 0;line-height:1.4}

#trilha{display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-size:12px;margin-bottom:10px}
#trilha .passo{color:#1B5E20;cursor:pointer;text-decoration:underline;text-underline-offset:2px}
#trilha .passo.atual{color:#333;font-weight:700;text-decoration:none;cursor:default}
#trilha .sep{color:#bbb}
#voltar{display:none;width:100%;margin-bottom:9px;padding:8px 10px;font-size:12.5px;text-align:left;
  border:1px solid #1B5E20;border-radius:7px;background:#E8F5E9;color:#1B5E20;cursor:pointer;font-weight:700}
#voltar:hover{background:#C8E6C9}

.filtro-linha{display:flex;gap:7px;margin-bottom:9px}
select.ctrl{flex:1;min-width:0;font:inherit;font-size:12px;padding:7px 8px;border:1px solid #d5d5d5;
  border-radius:7px;background:#fff;color:#333;cursor:pointer}
.seg{display:flex;border:1px solid #d5d5d5;border-radius:7px;overflow:hidden}
.seg button{appearance:none;background:#fff;border:0;padding:7px 11px;font:inherit;font-size:11.5px;
  color:#666;cursor:pointer;transition:background .12s,color .12s}
.seg button+button{border-left:1px solid #e3e3e3}
.seg button.on{background:#1B5E20;color:#fff;font-weight:600}

.kpis{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:9px 0 3px}
.kpi{background:#F5F7F5;border-radius:8px;padding:9px 10px}
.kpi b{display:block;font-size:17px;color:#1B5E20;font-variant-numeric:tabular-nums;line-height:1.15}
.kpi span{font-size:10.5px;color:#777;line-height:1.3;display:block;margin-top:1px}
.barra{display:flex;height:9px;border-radius:4px;overflow:hidden;margin:9px 0 5px;background:#eee}
.barra span{display:block}
.vazio{font-size:12px;color:#B00020;background:#FFEBEE;border-radius:7px;padding:9px 11px;
  margin-top:8px;line-height:1.4}

/* ---------- popups ---------- */
.maplibregl-popup-content{font-family:inherit;font-size:12.5px;padding:12px 14px;border-radius:9px;
  box-shadow:0 4px 18px rgba(0,0,0,.16)}
.pop-nome{font-weight:700;margin:0 0 2px;font-size:14px;line-height:1.25}
.pop-sub{font-size:11px;color:#888;margin:0 0 5px}
.pop-classe{font-size:12px;margin:0 0 7px;font-weight:700}
.pop-tab{width:100%;border-collapse:collapse;margin-top:2px}
.pop-tab td{padding:2.5px 0;border-bottom:1px solid #eee}
.pop-tab td:last-child{text-align:right;font-variant-numeric:tabular-nums}
.pop-falta{color:#B00020;font-size:11px;margin-top:7px}
.pop-info{font-size:11px;color:#555;margin:0 0 4px}
.pop-info b{color:#1B5E20}
.pop-cob b{color:#B00020}
.pop-det{color:#1B5E20;font-size:11.5px;margin:0 0 3px}
.pop-end{color:#555;font-size:12px;margin:0}
.pop-aprox{color:#b26a00;font-size:10.5px;margin-top:4px}
.pop-dica{font-size:10.8px;color:#8a8a8a;margin:7px 0 0}
.pop-ano{font-size:10.3px;color:#999;font-weight:400;margin:0}

@media (max-width:760px){
  #topo-linha{padding:8px 12px 0}
  #marca{font-size:13.5px}
  #painel{top:10px;left:10px;right:10px;width:auto;max-height:calc(100% - 20px)}
  #painel.recolhido{width:auto;right:auto}
  .kpis{grid-template-columns:1fr 1fr}
}
'''

JS = r'''
const geojsonRA = __RA__;
const geojsonMun = __MUN__;
const geojsonPontos = __PONTOS__;
const matchClasse = __MATCH_CLASSE__;
const matchEstagio = __MATCH_ESTAGIO__;
const matchCamada = __MATCH_CAMADA__;
const matchMaterial = __MATCH_MATERIAL__;
const matchCiclo = __MATCH_CICLO__;
const PALETA = __PALETA__;
const ESTAGIOS = __ESTAGIOS__;
const ESTAGIO_NOMES = __ESTAGIO_NOMES__;
const TEM_CONTEXTO = __TEM_CONTEXTO__;

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  center: [-48.6, -22.3], zoom: 6,
});
map.addControl(new maplibregl.NavigationControl(), 'top-right');

/* ================= estado ================= */
let tema = 'hub';
let nivel = 'estado';          // hub: estado | regiao | municipio
let raSel = null, munSel = null, munNome = null;
let corHub = 'classe';         // classe | estagio
let modo = 'pontos';           // pontos | calor  (temas tratamento/biologico)
let filtroRA = '';             // filtro global de RA nos temas de pontos

const $ = (s) => document.querySelector(s);
const num = (v, c = 1) => Number(v).toFixed(c).replace('.', ',');
const inteiro = (v) => Number(v).toLocaleString('pt-BR');
const lista = (d) => (typeof d === 'string' ? JSON.parse(d) : d);

/* ================= utilidades de mapa ================= */
function limites(feat) {
  const b = new maplibregl.LngLatBounds();
  (function anda(c) {
    if (typeof c[0] === 'number') { b.extend(c); return; }
    c.forEach(anda);
  })(feat.geometry.coordinates);
  return b;
}
function limitesDe(feats) {
  const b = new maplibregl.LngLatBounds();
  feats.forEach(f => b.extend(limites(f)));
  return b;
}
function enquadrarEstado(anim) {
  map.resize();
  map.fitBounds(limitesDe(geojsonRA.features), {padding: 40, maxZoom: 9, duration: anim ? 600 : 0});
}
const vis = (id, v) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', v ? 'visible' : 'none'); };

/* ================= hachura ================= */
function registraHachura(nome, tile, largura, alpha, passos) {
  const c = document.createElement('canvas');
  c.width = c.height = tile;
  const x = c.getContext('2d');
  x.clearRect(0, 0, tile, tile);
  x.strokeStyle = `rgba(255,255,255,${alpha})`;
  x.lineWidth = largura;
  const passo = (2 * tile) / passos;
  for (let k = 0; k <= 2 * tile; k += passo) {
    x.beginPath(); x.moveTo(k - tile - 1, tile + 1); x.lineTo(k + 1, -1); x.stroke();
  }
  map.addImage(nome, x.getImageData(0, 0, tile, tile), {pixelRatio: 2});
}

/* ================= popups ================= */
const popRegiao = new maplibregl.Popup({closeButton: false, closeOnClick: false, maxWidth: '310px'});
const popPonto = new maplibregl.Popup({closeButton: true, closeOnClick: true, maxWidth: '290px'});

function barraEstagio(dist, n) {
  const fat = dist.map((c, i) => c
    ? `<span style="width:${(100 * c / n).toFixed(2)}%;background:${PALETA[i]}" title="${c} município(s): ${ESTAGIO_NOMES[i]}"></span>`
    : '').join('');
  return `<div class="barra">${fat}</div>`;
}

function htmlRegiao(p, tipo) {
  const ehMun = tipo === 'municipio';
  const titulo = ehMun ? p.nome : p.regiao_administrativa;
  const sub = ehMun
    ? `<p class="pop-sub">${p.regiao_administrativa}</p>`
    : `<p class="pop-sub">${p.n_mun} municípios · média ${num(p.media, 2)} de 4 serviços</p>`;
  let cabeca;
  if (corHub === 'estagio') {
    const i = ESTAGIOS.indexOf(p.estagio);
    cabeca = `<p class="pop-classe" style="color:${PALETA[i]}">${ESTAGIO_NOMES[i]}</p>`;
  } else {
    cabeca = `<p class="pop-classe" style="color:${PALETA[p.classe]}">`
      + `${ehMun ? 'Nível' : 'Classe'} ${p.classe} — ${p.classe_desc}</p>`;
  }
  const ctx = (TEM_CONTEXTO && ehMun && (p.populacao || p.idhm)) ? `
    <p class="pop-info">${p.populacao ? inteiro(p.populacao) + ' habitantes' : ''}${p.populacao && p.idhm ? ' · ' : ''}${p.idhm ? 'IDHM ' + num(p.idhm, 3) : ''}</p>` : '';
  const bloco = ehMun ? '' : `
    ${barraEstagio(lista(p.dist_estagio), p.n_mun)}
    <p class="pop-info pop-cob"><b>${p.n_vazios} de ${p.n_mun} municípios (${num(p.pct_vazio)}%)</b> sem nenhum registro</p>
    <p class="pop-info">Serviços presentes em algum ponto da região: <b>${p.servicos_presentes} de 4</b></p>`;
  return `
    <p class="pop-nome">${titulo}</p>${sub}${cabeca}${ctx}${bloco}
    <table class="pop-tab">
      <tr><td>Coleta</td><td>${inteiro(p.coleta)}</td></tr>
      <tr><td>Reciclagem</td><td>${inteiro(p.reciclagem)}</td></tr>
      <tr><td>Tratamento/Disposição</td><td>${inteiro(p.tratamento)}</td></tr>
      <tr><td>Orgânicos (compost. + energia)</td><td>${inteiro(p.organicos)}</td></tr>
      <tr><td><b>Total de iniciativas</b></td><td><b>${inteiro(p.total_iniciativas)}</b></td></tr>
    </table>
    ${p.faltando !== 'nenhum elemento' ? `<p class="pop-falta">Nenhum registro em toda a área: ${p.faltando}</p>` : ''}`;
}

function htmlPonto(p) {
  if (p.setor === 'energia') {
    return `<p class="pop-nome">${p.nome}</p>`
      + `<p class="pop-det">${p.detalhe} · ${num(p.mw, 1)} MW</p>`
      + `<p class="pop-end">${p.municipio}</p>`
      + (p.proprietario ? `<p class="pop-end">${p.proprietario}</p>` : '');
  }
  return `<p class="pop-nome">${p.nome}</p>`
    + `<p class="pop-det">${p.detalhe}</p>`
    + `<p class="pop-end">${p.endereco}</p>`
    + (p.aprox === true || p.aprox === 'true' ? '<p class="pop-aprox">Localização aproximada (centro do CEP)</p>' : '');
}

/* ================= filtros dos temas de pontos ================= */
function camadasLigadas() {
  return [...document.querySelectorAll('[data-camada]')].filter(c => c.checked).map(c => c.dataset.camada);
}
function materiaisLigados() {
  return [...document.querySelectorAll('[data-material]')].filter(c => c.checked).map(c => c.dataset.material);
}
function ciclosLigados() {
  return [...document.querySelectorAll('[data-ciclo]')].filter(c => c.checked).map(c => c.dataset.ciclo);
}

function filtroTratamento() {
  const cams = camadasLigadas();
  const mats = materiaisLigados();
  // triagem tem sub-camada: quando ligada, o ponto precisa passar TAMBÉM pelo material
  const semTriagem = cams.filter(c => c !== 'triagem');
  const cond = ['any',
    ['in', ['get', 'camada'], ['literal', semTriagem]],
    ['all', ['==', ['get', 'camada'], 'triagem'],
            ['in', ['get', 'material'], ['literal', cams.includes('triagem') ? mats : []]]]];
  return filtroRA ? ['all', cond, ['==', ['get', 'ra'], filtroRA]] : cond;
}
function filtroCiclo() {
  const cond = ['in', ['get', 'ciclo'], ['literal', ciclosLigados()]];
  return filtroRA ? ['all', cond, ['==', ['get', 'ra'], filtroRA]] : cond;
}

function aplicarFiltros() {
  if (!map.getLayer('pontos-tema')) return;
  const f = tema === 'tratamento' ? filtroTratamento()
          : tema === 'biologico' ? filtroCiclo()
          : ['==', ['get', 'setor'], '__nada__'];
  map.setFilter('pontos-tema', f);
  map.setFilter('calor-tema', f);
  atualizarContagem();
}

function atualizarContagem() {
  const alvo = tema === 'biologico' ? $('#contagem-bio') : $('#contagem');
  if (!alvo) return;
  let n = 0, mw = 0;
  const cams = camadasLigadas(), mats = materiaisLigados(), cics = ciclosLigados();
  for (const f of geojsonPontos.features) {
    const p = f.properties;
    if (filtroRA && p.ra !== filtroRA) continue;
    let ok = false;
    if (tema === 'tratamento') {
      ok = p.camada === 'triagem'
        ? (cams.includes('triagem') && mats.includes(p.material))
        : cams.includes(p.camada);
    } else if (tema === 'biologico') {
      ok = cics.includes(p.ciclo);
    }
    if (ok) { n++; mw += p.mw || 0; }
  }
  alvo.innerHTML = tema === 'biologico'
    ? `<div class="kpi"><b>${inteiro(n)}</b><span>unidades visíveis</span></div>`
      + `<div class="kpi"><b>${num(mw, 1)}</b><span>MW de potência</span></div>`
    : `<div class="kpi"><b>${inteiro(n)}</b><span>estabelecimentos visíveis</span></div>`
      + `<div class="kpi"><b>${cams.length}</b><span>de 5 camadas ativas</span></div>`;
}

/* ================= hub: navegação ================= */
function pintarHub() {
  const expr = corHub === 'estagio' ? matchEstagio : matchClasse;
  if (map.getLayer('ra-fill')) map.setPaintProperty('ra-fill', 'fill-color', expr);
  if (map.getLayer('mun-fill')) map.setPaintProperty('mun-fill', 'fill-color', expr);
  $('#leg-classe').style.display = (corHub === 'classe' && nivel === 'estado') ? '' : 'none';
  $('#leg-nivel').style.display = (corHub === 'classe' && nivel !== 'estado') ? '' : 'none';
  $('#leg-estagio').style.display = corHub === 'estagio' ? '' : 'none';
  $('#leg-hachura').style.display = corHub === 'classe' ? '' : 'none';
  $('#titulo-escala').textContent = corHub === 'estagio'
    ? 'Estágio da cadeia'
    : (nivel === 'estado' ? 'Maturidade da região' : 'Maturidade do município');
}

const OP_CHEIA = 0.75, OP_FRACA = 0.28;

function visibilidadeHub() {
  const est = nivel === 'estado', reg = nivel === 'regiao', mun = nivel === 'municipio';
  vis('ra-fill', est); vis('ra-hachura', est && corHub === 'classe'); vis('ra-linha', est);
  vis('mun-fill', reg || mun); vis('mun-hachura', (reg || mun) && corHub === 'classe'); vis('mun-linha', reg || mun);
  vis('pontos-hub', mun);
  if (map.getLayer('mun-fill')) {
    map.setPaintProperty('mun-fill', 'fill-opacity', mun ? OP_FRACA : OP_CHEIA);
    map.setFilter('mun-fill', mun ? ['==', ['get', 'municipio_norm'], munSel]
                                  : ['==', ['get', 'regiao_administrativa'], raSel || '']);
  }
  if (map.getLayer('mun-hachura')) {
    map.setPaintProperty('mun-hachura', 'fill-opacity', mun ? 0.3 : 0.85);
    map.setFilter('mun-hachura', ['all', ['!=', ['get', 'listras'], 'liso'],
      mun ? ['==', ['get', 'municipio_norm'], munSel]
          : ['==', ['get', 'regiao_administrativa'], raSel || '']]);
  }
  if (map.getLayer('mun-linha')) {
    map.setPaintProperty('mun-linha', 'line-opacity', mun ? 0.5 : 1);
    map.setFilter('mun-linha', mun ? ['==', ['get', 'municipio_norm'], munSel]
                                   : ['==', ['get', 'regiao_administrativa'], raSel || '']);
  }
  if (map.getLayer('pontos-hub')) {
    map.setFilter('pontos-hub', ['==', ['get', 'municipio_norm'], munSel || '__nada__']);
  }
  $('#leg-pins').style.display = mun ? '' : 'none';
  pintarHub();
  trilha();
}

function trilha() {
  const btn = $('#voltar');
  btn.style.display = nivel === 'estado' ? 'none' : 'block';
  btn.textContent = nivel === 'municipio' ? `← Voltar para ${raSel}` : '← Voltar para o estado';
  let h = nivel === 'estado'
    ? '<span class="passo atual">Estado de SP</span>'
    : '<span class="passo" data-ir="estado">Estado de SP</span>';
  if (raSel) {
    h += ' <span class="sep">›</span> ' + (nivel === 'regiao'
      ? `<span class="passo atual">${raSel}</span>`
      : `<span class="passo" data-ir="regiao">${raSel}</span>`);
  }
  if (munNome) h += ` <span class="sep">›</span> <span class="passo atual">${munNome}</span>`;
  const el = $('#trilha');
  el.innerHTML = h;
  el.querySelectorAll('.passo[data-ir]').forEach(p => p.addEventListener('click', () => {
    p.dataset.ir === 'estado' ? irEstado() : irRegiao(raSel);
  }));
}

function irEstado() {
  nivel = 'estado'; raSel = null; munSel = null; munNome = null;
  $('#hub-vazio').style.display = 'none';
  visibilidadeHub();
  enquadrarEstado(true);
}
function irRegiao(ra) {
  nivel = 'regiao'; raSel = ra; munSel = null; munNome = null;
  $('#hub-vazio').style.display = 'none';
  visibilidadeHub();
  const fs = geojsonMun.features.filter(f => f.properties.regiao_administrativa === ra);
  if (fs.length) map.fitBounds(limitesDe(fs), {padding: 30, maxZoom: 11, duration: 600});
}
function irMunicipio(norm, nome) {
  nivel = 'municipio'; munSel = norm; munNome = nome;
  visibilidadeHub();
  const f = geojsonMun.features.find(x => x.properties.municipio_norm === norm);
  const n = geojsonPontos.features.filter(x => x.properties.municipio_norm === norm).length;
  const vz = $('#hub-vazio');
  if (n === 0) {
    vz.style.display = '';
    vz.innerHTML = `<div class="vazio">Nenhuma empresa ou usina mapeada em <b>${nome}</b> nesta base.</div>`;
  } else vz.style.display = 'none';
  if (f) map.fitBounds(limites(f), {padding: 40, maxZoom: 14, duration: 600});
}

/* ================= troca de tema ================= */
const TEMAS = {
  hub: {titulo: 'Hub Circular'},
  tratamento: {titulo: 'Tratamento de resíduos'},
  biologico: {titulo: 'Ciclo biológico'},
  contexto: {titulo: 'Contexto socioeconômico'},
};

function trocarTema(novo) {
  if (novo === tema) return;
  tema = novo;
  popRegiao.remove(); popPonto.remove();
  document.querySelectorAll('.aba').forEach(a => a.classList.toggle('ativa', a.dataset.tema === novo));
  document.querySelectorAll('.painel-tema').forEach(p => p.style.display = p.dataset.tema === novo ? '' : 'none');
  $('#painel-titulo').textContent = TEMAS[novo].titulo;

  const ehHub = novo === 'hub';
  const ehCtx = novo === 'contexto';
  const ehPontos = novo === 'tratamento' || novo === 'biologico';

  // hub
  ['ra-fill', 'ra-hachura', 'ra-linha', 'mun-fill', 'mun-hachura', 'mun-linha', 'pontos-hub']
    .forEach(id => vis(id, false));
  vis('ctx-fill', ehCtx); vis('ctx-linha', ehCtx);
  vis('pontos-tema', ehPontos && modo === 'pontos');
  vis('calor-tema', ehPontos && modo === 'calor');

  if (ehHub) { visibilidadeHub(); }
  if (ehPontos) {
    map.setPaintProperty('pontos-tema', 'circle-color', novo === 'biologico' ? matchCiclo : matchCamada);
    // no ciclo biológico o raio conta potência: uma usina de 300 MW não pode ter o
    // mesmo peso visual de uma de 0,5 MW
    map.setPaintProperty('pontos-tema', 'circle-radius', novo === 'biologico'
      ? ['interpolate', ['linear'], ['zoom'],
          6, ['interpolate', ['linear'], ['get', 'mw'], 0, 3.5, 100, 11],
          12, ['interpolate', ['linear'], ['get', 'mw'], 0, 7, 100, 26]]
      : ['interpolate', ['linear'], ['zoom'], 6, 2.6, 10, 4.5, 15, 9]);
    aplicarFiltros();
  }
  if (ehCtx) aplicarContexto();

  // cada tema tem um escopo natural: o hub retoma onde o drill-down parou, os demais
  // são visões estaduais (ou da RA filtrada). Sem isto o mapa herdava o enquadramento
  // do tema anterior e o estado aparecia minúsculo num canto.
  if (!ehHub) {
    const fs = filtroRA
      ? geojsonMun.features.filter(f => f.properties.regiao_administrativa === filtroRA)
      : null;
    if (fs && fs.length) map.fitBounds(limitesDe(fs), {padding: 30, maxZoom: 10, duration: 500});
    else enquadrarEstado(true);
  }
}

/* ================= contexto ================= */
let varCtx = 'populacao';
function aplicarContexto() {
  if (!map.getLayer('ctx-fill')) return;
  const expr = varCtx === 'idhm'
    ? ['case', ['==', ['get', 'idhm'], null], '#e0e0e0',
        ['interpolate', ['linear'], ['get', 'idhm'],
          0.60, '#B00020', 0.68, '#E65100', 0.74, '#F5C518', 0.80, '#8BC34A', 0.86, '#1B5E20']]
    : ['case', ['==', ['get', 'populacao'], null], '#e0e0e0',
        ['interpolate', ['linear'], ['log10', ['max', ['get', 'populacao'], 1]],
          3, '#EDF8E9', 4, '#BAE4B3', 4.7, '#74C476', 5.5, '#31A354', 7, '#006D2C']];
  map.setPaintProperty('ctx-fill', 'fill-color', expr);
  document.querySelectorAll('[data-ctxleg]').forEach(e => {
    e.style.display = e.dataset.ctxleg === varCtx ? '' : 'none';
  });
}

/* ================= montagem ================= */
function iniciar() {
  registraHachura('hach-leve', 32, 3, 0.6, 2);
  registraHachura('hach-forte', 32, 4, 0.9, 4);

  map.addSource('ra', {type: 'geojson', data: geojsonRA});
  map.addSource('mun', {type: 'geojson', data: geojsonMun});
  map.addSource('pontos', {type: 'geojson', data: geojsonPontos});

  const hachPaint = {
    'fill-pattern': ['match', ['get', 'listras'], 'forte', 'hach-forte', 'hach-leve'],
    'fill-opacity': 0.85,
  };

  map.addLayer({id: 'ctx-fill', type: 'fill', source: 'mun',
    paint: {'fill-color': '#e0e0e0', 'fill-opacity': 0.8}, layout: {visibility: 'none'}});
  map.addLayer({id: 'ctx-linha', type: 'line', source: 'mun',
    paint: {'line-color': '#fff', 'line-width': 0.5}, layout: {visibility: 'none'}});

  map.addLayer({id: 'ra-fill', type: 'fill', source: 'ra',
    paint: {'fill-color': matchClasse, 'fill-opacity': OP_CHEIA}});
  map.addLayer({id: 'ra-hachura', type: 'fill', source: 'ra',
    filter: ['!=', ['get', 'listras'], 'liso'], paint: hachPaint});
  map.addLayer({id: 'ra-linha', type: 'line', source: 'ra',
    paint: {'line-color': '#fff', 'line-width': 1.5}});

  map.addLayer({id: 'mun-fill', type: 'fill', source: 'mun',
    paint: {'fill-color': matchClasse, 'fill-opacity': OP_CHEIA}, layout: {visibility: 'none'}});
  map.addLayer({id: 'mun-hachura', type: 'fill', source: 'mun',
    filter: ['!=', ['get', 'listras'], 'liso'], paint: hachPaint, layout: {visibility: 'none'}});
  map.addLayer({id: 'mun-linha', type: 'line', source: 'mun',
    paint: {'line-color': '#fff', 'line-width': 1}, layout: {visibility: 'none'}});

  map.addLayer({id: 'calor-tema', type: 'heatmap', source: 'pontos',
    paint: {
      'heatmap-weight': 0.6,
      'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 5, 1, 12, 3],
      'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 5, 14, 12, 34],
      'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.85, 13, 0.5],
      'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
        0, 'rgba(0,0,0,0)', 0.2, '#C8E6C9', 0.4, '#81C784', 0.6, '#F9A825',
        0.8, '#E65100', 1, '#B00020'],
    }, layout: {visibility: 'none'}});

  map.addLayer({id: 'pontos-tema', type: 'circle', source: 'pontos',
    paint: {'circle-color': matchCamada, 'circle-opacity': 0.82,
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, 2.6, 10, 4.5, 15, 9],
      'circle-stroke-width': 0.5, 'circle-stroke-color': '#fff'},
    layout: {visibility: 'none'}});

  map.addLayer({id: 'pontos-hub', type: 'circle', source: 'pontos',
    filter: ['==', ['get', 'municipio_norm'], '__nada__'],
    paint: {'circle-color': matchCamada, 'circle-opacity': 0.85,
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 3, 15, 9],
      'circle-stroke-width': 0.6, 'circle-stroke-color': '#fff'},
    layout: {visibility: 'none'}});

  visibilidadeHub();
  enquadrarEstado(false);

  /* ---- interação: hub ---- */
  const semHover = window.matchMedia('(hover: none)').matches;
  let toqueEm = null;

  map.on('mousemove', 'ra-fill', e => {
    if (tema !== 'hub') return;
    popRegiao.setLngLat(e.lngLat)
      .setHTML(htmlRegiao(e.features[0].properties, 'ra')
        + '<p class="pop-dica">Clique para abrir esta região →</p>').addTo(map);
  });
  map.on('mouseleave', 'ra-fill', () => popRegiao.remove());
  map.on('click', 'ra-fill', e => {
    if (tema !== 'hub') return;
    const p = e.features[0].properties;
    if (semHover && toqueEm !== p.regiao_administrativa) {
      toqueEm = p.regiao_administrativa;
      popRegiao.setLngLat(e.lngLat)
        .setHTML(htmlRegiao(p, 'ra') + '<p class="pop-dica">Toque de novo para abrir →</p>').addTo(map);
      return;
    }
    toqueEm = null; popRegiao.remove(); irRegiao(p.regiao_administrativa);
  });

  map.on('mousemove', 'mun-fill', e => {
    if (tema !== 'hub' || nivel !== 'regiao') return;
    popRegiao.setLngLat(e.lngLat)
      .setHTML(htmlRegiao(e.features[0].properties, 'municipio')
        + '<p class="pop-dica">Clique para ver as empresas →</p>').addTo(map);
  });
  map.on('mouseleave', 'mun-fill', () => popRegiao.remove());
  map.on('click', 'mun-fill', e => {
    if (tema !== 'hub' || nivel !== 'regiao') return;
    const p = e.features[0].properties;
    if (semHover && toqueEm !== p.municipio_norm) {
      toqueEm = p.municipio_norm;
      popRegiao.setLngLat(e.lngLat)
        .setHTML(htmlRegiao(p, 'municipio') + '<p class="pop-dica">Toque de novo para ver →</p>').addTo(map);
      return;
    }
    toqueEm = null; popRegiao.remove(); irMunicipio(p.municipio_norm, p.nome);
  });

  /* ---- interação: contexto ---- */
  map.on('mousemove', 'ctx-fill', e => {
    if (tema !== 'contexto') return;
    const p = e.features[0].properties;
    popRegiao.setLngLat(e.lngLat).setHTML(
      `<p class="pop-nome">${p.nome}</p><p class="pop-sub">${p.regiao_administrativa}</p>`
      + `<p class="pop-info">${p.populacao ? '<b>' + inteiro(p.populacao) + '</b> habitantes' : 'população não disponível'}`
      + `<span class="pop-ano"> (estimativa ${p.ano_populacao})</span></p>`
      + (p.idhm ? `<p class="pop-info"><b>IDHM ${num(p.idhm, 3)}</b>`
          + `<span class="pop-ano"> (${p.ano_idhm} — o dado municipal mais recente que existe)</span></p>`
          + `<p class="pop-ano">renda ${num(p.idhm_renda,3)} · longevidade ${num(p.idhm_longevidade,3)}`
          + ` · educação ${num(p.idhm_educacao,3)}</p>` : '')
      + `<hr style="border:0;border-top:1px solid #eee;margin:7px 0">`
      + `<p class="pop-info">Serviços circulares: <b>${p.nivel} de 4</b>`
      + ` · <b>${ESTAGIO_NOMES[ESTAGIOS.indexOf(p.estagio)]}</b></p>`
    ).addTo(map);
  });
  map.on('mouseleave', 'ctx-fill', () => popRegiao.remove());

  /* ---- interação: pontos ---- */
  ['pontos-tema', 'pontos-hub'].forEach(id => {
    map.on('click', id, e => {
      popPonto.setLngLat(e.features[0].geometry.coordinates)
        .setHTML(htmlPonto(e.features[0].properties)).addTo(map);
    });
  });
  ['ra-fill', 'mun-fill', 'pontos-tema', 'pontos-hub', 'ctx-fill'].forEach(id => {
    map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', id, () => map.getCanvas().style.cursor = '');
  });

  map.resize(); map.triggerRepaint();
  let lw = 0, lh = 0, mexeu = false;
  map.on('dragstart', () => mexeu = true);
  map.on('zoomstart', ev => { if (ev.originalEvent) mexeu = true; });
  new ResizeObserver(() => {
    const el = map.getContainer();
    if (el.clientWidth === lw && el.clientHeight === lh) return;
    lw = el.clientWidth; lh = el.clientHeight;
    map.resize();
    // vale para TODOS os temas, não só o hub: o container costuma crescer depois do
    // load e o fitBounds inicial sai com zoom errado em qualquer um deles
    const noEstado = tema === 'hub' ? nivel === 'estado' : !filtroRA;
    if (noEstado && !mexeu) enquadrarEstado(false);
    map.triggerRepaint();
  }).observe(map.getContainer());
}

/* ================= controles ================= */
const abasEl = $('#abas'), abasWrap = $('#abas-wrap');
function marcarOverflow() {
  const sobra = abasEl.scrollWidth - abasEl.clientWidth;
  abasWrap.classList.toggle('tem-mais', sobra > 4 && abasEl.scrollLeft < sobra - 4);
}
abasEl.addEventListener('scroll', marcarOverflow);
window.addEventListener('resize', marcarOverflow);
marcarOverflow();

document.querySelectorAll('.aba').forEach(a =>
  a.addEventListener('click', () => {
    trocarTema(a.dataset.tema);
    // em tela estreita a aba clicada pode estar meio fora: traz ela para a vista
    a.scrollIntoView({behavior: 'smooth', block: 'nearest', inline: 'center'});
    setTimeout(marcarOverflow, 350);
  }));

$('#voltar').addEventListener('click', () => {
  nivel === 'municipio' ? irRegiao(raSel) : irEstado();
});

document.querySelectorAll('[data-camada],[data-material],[data-ciclo]').forEach(c =>
  c.addEventListener('change', () => {
    const tri = document.querySelector('[data-camada="triagem"]');
    $('#sub-materiais').classList.toggle('off', !tri.checked);
    aplicarFiltros();
  }));

document.querySelectorAll('[data-corhub]').forEach(b => b.addEventListener('click', () => {
  corHub = b.dataset.corhub;
  document.querySelectorAll('[data-corhub]').forEach(x => x.classList.toggle('on', x === b));
  visibilidadeHub();
}));

document.querySelectorAll('[data-modo]').forEach(b => b.addEventListener('click', () => {
  modo = b.dataset.modo;
  document.querySelectorAll('[data-modo]').forEach(x => x.classList.toggle('on', x.dataset.modo === modo));
  const ehPontos = tema === 'tratamento' || tema === 'biologico';
  vis('pontos-tema', ehPontos && modo === 'pontos');
  vis('calor-tema', ehPontos && modo === 'calor');
}));

document.querySelectorAll('[data-ctxvar]').forEach(b => b.addEventListener('click', () => {
  varCtx = b.dataset.ctxvar;
  document.querySelectorAll('[data-ctxvar]').forEach(x => x.classList.toggle('on', x === b));
  aplicarContexto();
}));

document.querySelectorAll('.filtro-ra').forEach(s => s.addEventListener('change', () => {
  filtroRA = s.value;
  document.querySelectorAll('.filtro-ra').forEach(o => o.value = filtroRA);
  aplicarFiltros();
  if (filtroRA) {
    const fs = geojsonMun.features.filter(f => f.properties.regiao_administrativa === filtroRA);
    if (fs.length) map.fitBounds(limitesDe(fs), {padding: 30, maxZoom: 10, duration: 600});
  } else enquadrarEstado(true);
}));

const painel = $('#painel');
$('#recolher').addEventListener('click', () => {
  painel.classList.toggle('recolhido');
  $('#recolher').textContent = painel.classList.contains('recolhido') ? '☰' : '✕';
});
if (window.matchMedia('(max-width: 760px)').matches) {
  painel.classList.add('recolhido');
  $('#recolher').textContent = '☰';
}

if (map.isStyleLoaded()) iniciar(); else map.once('style.load', iniciar);
'''

aba_contexto = '''
      <button class="aba" data-tema="contexto">Contexto
        <span class="aba-sub">População e IDH</span></button>''' if TEM_CONTEXTO else ''

painel_contexto = '''
      <div class="painel-tema" data-tema="contexto" style="display:none">
        <div class="seg" style="margin-bottom:10px">
          <button data-ctxvar="populacao" class="on">População</button>
          <button data-ctxvar="idhm">IDHM</button>
        </div>
        <div class="secao">Escala</div>
        <div data-ctxleg="populacao">
          __LEG_POP__
        </div>
        <div data-ctxleg="idhm" style="display:none">
          __LEG_IDH__
        </div>
        <p class="dica">Passe o mouse por um município para ver população, IDHM e o
        estágio da cadeia circular ali. É o cruzamento pedido na reunião: onde o vazio
        circular coincide com menor desenvolvimento humano.</p>
        <div class="secao">O que o cruzamento mostra</div>
        __BLOCO_CRUZ__
        <p class="nota">O IDHM municipal é de <b>2010</b> — não por escolha de fonte, mas
        porque é o mais recente que existe. Depois do Censo 2010 o índice passou a ser
        calculado com a PNAD Contínua, que só tem representatividade estadual, e a versão
        com o Censo 2022 ainda não foi publicada. A população é a estimativa de 2026, então
        as duas camadas têm defasagem de uma década entre si.</p>
      </div>''' if TEM_CONTEXTO else ''

leg_pop = ''.join(item_legenda(c, t) for c, t in [
    ('#EDF8E9', 'até 1.000 hab.'), ('#BAE4B3', '1.000 a 10.000'),
    ('#74C476', '10.000 a 50.000'), ('#31A354', '50.000 a 300.000'),
    ('#006D2C', 'mais de 300.000'), ('#e0e0e0', 'sem dado')])
leg_idh = ''.join(item_legenda(c, t) for c, t in [
    ('#1B5E20', 'IDHM 0,86 ou mais — muito alto'), ('#8BC34A', '0,80 a 0,86 — alto'),
    ('#F5C518', '0,74 a 0,80 — médio-alto'), ('#E65100', '0,68 a 0,74 — médio'),
    ('#B00020', 'abaixo de 0,68 — baixo'), ('#e0e0e0', 'sem dado')])
def dec(v, casas=2, sinal=False):
    """Decimal com vírgula. Formatado em separado justamente para não encadear
    .replace('.', ',') numa string que também contém prosa."""
    txt = f'{v:+.{casas}f}' if sinal else f'{v:.{casas}f}'
    return txt.replace('.', ',')


bloco_cruz = ''
if TEM_CONTEXTO and cruz:
    r_pop = dec(cruz['r_pop'], 2, sinal=True)
    r_idhm = dec(cruz['r_idhm'], 2, sinal=True)
    pop0, pop4 = milhar(cruz['pop_med_n0']), milhar(cruz['pop_med_n4'])
    idhm0, idhm4 = dec(cruz['idhm_med_n0'], 3), dec(cruz['idhm_med_n4'], 3)
    bloco_cruz = f'''
    <div class="kpis">
      <div class="kpi"><b>{r_pop}</b><span>correlação com o tamanho da população</span></div>
      <div class="kpi"><b>{r_idhm}</b><span>correlação com o IDHM</span></div>
    </div>
    <p class="dica">A intuição da reunião era que o vazio circular acompanharia o IDH baixo.
    Acompanha — mas fracamente. O que realmente prevê a presença de infraestrutura é o
    <b>tamanho do município</b>: a população mediana salta de {pop0} habitantes nos
    municípios sem nenhum serviço para {pop4} nos que têm os quatro, enquanto o IDHM médio
    mal se move ({idhm0} contra {idhm4}). O problema é de <b>escala</b>, não de renda.</p>'''

painel_contexto = (painel_contexto.replace('__LEG_POP__', leg_pop)
                   .replace('__LEG_IDH__', leg_idh)
                   .replace('__BLOCO_CRUZ__', bloco_cruz))

HTML = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Mapa da Economia Circular — Estado de São Paulo</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<style>__CSS__</style>
</head>
<body>
<div id="app">
  <header id="topo">
    <div id="topo-linha">
      <div id="marca">Mapa da Economia Circular
        <span>Estado de São Paulo · SENAC SP · Revolução Circular</span></div>
    </div>
    <div id="abas-wrap"><nav id="abas">
      <button class="aba ativa" data-tema="hub">Hub Circular
        <span class="aba-sub">Maturidade por região</span></button>
      <button class="aba" data-tema="tratamento">Tratamento de resíduos
        <span class="aba-sub">5 camadas combináveis</span></button>
      <button class="aba" data-tema="biologico">Ciclo biológico
        <span class="aba-sub">Compostagem, biogás e biomassa</span></button>__ABA_CTX__
    </nav></div>
  </header>

  <div id="corpo">
    <div id="map"></div>
    <aside id="painel">
      <div id="painel-topo">
        <div id="painel-titulo">Hub Circular</div>
        <button id="recolher" title="Recolher painel">✕</button>
      </div>
      <div id="painel-corpo">

        <!-- ---------- HUB ---------- -->
        <div class="painel-tema" data-tema="hub">
          <button id="voltar">← Voltar</button>
          <div id="trilha"></div>
          <div class="seg" style="margin-bottom:11px">
            <button data-corhub="classe" class="on">Escala 0-4</button>
            <button data-corhub="estagio">Estágio da cadeia</button>
          </div>
          <div class="secao" id="titulo-escala">Maturidade da região</div>
          <div id="leg-classe">__LEG_CLASSE__</div>
          <div id="leg-nivel" style="display:none">__LEG_NIVEL__</div>
          <div id="leg-estagio" style="display:none">__LEG_ESTAGIO__</div>
          <div id="leg-hachura">
            <div class="secao">Cobertura (hachura)</div>
            <div class="leg-item"><span class="sw hach-liso"></span>
              <span class="leg-txt">Menos de 15% dos municípios sem registro</span></div>
            <div class="leg-item"><span class="sw hach-leve"></span>
              <span class="leg-txt">15% a 30% sem registro</span></div>
            <div class="leg-item"><span class="sw hach-forte"></span>
              <span class="leg-txt">30% ou mais sem registro</span></div>
          </div>
          <div id="leg-pins" style="display:none">
            <div class="secao">Atividade dos pontos</div>
            __LEG_PINS__
          </div>
          <div id="hub-vazio" style="display:none"></div>
          <p class="dica">Clique numa região para ver os municípios; clique num município
          para ver as empresas.</p>
        </div>

        <!-- ---------- TRATAMENTO ---------- -->
        <div class="painel-tema" data-tema="tratamento" style="display:none">
          <div class="filtro-linha">
            <select class="ctrl filtro-ra"><option value="">Todas as regiões</option>__OPCOES_RA__</select>
          </div>
          <div class="seg" style="margin-bottom:4px">
            <button data-modo="pontos" class="on">Pontos</button>
            <button data-modo="calor">Densidade</button>
          </div>
          <div class="kpis" id="contagem"></div>
          <div class="secao">Camadas (combináveis)</div>
          __CHK_CAMADAS__
          <div class="secao">Material recuperado</div>
          <div id="sub-materiais" class="sub-bloco">
            __CHK_MATERIAIS__
            <p class="nota">Só metal e plástico têm CNAE próprio na Receita Federal.
            Papel, vidro e construção civil caem todos no código genérico 3839-4/99 e
            não podem ser separados por esta fonte.</p>
          </div>
        </div>

        <!-- ---------- CICLO BIOLÓGICO ---------- -->
        <div class="painel-tema" data-tema="biologico" style="display:none">
          <div class="filtro-linha">
            <select class="ctrl filtro-ra"><option value="">Todas as regiões</option>__OPCOES_RA__</select>
          </div>
          <div class="seg" style="margin-bottom:4px">
            <button data-modo="pontos" class="on">Pontos</button>
            <button data-modo="calor">Densidade</button>
          </div>
          <div class="kpis" id="contagem-bio"></div>
          <div class="secao">Fontes</div>
          __CHK_CICLOS__
          <p class="dica">O tamanho do círculo é proporcional à potência outorgada.
          O estado soma __MW_TOTAL__ MW em operação — a esmagadora maioria de bagaço
          de cana, no cinturão canavieiro do interior.</p>
        </div>
        __PAINEL_CTX__

      </div>
    </aside>
  </div>
</div>
<script>__JS__</script>
</body>
</html>'''

js = (JS
      .replace('__RA__', json.dumps(geojson_ra, ensure_ascii=False))
      .replace('__MUN__', json.dumps(geojson_mun, ensure_ascii=False))
      .replace('__PONTOS__', json.dumps(D['pontos'], ensure_ascii=False))
      .replace('__MATCH_CLASSE__', json.dumps(match_classe))
      .replace('__MATCH_ESTAGIO__', json.dumps(match_estagio))
      .replace('__MATCH_CAMADA__', json.dumps(match_camada))
      .replace('__MATCH_MATERIAL__', json.dumps(match_material))
      .replace('__MATCH_CICLO__', json.dumps(match_ciclo))
      .replace('__PALETA__', json.dumps(PALETA))
      .replace('__ESTAGIOS__', json.dumps(ESTAGIOS))
      .replace('__ESTAGIO_NOMES__', json.dumps([ESTAGIO_INFO[e][0] for e in ESTAGIOS],
                                               ensure_ascii=False))
      .replace('__TEM_CONTEXTO__', 'true' if TEM_CONTEXTO else 'false'))

html = (HTML
        .replace('__CSS__', CSS)
        .replace('__ABA_CTX__', aba_contexto)
        .replace('__PAINEL_CTX__', painel_contexto)
        .replace('__LEG_CLASSE__', leg_classe)
        .replace('__LEG_NIVEL__', leg_nivel)
        .replace('__LEG_ESTAGIO__', leg_estagio)
        .replace('__LEG_PINS__', leg_pins)
        .replace('__CHK_CAMADAS__', chk_camadas)
        .replace('__CHK_MATERIAIS__', chk_materiais)
        .replace('__CHK_CICLOS__', chk_ciclos)
        .replace('__OPCOES_RA__', opcoes_ra)
        .replace('__MW_TOTAL__', str(mw_total).replace('.', ','))
        .replace('__JS__', js))

with open(SAIDA, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'-> {SAIDA} ({round(os.path.getsize(SAIDA)/1024/1024, 2)} MB)')
