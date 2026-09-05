# Mapa de Economia Circular — Estado de SP

Mapeamento georreferenciado de iniciativas de economia circular no estado de São Paulo, construído para o projeto **Revolução Circular** (SENAC SP, Geração 2027).

**[Ver Hub Circular por Região Administrativa](https://helanmatos.github.io/mapa-economia-circular-sp/mapa_hub_circular.html)** · **[Ver mapa de pontos](https://helanmatos.github.io/mapa-economia-circular-sp/)** · **[Ver mapa de calor](https://helanmatos.github.io/mapa-economia-circular-sp/mapa_calor.html)**

## O que tem no mapa

- **8.719 empresas** de resíduos sólidos urbanos (coleta, tratamento, recuperação de materiais), extraídas dos Dados Abertos do CNPJ da Receita Federal e geocodificadas via Nominatim/OpenStreetMap.
- **239 usinas de energia** por biogás/biomassa em operação, via dados abertos da ANEEL (SIGA), já com coordenadas oficiais.
- Filtro por **Região Administrativa** (as 16 RAs do estado) e por **categoria circular** (ISO 59000: Reciclagem, Bioeconomia, Valorização energética, Tratamento/disposição).
- Três visualizações: **Hub Circular** por RA (`mapa_hub_circular.html`, coroplético com índice de maturidade — 4 elementos: coleta, reciclagem, tratamento/disposição, orgânicos), pontos individuais coloridos (`index.html`) e **mapa de calor** de densidade (`mapa_calor.html`), com transição suave para pontos ao aproximar o zoom.

### Hub Circular — índice de maturidade

Reformulação proposta em reunião de produto (07/09/2026): em vez de olhar empresa por empresa, o Hub Circular mede quantos dos 4 elementos de infraestrutura existem em cada lugar — Coleta, Reciclagem, Tratamento/Disposição e Orgânicos (compostagem + energia).

O **nível do município** é a contagem direta desses 4 elementos. Dos 645 municípios: 125 no nível 0, 171 no nível 1, 196 no nível 2, 130 no nível 3 e apenas 23 no nível 4 — média estadual de 1,62 serviço por município.

A **classe da Região Administrativa** é a média dos municípios dela, arredondada, sujeita a uma **trava de lacuna**: quanto maior a fatia de municípios sem nenhum registro, mais baixo o teto da classe (a partir de 15% o teto é 2, de 30% é 1, de 50% é 0). A trava só rebaixa, nunca promove. Vale registrar que, **com os dados atuais, a trava não chega a ser acionada em nenhuma das 16 RAs** — ela é uma salvaguarda contra uma região com média alta concentrada em poucos municípios, situação que hoje não ocorre. O que efetivamente corrige a leitura é a troca da presença regional pela média municipal.

Uma **hachura diagonal** sobre o polígono mostra a fatia de municípios sem registro — um segundo canal, independente da cor, e o único que sobrevive à impressão em preto-e-branco. Oito RAs saem lisas, cinco com hachura leve e três com hachura forte.

Isso substituiu a regra anterior, que pintava a RA pela presença do serviço *em algum lugar da região*: bastava um município ter tratamento para a região inteira virar "circular completo", e 12 das 16 RAs apareciam no nível máximo. O caso mais claro era a 8ª São José do Rio Preto, pintada de verde-escuro com 38,5% dos seus municípios sem nenhum registro, acima da 2ª Santos, que não tem nenhum município zerado.

Com a regra atual nenhuma RA alcança a classe 4. A 1ª Grande SP é a única classe 3; nove regiões ficam na classe 2 e seis na classe 1 (Registro, Presidente Prudente, Marília, São José do Rio Preto, Araçatuba e Itapeva). Coleta e reciclagem continuam praticamente universais; o que diferencia as regiões é a presença de tratamento/disposição formal e, sobretudo, o tamanho do vazio interno.

## Fontes de dados

| Fonte | Uso | Cobertura |
|---|---|---|
| Receita Federal (CNPJ) | Empresas de resíduos por CNAE | Ativa, jun/2026 |
| ANEEL (SIGA) | Usinas de biogás/biomassa | Operação, jul/2026 |
| IBGE/Wikipédia | Município → Região Administrativa | 645 municípios |

## Documentos

- [`documento_completo_mapa_economia_circular.pdf`](documento_completo_mapa_economia_circular.pdf) — documento técnico completo: processo, fontes de dados, método, qualidade/limitações, conteúdo dos mapas, insights, conclusões e o que falta dentro do escopo formal.
- [`analise_estrategica_mapa_economia_circular.pdf`](analise_estrategica_mapa_economia_circular.pdf) — análise estratégica: concentração regional, "desertos circulares", lacunas na cadeia circular e KPIs.
- [`relatorio_mapa_economia_circular.pdf`](relatorio_mapa_economia_circular.pdf) — relatório da primeira entrega (base de empresas).

## Limitações conhecidas

Fontes institucionais adicionais previstas no escopo (CETESB, SNIS, cadastro de cooperativas de catadores via SINIR) estão indisponíveis até 25/10/2026 por conta do período de defeso eleitoral (Lei 9.504/1997, art. 73 VI "b"). Reuso, remanufatura e logística reversa não têm CNAE próprio na Receita Federal e por isso não aparecem na base atual — ver a análise estratégica para detalhes.

## Reproduzindo o pipeline

Scripts em Python (DuckDB + reportlab), executados em sequência: `run_pipeline.sh` (extração CNPJ) → `geocodifica.py` (geocodificação Nominatim) → `extrai_aneel.py` (energia ANEEL) → `enriquece.py` (Região Administrativa + categoria circular) → `gerar_mapa.py` (mapa MapLibre GL) → `gerar_analise_estrategica.py` / `gerar_relatorio.py` (PDFs).
