# Voto pendular 2018–2026

Análise da votação para presidente por seção eleitoral em 2018, 2022 e 2026, para encontrar onde o voto oscila entre PT e bolsonarismo e onde a abstenção cresceu.

- **Mapa interativo:** https://leolmcoelho.github.io/mapa-virada/ (código em [leolmcoelho/mapa-virada](https://github.com/leolmcoelho/mapa-virada))
- **Planilha com os resultados:** [`resumo_padroes_voto.xlsx`](resumo_padroes_voto.xlsx)
- **Dados por seção (CSV, 160 MB):** na aba [Releases](../../releases) deste repositório

## Principais resultados

- 3,1% das seções foram Bolsonaro em 2018, Lula em 2022 e Flávio Bolsonaro em 2026. Ficaram perto do empate (46,6% para Lula no 1º turno de 2026).
- O voto pendular se concentra no sul e centro de Minas, no Triângulo Mineiro, na metade sul do RS e no sul fluminense. Barbacena/MG lidera, com 14,7% dos votos em seções pendulares.
- A abstenção subiu nas seções pendulares (de 21,4% para 22,4% entre os 1º turnos de 2022 e 2026) e caiu na base fiel do PT (de 20,6% para 19,7%).

## Como rodar

Requer [uv](https://docs.astral.sh/uv/). Na primeira execução o script baixa cerca de 2 GB do [Portal de Dados Abertos do TSE](https://dadosabertos.tse.jus.br/).

```bash
git clone https://github.com/leolmcoelho/mapas-analise.git
cd mapas-analise
git clone https://github.com/leolmcoelho/mapa-virada.git mapa   # opcional: para regenerar o mapa
uv run analise_secoes.py
```

Leva cerca de 1 minuto depois do download. Sem a pasta `mapa/`, o script gera a planilha e o CSV e pula o mapa.

## O que o script gera

| Arquivo | Conteúdo |
| --- | --- |
| `resumo_padroes_voto.xlsx` | Abas Ranking pendular, Por região, Por macrorregião, Brasil, Por UF, Por município, Seções que viraram e Casamento de seções |
| `resultado_secoes_2018_2022_2026.csv` | Uma linha por seção de 2026: local, bairro, coordenadas, votos e percentuais de cada eleição, abstenção, trajetória e região |
| `mapa/dados.js`, `mapa/index.html` | Dados e página do mapa |

## Metodologia

- **Lado vencedor da seção:** 2º turno de 2018 (Haddad × Bolsonaro), 2º turno de 2022 (Lula × Bolsonaro) e 1º turno de 2026 (Lula × Flávio).
- **Percentual do PT:** no voto dos dois polos, PT ÷ (PT + candidato do PSL/PL).
- **Voto pendular:** votos de 2026 em seções que trocaram de lado e voltaram (Bolsonaro → Lula → Flávio, ou Haddad → Bolsonaro → Lula).
- **Abstenção:** sempre no 1º turno, com os eleitores aptos de cada seção.
- **Ligação entre eleições:** pelo número da seção (UF, município, zona e seção). 92% das seções de 2026 existiam em 2022 e 87% em 2018.
- **Macrorregião:** região geográfica intermediária do IBGE. A ligação entre os códigos de município do TSE e do IBGE está em `ref/`.
- **Coordenadas:** cerca de 2.600 seções tinham coordenadas erradas no cadastro do TSE (algumas em outro estado). O script as move para o centro do município ou da macrorregião.

## Limitações

- Seção não é eleitor: uma seção que mudou de lado pode refletir mudança de opinião, abstenção diferente ou mudança de endereço.
- 2026 ainda tem só o 1º turno. Quando o TSE publicar o 2º, basta apagar `secao/2026` e `detalhe/2026` e rodar de novo.

## Fontes

- TSE, Portal de Dados Abertos: votação por seção eleitoral, detalhe da apuração por seção e eleitorado por local de votação.
- IBGE: divisão regional (API de localidades).
- Correspondência de códigos TSE–IBGE: [betafcc/Municipios-Brasileiros-TSE](https://github.com/betafcc/Municipios-Brasileiros-TSE).
