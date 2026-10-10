# /// script
# dependencies = ["duckdb", "pandas", "openpyxl"]
# ///
"""Cruza votação presidencial por seção: 2018 (Haddad x Bolsonaro), 2022 (Lula x Bolsonaro), 2026 (1º turno).
Uso: uv run analise_secoes.py   (na primeira vez baixa ~2 GB do portal de dados abertos do TSE)
"""
import os
import urllib.request
import zipfile

import duckdb

SRC = "secao/{y}/votacao_secao_{y}_BR.csv"
# número do candidato da direita em cada ano (PT é sempre 13)
DIREITA = {2018: 17, 2022: 22, 2026: 22}

# arquivos do TSE usados: destino local -> (zip no CDN, arquivo dentro do zip)
TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele/"
ARQUIVOS = {
    **{SRC.format(y=y): (f"votacao_secao/votacao_secao_{y}_BR.zip", f"votacao_secao_{y}_BR.csv") for y in DIREITA},
    **{f"detalhe/{y}/detalhe_votacao_secao_{y}_BR.csv": (f"detalhe_votacao_secao/detalhe_votacao_secao_{y}.zip", f"detalhe_votacao_secao_{y}_BR.csv") for y in DIREITA},
    "locais/eleitorado_local_votacao_2026_BRASIL.csv": ("eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip", "eleitorado_local_votacao_2026_BRASIL.csv"),
}
for destino, (url, membro) in ARQUIVOS.items():
    if os.path.exists(destino):
        continue
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    print("baixando", TSE + url)
    tmp, _ = urllib.request.urlretrieve(TSE + url)
    with zipfile.ZipFile(tmp) as z, z.open(membro) as src, open(destino, "wb") as dst:
        while bloco := src.read(1 << 20):
            dst.write(bloco)
    os.remove(tmp)

con = duckdb.connect()

for y, dir_nr in DIREITA.items():
    con.execute(f"""
    CREATE TABLE v{y} AS
    SELECT SG_UF uf, CD_MUNICIPIO cd_mun, any_value(NM_MUNICIPIO) municipio, NR_ZONA zona, NR_SECAO secao, NR_TURNO turno,
           any_value(NM_LOCAL_VOTACAO) local_votacao, any_value(DS_LOCAL_VOTACAO_ENDERECO) endereco,
           coalesce(sum(QT_VOTOS) FILTER (NR_VOTAVEL = 13), 0) pt,
           coalesce(sum(QT_VOTOS) FILTER (NR_VOTAVEL = {dir_nr}), 0) dir,
           coalesce(sum(QT_VOTOS) FILTER (NR_VOTAVEL NOT IN (95, 96, 97)), 0) validos,
           sum(QT_VOTOS) total
    FROM read_csv('{SRC.format(y=y)}', delim=';', header=true, encoding='latin-1', all_varchar=false)
    WHERE CD_CARGO = 1
    GROUP BY ALL
    """)

def cols(y, t, tag, a=None):
    a = a or f"t{y}_{t}"
    return f"""{a}.pt pt_{tag}, {a}.dir dir_{tag}, {a}.validos validos_{tag},
       round(100.0*{a}.pt/nullif({a}.validos,0),1) pct_pt_{tag},
       round(100.0*{a}.dir/nullif({a}.validos,0),1) pct_dir_{tag},
       round(100.0*{a}.pt/nullif({a}.pt+{a}.dir,0),1) bip_pt_{tag}"""

def lado(y, t, esq, dir, a=None):
    a = a or f"t{y}_{t}"
    return f"CASE WHEN {a}.pt IS NULL THEN NULL WHEN {a}.pt > {a}.dir THEN '{esq}' WHEN {a}.pt < {a}.dir THEN '{dir}' ELSE 'Empate' END"

# coordenadas e bairro de cada seção (cadastro de locais de votação 2026)
con.execute("""
CREATE TABLE loc AS
SELECT SG_UF uf, CAST(CD_MUNICIPIO AS INT) cd_mun, CAST(NR_ZONA AS INT) zona, CAST(NR_SECAO AS INT) secao, CAST(NR_LOCAL_VOTACAO AS INT) nr_local, NM_BAIRRO bairro,
       TRY_CAST(replace(NR_LATITUDE, ',', '.') AS DOUBLE) lat, TRY_CAST(replace(NR_LONGITUDE, ',', '.') AS DOUBLE) lon
FROM read_csv('locais/eleitorado_local_votacao_2026_BRASIL.csv', delim=';', header=true, encoding='latin-1', all_varchar=true)
WHERE NR_TURNO = '1'
QUALIFY row_number() OVER (PARTITION BY uf, cd_mun, zona, secao) = 1
""")

# eleitores aptos e comparecimento por seção (detalhe da apuração, presidente)
for y in (2018, 2022, 2026):
    con.execute(f"""
    CREATE TABLE ab{y} AS
    SELECT SG_UF uf, CD_MUNICIPIO cd_mun, NR_ZONA zona, NR_SECAO secao, NR_TURNO turno, sum(QT_APTOS) aptos, sum(QT_ABSTENCOES) abst
    FROM read_csv('detalhe/{y}/detalhe_votacao_secao_{y}_BR.csv', delim=';', header=true, encoding='latin-1')
    WHERE CD_CARGO = 1 GROUP BY ALL
    """)

# regiões do IBGE: grande região (5) e região geográfica intermediária ("macrorregião" dentro do estado)
con.execute("""
CREATE TABLE reg AS
SELECT t.codigo_tse cd_mun, i."regiao-nome" regiao, i."regiao-intermediaria-nome" macrorregiao
FROM read_csv('ref/tse_ibge.csv') t JOIN read_json('ref/ibge_municipios.json') i ON i."municipio-id" = t.codigo_ibge
UNION ALL SELECT 73709, 'Centro-Oeste', 'Sinop'  -- Boa Esperança do Norte/MT, criado em 2024 (desmembrado de Sorriso), fora da tabela TSE-IBGE
""")

# base = seções de 2026; casa com 2022/2018 pela chave UF+município+zona+seção
joins = ""
for y, t in [(2022, 1), (2022, 2), (2018, 1), (2018, 2)]:
    joins += f"\nLEFT JOIN v{y} t{y}_{t} ON t{y}_{t}.turno={t} AND (t{y}_{t}.uf, t{y}_{t}.cd_mun, t{y}_{t}.zona, t{y}_{t}.secao) = (b.uf, b.cd_mun, b.zona, b.secao)"

con.execute(f"""
CREATE TABLE secoes AS
WITH b AS (SELECT * FROM v2026 WHERE turno = 1)
SELECT b.uf, coalesce(reg.regiao, CASE WHEN b.uf = 'ZZ' THEN 'Exterior' ELSE 'Não identificada' END) regiao,
       coalesce(reg.macrorregiao, CASE WHEN b.uf = 'ZZ' THEN 'Exterior' ELSE 'Não identificada' END) macrorregiao,
       b.cd_mun, b.municipio, b.zona, b.secao, loc.nr_local, b.local_votacao, loc.bairro, b.endereco, loc.lat, loc.lon, b.total votos_2026,
       ab18.aptos aptos_2018t1, ab18.abst abst_2018t1, ab22.aptos aptos_2022t1, ab22.abst abst_2022t1, ab26.aptos aptos_2026t1, ab26.abst abst_2026t1,
       round(100.0*ab18.abst/nullif(ab18.aptos,0),1) pct_abst_2018t1, round(100.0*ab22.abst/nullif(ab22.aptos,0),1) pct_abst_2022t1, round(100.0*ab26.abst/nullif(ab26.aptos,0),1) pct_abst_2026t1,
       {lado(2018, 2, 'Haddad', 'Bolsonaro')} lado_2018,
       {lado(2022, 2, 'Lula', 'Bolsonaro')} lado_2022,
       {lado(2026, 1, "Lula", "Flávio", "b")} lado_2026,
       {cols(2018, 1, '2018t1')}, {cols(2018, 2, '2018t2')},
       {cols(2022, 1, '2022t1')}, {cols(2022, 2, '2022t2')},
       {cols(2026, 1, "2026t1", "b")}
FROM b{joins}
LEFT JOIN loc ON (loc.uf, loc.cd_mun, loc.zona, loc.secao) = (b.uf, b.cd_mun, b.zona, b.secao)
LEFT JOIN reg ON reg.cd_mun = b.cd_mun
LEFT JOIN ab2018 ab18 ON ab18.turno = 1 AND (ab18.uf, ab18.cd_mun, ab18.zona, ab18.secao) = (b.uf, b.cd_mun, b.zona, b.secao)
LEFT JOIN ab2022 ab22 ON ab22.turno = 1 AND (ab22.uf, ab22.cd_mun, ab22.zona, ab22.secao) = (b.uf, b.cd_mun, b.zona, b.secao)
LEFT JOIN ab2026 ab26 ON ab26.turno = 1 AND (ab26.uf, ab26.cd_mun, ab26.zona, ab26.secao) = (b.uf, b.cd_mun, b.zona, b.secao)
""")
con.execute("""
ALTER TABLE secoes ADD COLUMN padrao VARCHAR;
UPDATE secoes SET padrao = coalesce(lado_2018,'(sem seção 2018)') || ' → ' || coalesce(lado_2022,'(sem seção 2022)') || ' → ' || lado_2026;
ALTER TABLE secoes ADD COLUMN var_bip_pt_22t1_26t1 DOUBLE;
UPDATE secoes SET var_bip_pt_22t1_26t1 = round(bip_pt_2026t1 - bip_pt_2022t1, 1);
""")

# coordenadas erradas no cadastro do TSE (local a mais de 2° do centro do próprio município) vão para o centro do município
con.execute("""
UPDATE secoes s SET lat = m.mlat, lon = m.mlon
FROM (SELECT uf, cd_mun, median(lat) mlat, median(lon) mlon FROM secoes WHERE lat <> 0 GROUP BY ALL) m
WHERE (s.uf, s.cd_mun) = (m.uf, m.cd_mun) AND (abs(s.lat - m.mlat) > 2 OR abs(s.lon - m.mlon) > 2 OR s.lat = 0)
""")
# município inteiro geocodificado em outro estado (ex.: Funilândia/MG no PR): ponto fora da caixa do estado vai para o centro da macrorregião
con.execute("""
UPDATE secoes s SET lat = m.mlat, lon = m.mlon
FROM (SELECT uf, macrorregiao, median(lat) mlat, median(lon) mlon FROM secoes GROUP BY ALL) m,
     (SELECT uf, quantile_cont(lat, 0.01) - 1 la0, quantile_cont(lat, 0.99) + 1 la1, quantile_cont(lon, 0.01) - 1 lo0, quantile_cont(lon, 0.99) + 1 lo1 FROM secoes GROUP BY uf) b
WHERE (s.uf, s.macrorregiao) = (m.uf, m.macrorregiao) AND s.uf = b.uf AND s.uf <> 'ZZ'
  AND (s.lat NOT BETWEEN b.la0 AND b.la1 OR s.lon NOT BETWEEN b.lo0 AND b.lo1)
""")
print("seções com coordenada corrigida:", con.sql("SELECT count(*) FROM secoes s JOIN loc USING (uf, cd_mun, zona, secao) WHERE s.lat IS DISTINCT FROM loc.lat").fetchone()[0])

resumo = """
SELECT {g} padrao, count(*) secoes, sum(votos_2026) votos_2026,
       round(100.0*count(*)/sum(count(*)) OVER ({p}),1) pct_secoes,
       round(sum(pt_2018t2)*100.0/sum(pt_2018t2+dir_2018t2),1) bip_pt_2018t2,
       round(sum(pt_2022t1)*100.0/sum(pt_2022t1+dir_2022t1),1) bip_pt_2022t1,
       round(sum(pt_2022t2)*100.0/sum(pt_2022t2+dir_2022t2),1) bip_pt_2022t2,
       round(sum(pt_2026t1)*100.0/sum(pt_2026t1+dir_2026t1),1) bip_pt_2026t1
FROM secoes GROUP BY {g} padrao ORDER BY {o} secoes DESC
"""
brasil = con.sql(resumo.format(g="", p="", o="")).df()
uf = con.sql(resumo.format(g="uf,", p="PARTITION BY uf", o="uf,")).df()
mun = con.sql(resumo.format(g="uf, municipio,", p="PARTITION BY uf, municipio", o="uf, municipio,")).df()
# painel largo: uma linha por região, com % do PT em cada eleição e peso de cada trajetória
painel = """
SELECT {g}, count(DISTINCT cd_mun) municipios, count(*) secoes, sum(votos_2026) votos_2026,
       round(sum(pt_2018t2)*100.0/sum(pt_2018t2+dir_2018t2),1) haddad_2018t2,
       round(sum(pt_2022t1)*100.0/sum(pt_2022t1+dir_2022t1),1) lula_2022t1,
       round(sum(pt_2022t2)*100.0/sum(pt_2022t2+dir_2022t2),1) lula_2022t2,
       round(sum(pt_2026t1)*100.0/sum(pt_2026t1+dir_2026t1),1) lula_2026t1,
       round(sum(pt_2026t1)*100.0/sum(pt_2026t1+dir_2026t1) - sum(pt_2022t1)*100.0/sum(pt_2022t1+dir_2022t1),1) var_pp_22t1_26t1,
       sum(aptos_2026t1) aptos_2026,
       round(100.0*sum(abst_2018t1)/sum(aptos_2018t1),1) pct_abst_2018t1,
       round(100.0*sum(abst_2022t1)/sum(aptos_2022t1),1) pct_abst_2022t1,
       round(100.0*sum(abst_2026t1)/sum(aptos_2026t1),1) pct_abst_2026t1,
       round(100.0*sum(abst_2026t1) FILTER (aptos_2022t1 > 0)/sum(aptos_2026t1) FILTER (aptos_2022t1 > 0) - 100.0*sum(abst_2022t1)/sum(aptos_2022t1),1) var_abst_pp_22t1_26t1,
       sum(abst_2026t1) abstencoes_2026,
       round(100.0*sum(abst_2026t1) FILTER (padrao IN ('Bolsonaro → Lula → Flávio', 'Haddad → Bolsonaro → Lula'))/nullif(sum(aptos_2026t1) FILTER (padrao IN ('Bolsonaro → Lula → Flávio', 'Haddad → Bolsonaro → Lula')),0),1) pct_abst_2026_secoes_pendulares,
       round(100.0*sum(votos_2026) FILTER (padrao IN ('Bolsonaro → Lula → Flávio', 'Haddad → Bolsonaro → Lula'))/sum(votos_2026),1) "% votos pendulares",
       round(100.0*sum(votos_2026) FILTER ('Empate' NOT IN (lado_2018, lado_2022, lado_2026) AND ((lado_2018 = 'Haddad') <> (lado_2022 = 'Lula') OR (lado_2022 = 'Lula') <> (lado_2026 = 'Lula')))/sum(votos_2026),1) "% votos que mudaram",
       round(avg((abs(bip_pt_2022t2 - bip_pt_2018t2) + abs(bip_pt_2026t1 - bip_pt_2022t1)) / 2),1) volatilidade_pp,
       round(100.0*count(*) FILTER (padrao = 'Haddad → Lula → Lula')/count(*),1) "% fiel PT",
       round(100.0*count(*) FILTER (padrao = 'Bolsonaro → Lula → Lula')/count(*),1) "% virou 2022 e ficou",
       round(100.0*count(*) FILTER (padrao = 'Bolsonaro → Lula → Flávio')/count(*),1) "% virou 2022 e voltou",
       round(100.0*count(*) FILTER (padrao LIKE 'Haddad → % → Flávio')/count(*),1) "% PT perdeu",
       round(100.0*count(*) FILTER (padrao = 'Bolsonaro → Bolsonaro → Lula')/count(*),1) "% direita perdeu 2026",
       round(100.0*count(*) FILTER (padrao = 'Bolsonaro → Bolsonaro → Flávio')/count(*),1) "% fiel direita"
FROM secoes GROUP BY {g} ORDER BY {g}
"""
por_regiao = con.sql(painel.format(g="regiao")).df()
por_macro = con.sql(painel.format(g="uf, macrorregiao")).df()
# ranking: macrorregiões com voto pendular (mínimo 50 mil votos para não destacar ruído de regiões pequenas)
ranking = por_macro[por_macro.votos_2026 >= 50000].sort_values("% votos pendulares", ascending=False)
# seções que mudaram de lado desde 2022 (alvos de conversão / risco)
viradas = con.sql("SELECT * FROM secoes WHERE lado_2022 IS NOT NULL AND lado_2022 <> 'Empate' AND (lado_2022='Lula') <> (lado_2026='Lula') ORDER BY uf, municipio, zona, secao").df()
casamento = con.sql("""SELECT count(*) secoes_2026,
    count(lado_2022) casaram_2022, round(100.0*count(lado_2022)/count(*),1) pct_2022,
    count(lado_2018) casaram_2018, round(100.0*count(lado_2018)/count(*),1) pct_2018 FROM secoes""").df()

con.execute("COPY secoes TO 'resultado_secoes_2018_2022_2026.csv' (HEADER, DELIMITER ';')")
with __import__("pandas").ExcelWriter("resumo_padroes_voto.xlsx") as xw:
    ranking.to_excel(xw, sheet_name="Ranking pendular", index=False)
    casamento.to_excel(xw, sheet_name="Casamento de seções", index=False)
    brasil.to_excel(xw, sheet_name="Brasil", index=False)
    por_regiao.to_excel(xw, sheet_name="Por região", index=False)
    por_macro.to_excel(xw, sheet_name="Por macrorregião", index=False)
    uf.to_excel(xw, sheet_name="Por UF", index=False)
    mun.to_excel(xw, sheet_name="Por município", index=False)
    viradas.to_excel(xw, sheet_name="Seções que viraram", index=False)

print(casamento.to_string(), "\n")
print(brasil.to_string())


# dados do mapa: seções agregadas por local de votação
import json
locs = con.sql("""
SELECT uf, municipio || ' / ' || uf mun, coalesce(any_value(bairro), '') bairro, any_value(local_votacao) nome,
       round(avg(lat), 4) lat, round(avg(lon), 4) lon, count(*) secoes, sum(votos_2026) votos,
       sum(pt_2018t2) a18, sum(dir_2018t2) b18, sum(pt_2022t1) a22_1, sum(dir_2022t1) b22_1,
       sum(pt_2022t2) a22, sum(dir_2022t2) b22, sum(pt_2026t1) a26, sum(dir_2026t1) b26,
       any_value(regiao) regiao, any_value(macrorregiao) || ' / ' || uf macro_rg,
       coalesce(sum(votos_2026) FILTER (padrao IN ('Bolsonaro → Lula → Flávio', 'Haddad → Bolsonaro → Lula')), 0) pend,
       coalesce(sum(votos_2026) FILTER ('Empate' NOT IN (lado_2018, lado_2022, lado_2026) AND ((lado_2018 = 'Haddad') <> (lado_2022 = 'Lula') OR (lado_2022 = 'Lula') <> (lado_2026 = 'Lula'))), 0) mudou,
       coalesce(sum(aptos_2022t1), 0) ap22, coalesce(sum(abst_2022t1), 0) ab22, coalesce(sum(aptos_2026t1), 0) ap26, coalesce(sum(abst_2026t1), 0) ab26
FROM secoes WHERE lat BETWEEN -34 AND 6 AND lon BETWEEN -75 AND -28
GROUP BY uf, cd_mun, municipio, zona, nr_local
""").fetchall()
ufs, muns, bairros, regs, macros = {}, {}, {}, {}, {}
idx = lambda d, k: d.setdefault(k, len(d))
rows = [[r[4], r[5], idx(ufs, r[0]), idx(muns, r[1]), idx(bairros, r[2]), r[3]] + [None if v is None else int(v) for v in r[6:16]] + [idx(regs, r[16]), idx(macros, r[17])] + [int(v) for v in r[18:24]] for r in locs]
# mapa/ é um clone de github.com/leolmcoelho/mapa-virada (o site no GitHub Pages)
if not os.path.isdir("mapa"):
    print("pasta mapa/ ausente: clone o repositório mapa-virada nela para gerar o mapa")
    raise SystemExit
with open("mapa/dados.js", "w", encoding="utf-8") as f:
    j = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
    f.write(f"const UFS={j(list(ufs))};\nconst MUNS={j(list(muns))};\nconst BAIRROS={j(list(bairros))};\nconst REGS={j(list(regs))};\nconst MACROS={j(list(macros))};\nconst LOCAIS={j(rows)};\n")
# index.html = template + contorno dos estados embutido
with open("mapa/mapa_template.html", encoding="utf-8") as t, open("mapa/estados.geojson", encoding="utf-8") as g:
    html = t.read().replace("__ESTADOS__", " ".join(g.read().split()))
with open("mapa/index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("locais no mapa:", len(rows))
