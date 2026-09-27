# Mapa de Economia Circular — Estado de SP

Mapeamento georreferenciado de iniciativas de economia circular no estado de São Paulo, construído para o projeto **Revolução Circular** (SENAC SP, Geração 2027).

**[Abrir o mapa](https://helanmatos.github.io/mapa-economia-circular-sp/)** — aplicação única com quatro temas: Hub Circular, Tratamento de resíduos, Ciclo biológico e Contexto socioeconômico.

## O que tem no mapa

- **10.504 empresas** de resíduos sólidos urbanos (coleta, tratamento, recuperação de materiais), extraídas dos Dados Abertos do CNPJ da Receita Federal e geocodificadas em duas passadas — Nominatim/OpenStreetMap e, para o que ele não achou, coordenada do CEP validada contra o polígono do município.
- **239 usinas de energia** por biogás/biomassa em operação, via dados abertos da ANEEL (SIGA), já com coordenadas oficiais.
- Filtro por **Região Administrativa** (as 16 RAs do estado) e por **categoria circular** (ISO 59000: Reciclagem, Bioeconomia, Valorização energética, Tratamento/disposição).
- **Quatro temas numa aplicação só** (`index.html`), com troca instantânea entre eles — os dados são carregados uma vez e o que muda é filtro, cor e visibilidade, então a navegação não recarrega nada e preserva o enquadramento do mapa.

### Hub Circular — índice de maturidade

Reformulação proposta em reunião de produto (07/09/2026): em vez de olhar empresa por empresa, o Hub Circular mede quantos dos 4 elementos de infraestrutura existem em cada lugar — Coleta, Reciclagem, Tratamento/Disposição e Orgânicos (compostagem + energia).

O **nível do município** é a contagem direta desses 4 elementos. Dos 645 municípios: 99 no nível 0, 162 no nível 1, 203 no nível 2, 145 no nível 3 e 36 no nível 4 — média estadual de 1,78 serviço por município.

A **classe da Região Administrativa** é a média dos municípios dela, arredondada, sujeita a uma **trava de lacuna**: quanto maior a fatia de municípios sem nenhum registro, mais baixo o teto da classe (a partir de 15% o teto é 2, de 30% é 1, de 50% é 0). A trava só rebaixa, nunca promove. Vale registrar que, **com os dados atuais, a trava não chega a ser acionada em nenhuma das 16 RAs** — ela é uma salvaguarda contra uma região com média alta concentrada em poucos municípios, situação que hoje não ocorre. O que efetivamente corrige a leitura é a troca da presença regional pela média municipal.

Uma **hachura diagonal** sobre o polígono mostra a fatia de municípios sem registro — um segundo canal, independente da cor, e o único que sobrevive à impressão em preto-e-branco. Nove RAs saem lisas, cinco com hachura leve e duas com hachura forte.

Isso substituiu a regra anterior, que pintava a RA pela presença do serviço *em algum lugar da região*: bastava um município ter tratamento para a região inteira virar "circular completo", e 12 das 16 RAs apareciam no nível máximo. O caso mais claro era a 8ª São José do Rio Preto, pintada de verde-escuro com 31,2% dos seus municípios sem nenhum registro, acima da 2ª Santos, que não tem nenhum município zerado.

### Duas escalas, cada uma no nível em que funciona

O índice tem duas leituras, e a escala **acompanha o nível de navegação** — não é preferência, é o que os dados sustentam:

| Nível | Escala | Por quê |
|---|---|---|
| **Estado** (16 regiões) | Média municipal, 0-4 | É a única que não deixa uma região verde tendo um terço dos municípios vazio |
| **Município** | Escada nomeada (básico / estruturado / circular) | Sem agregação, presença *é* a realidade local — e o nome comunica melhor que "2 de 4" |

A **escada composicional** é a leitura proposta na reunião: não conta quantos serviços existem, verifica *quais*. Básico = coleta + reciclagem; estruturado = + tratamento; circular = + orgânicos. Aplicada aos 645 municípios: 36 circulares (5,6%), 51 estruturados (7,9%), 262 básicos (40,6%), **197 incipientes (30,5%)** e 99 sem nada (15,3%). Os "incipientes" têm algum serviço mas não fecham nem coleta + reciclagem — um terço do estado, que a contagem simples misturava com quem tem a base montada.

**Por que a escada não serve para a região.** Agregada por RA, ela volta a medir "presença em algum ponto do território" — exatamente o defeito que a média veio corrigir. Pela escada, 12 das 16 regiões são "circulares", incluindo a 9ª Araçatuba, que tem **um único** estabelecimento de tratamento e 32,6% dos municípios sem nenhum registro. No sentido oposto, a 2ª Santos, com 0% de municípios vazios, cai para "estruturado". Abrir Araçatuba no mapa mostra o problema de imediato: a região verde se desfaz em vermelhos, laranjas e um só município verde.

**Por que a escada é melhor no município.** Ela prioriza o tratamento/disposição, que é o elo escasso do estado — 137 estabelecimentos, contra 3.894 de coleta e 6.387 de triagem. As duas escalas discordam em 128 dos 645 municípios — a contagem chama de "quase completo" municípios que a escada mantém em "básico" por falta de tratamento, e chama de "intermediário" outros que a escada rebaixa a "incipiente" por falta de coleta.

O botão de escala continua no painel para comparar as duas; ao mudar de nível ele volta ao padrão. Forçar a escada no estado exibe um aviso explicando o que aquela leitura esconde.

Com a regra atual nenhuma RA alcança a classe 4. A 1ª Grande SP é a única classe 3; dez regiões ficam na classe 2 e cinco na classe 1 (Registro, Presidente Prudente, São José do Rio Preto, Araçatuba e Itapeva). Coleta e reciclagem continuam praticamente universais; o que diferencia as regiões é a presença de tratamento/disposição formal e, sobretudo, o tamanho do vazio interno.

## Os quatro temas

**1. Hub Circular** — as 16 Regiões Administrativas coloridas por maturidade, com drill-down: clica na região e ela abre nos municípios, clica no município e aparecem os pinos de cada empresa. A escala acompanha o nível: **média municipal no estado, escada nomeada no município** (ver a seção acima). O botão permite comparar as duas.

**2. Tratamento de resíduos** — as 5 camadas da cadeia (coleta e movimentação, triagem e recuperação, orgânicos, tratamento e disposição, descontaminação), **combináveis entre si**: dá para ver coleta e triagem juntas, ou isolar só descontaminação. Alterna entre colorir por **camada da cadeia** ou por **categoria circular (ISO 59000)** — nesta segunda, Reuso, Remanufatura e Logística reversa aparecem na legenda com zero, porque não têm CNAE próprio na Receita Federal e a ausência delas é o próprio achado do item 4 do escopo. Dentro de "triagem e recuperação" há a sub-camada de material recuperado — metal, plástico e um terceiro balde honesto. Só metal e plástico têm CNAE próprio na Receita Federal; papel, vidro e construção civil caem todos no genérico 3839-4/99 e não podem ser separados por esta fonte.

**3. Ciclo biológico** — compostagem, biogás e biomassa energética, com o **raio do círculo proporcional à potência outorgada**. São 293 unidades — 54 usinas de compostagem, 13 de biogás e 226 de biomassa — somando 6.951,3 MW, quase tudo bagaço de cana no cinturão canavieiro. O contraste com o tema 1 é o achado: resíduos sólidos se concentram na Grande SP, energia se concentra no interior agrícola.

**4. Contexto socioeconômico** — população (IBGE) e IDHM (Ipeadata / Atlas do Desenvolvimento Humano) nos 645 municípios, cruzados com o índice de maturidade. É o cruzamento pedido na reunião, e ele **qualifica a hipótese original**: a intuição era que o vazio circular acompanharia o IDH baixo. Acompanha, mas fracamente — a correlação com o IDHM é 0,45, enquanto a correlação com o **tamanho da população** é 0,68. A população mediana salta de 4.101 habitantes nos municípios sem nenhum serviço para 100.272 nos que têm os quatro (fator de 24×), enquanto o IDHM médio mal se move (0,722 contra 0,769).

O que isso muda: se o determinante fosse renda, a resposta seria política de desenvolvimento regional. Como é **escala**, a resposta é arranjo intermunicipal — um município de 4 mil habitantes não sustenta aterro licenciado nem usina de triagem por mais rico que seja. Somado ao achado de que o vazio está *dentro* das regiões e não entre elas, isso aponta para consórcio, transbordo e escala compartilhada.

O IDHM municipal é de **2010** — não por escolha de fonte, mas porque é o mais recente que existe: depois do Censo 2010 o índice passou a ser calculado com a PNAD Contínua, que só tem representatividade estadual, e a versão com o Censo 2022 ainda não saiu. O app declara a defasagem na própria legenda.

Os temas 2 e 3 têm ainda filtro por Região Administrativa e alternância entre pontos e mapa de densidade.

## Fontes de dados

| Fonte | Uso | Cobertura |
|---|---|---|
| Receita Federal (CNPJ) | Empresas de resíduos por CNAE | Ativa, jun/2026 |
| ANEEL (SIGA) | Usinas de biogás/biomassa | Operação, jul/2026 |
| IBGE/Wikipédia | Município → Região Administrativa | 645 municípios |
| IBGE (API de agregados) | População municipal | Estimativa 2026 + Censo 2022, 645/645 |
| Ipeadata (base do Atlas do Desenvolvimento Humano) | IDHM e dimensões | Censo 2010, 645/645 |

## Documentos

- [`documento_completo_mapa_economia_circular.pdf`](documento_completo_mapa_economia_circular.pdf) — documento técnico completo: processo, fontes de dados, método, qualidade/limitações, conteúdo dos mapas, insights, conclusões e o que falta dentro do escopo formal.
- [`analise_estrategica_mapa_economia_circular.pdf`](analise_estrategica_mapa_economia_circular.pdf) — análise estratégica: concentração regional, "desertos circulares", lacunas na cadeia circular e KPIs.
- [`relatorio_mapa_economia_circular.pdf`](relatorio_mapa_economia_circular.pdf) — relatório da primeira entrega (base de empresas).

## Geocodificação em duas passadas

**10.504 dos 10.509 estabelecimentos (100,0%) estão no mapa.** Chegar aí exigiu duas passadas, porque a primeira tinha um vazio grande e enviesado.

**1ª passada — Nominatim/OpenStreetMap.** Geocodificou 8.719 (83%). Os 1.790 que faltaram eram endereços de cidades pequenas do interior, que o OSM mapeia mal. E a falha não era uniforme: ia de 4,3% na 2ª Registro a 27,3% na 11ª Marília, concentrada justamente nas regiões que o mapa aponta como vazias.

**2ª passada — por CEP.** Todos os 1.790 têm CEP de 8 dígitos (1.602 distintos), e o CEP tem coordenada em bases que não dependem do OSM. Testando com CEPs reais da base:

| Fonte | Retorna coordenada | Cai no município certo |
|---|---|---|
| **BrasilAPI v2** | 97% | **100% das que retorna** |
| AwesomeAPI | 100% | 92% — 8% caem na Grande SP |
| ViaCEP | — | não devolve coordenada |
| Photon (OSM) | sim | erra o município |

A BrasilAPI entrou como fonte principal e a AwesomeAPI como reserva. **Toda coordenada é validada contra o polígono do município declarado no CNPJ** — sem isso, a reserva injetaria erro grosseiro: no CEP de Aguaí ela devolve um ponto perto de Taubaté, acertando o nome da cidade e errando o lugar.

Resultado: **1.785 dos 1.790 recuperados**, 5 descartados por cair fora do município. Empresas sem coordenada caíram de 1.790 para **5**, municípios sem nenhum ponto no mapa de 33 para **zero**, e a pior taxa de falha por região de 27,3% para **0,2%**.

**O índice não mudou com isso** — [99, 162, 203, 145, 36], média 1,78 — e isso é o esperado: desde a v7 o índice é calculado por município, e o município sempre esteve preenchido em 100% dos registros. A geocodificação corrigiu o **mapa**, não a medida.

**Ressalva de precisão:** os 2.487 pontos vindos de CEP (702 da 1ª passada + 1.785 da 2ª) têm precisão de **logradouro, não de número**. Em CEP geral de município caem no centro da cidade. O popup os marca como aproximados.

## Limitações conhecidas

Fontes institucionais adicionais previstas no escopo (CETESB, SNIS, cadastro de cooperativas de catadores via SINIR) estão indisponíveis até 25/10/2026 por conta do período de defeso eleitoral (Lei 9.504/1997, art. 73 VI "b"). Reuso, remanufatura e logística reversa não têm CNAE próprio na Receita Federal e por isso não aparecem na base atual — ver a análise estratégica para detalhes.

## Reproduzindo o pipeline

Scripts em Python (DuckDB + reportlab), executados em sequência: `run_pipeline.sh` (extração CNPJ) → `geocodifica.py` (geocodificação Nominatim) → `extrai_aneel.py` (energia ANEEL) → `geocodifica_cep.py` (2ª passada por CEP) → `extrai_contexto.py` (população IBGE + IDHM Ipeadata) → `enriquece.py` (Região Administrativa + categoria circular) → `gerar_app.py` (a aplicação de quatro temas) → `gerar_documento_completo.py` / `gerar_analise_estrategica.py` / `gerar_relatorio.py` (PDFs).

Dois módulos concentram as regras para que mapa e documento nunca divirjam: **`maturidade.py`** (índice de maturidade, escalas de cor, escada composicional) e **`dados_app.py`** (camadas, materiais e ciclos). O cruzamento de município entre fontes passa sempre por `enriquece.chave()` — normalizar só um lado do join faz ele falhar em silêncio, e foi assim que 105 usinas de energia ficaram fora do índice numa versão anterior.
