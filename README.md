# Mapa de Economia Circular — Estado de SP

Mapeamento georreferenciado de iniciativas de economia circular no estado de São Paulo, construído para o projeto **Revolução Circular** (SENAC SP, Geração 2027).

**[Ver o mapa interativo (pontos)](https://helanmatos.github.io/mapa-economia-circular-sp/)** · **[Ver mapa de calor](https://helanmatos.github.io/mapa-economia-circular-sp/mapa_calor.html)**

## O que tem no mapa

- **8.719 empresas** de resíduos sólidos urbanos (coleta, tratamento, recuperação de materiais), extraídas dos Dados Abertos do CNPJ da Receita Federal e geocodificadas via Nominatim/OpenStreetMap.
- **239 usinas de energia** por biogás/biomassa em operação, via dados abertos da ANEEL (SIGA), já com coordenadas oficiais.
- Filtro por **Região Administrativa** (as 16 RAs do estado) e por **categoria circular** (ISO 59000: Reciclagem, Bioeconomia, Valorização energética, Tratamento/disposição).
- Duas visualizações: pontos individuais coloridos (`index.html`) e **mapa de calor** de densidade (`mapa_calor.html`), com transição suave para pontos ao aproximar o zoom.

## Fontes de dados

| Fonte | Uso | Cobertura |
|---|---|---|
| Receita Federal (CNPJ) | Empresas de resíduos por CNAE | Ativa, jun/2026 |
| ANEEL (SIGA) | Usinas de biogás/biomassa | Operação, jul/2026 |
| IBGE/Wikipédia | Município → Região Administrativa | 645 municípios |

## Documentos

- [`analise_estrategica_mapa_economia_circular.pdf`](analise_estrategica_mapa_economia_circular.pdf) — análise estratégica: concentração regional, "desertos circulares", lacunas na cadeia circular e KPIs.
- [`relatorio_mapa_economia_circular.pdf`](relatorio_mapa_economia_circular.pdf) — relatório da primeira entrega (base de empresas).

## Limitações conhecidas

Fontes institucionais adicionais previstas no escopo (CETESB, SNIS, cadastro de cooperativas de catadores via SINIR) estão indisponíveis até 25/10/2026 por conta do período de defeso eleitoral (Lei 9.504/1997, art. 73 VI "b"). Reuso, remanufatura e logística reversa não têm CNAE próprio na Receita Federal e por isso não aparecem na base atual — ver a análise estratégica para detalhes.

## Reproduzindo o pipeline

Scripts em Python (DuckDB + reportlab), executados em sequência: `run_pipeline.sh` (extração CNPJ) → `geocodifica.py` (geocodificação Nominatim) → `extrai_aneel.py` (energia ANEEL) → `enriquece.py` (Região Administrativa + categoria circular) → `gerar_mapa.py` (mapa MapLibre GL) → `gerar_analise_estrategica.py` / `gerar_relatorio.py` (PDFs).
