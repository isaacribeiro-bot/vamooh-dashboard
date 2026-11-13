#!/usr/bin/env python3
"""Busca os dados publicados do Google Sheets (CSV) e atualiza o index.html do painel."""
import csv
import io
import json
import re
import sys
import urllib.request

URL_LANCAMENTOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTRWZOBjVlLN07yxqi_aP8UgqSenlIeUIF0pZKjehwK1aAoJI7ADPq6-Vzd-8VzYJOr-pccUSYyxuhu/pub?gid=26808&single=true&output=csv"
URL_METAS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTRWZOBjVlLN07yxqi_aP8UgqSenlIeUIF0pZKjehwK1aAoJI7ADPq6-Vzd-8VzYJOr-pccUSYyxuhu/pub?gid=2054887422&single=true&output=csv"
URL_EXECUTIVOS = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTRWZOBjVlLN07yxqi_aP8UgqSenlIeUIF0pZKjehwK1aAoJI7ADPq6-Vzd-8VzYJOr-pccUSYyxuhu/pub?gid=1710935790&single=true&output=csv"

MES_MAP = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
           'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12}
MONTHS_ORDER = [f"2026-{m:02d}" for m in range(1, 13)]


def fetch_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    text = raw.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def parse_money(v):
    if v is None:
        return None
    v = v.strip()
    if v in ("", "-"):
        return None
    s = v.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_pct(v):
    if v is None:
        return None
    v = v.strip()
    if v in ("", "-"):
        return None
    s = v.replace("%", "").replace(",", ".").strip()
    try:
        return round(float(s) / 100, 4)
    except ValueError:
        return None


def parse_mes(v):
    m = re.match(r"([a-z]{3})\./(\d{2})", v.strip().lower())
    if not m:
        return None
    mm = MES_MAP.get(m.group(1))
    yy = int(m.group(2)) + 2000
    if not mm:
        return None
    return f"{yy:04d}-{mm:02d}"


def build_lancamentos():
    rows = fetch_csv(URL_LANCAMENTOS)
    header = rows[0]
    idx = {name: i for i, name in enumerate(header) if name}
    out = []
    for r in rows[1:]:
        if len(r) <= idx.get("AV / CR", 1) or not r[idx["Mês (competência)"]].strip():
            continue
        mes_key = parse_mes(r[idx["Mês (competência)"]])
        if not mes_key:
            continue
        executivo = r[idx["Executivo (fica fixo na venda)"]].strip() or "(sem executivo)"
        if executivo == "DEFINIR":
            executivo = "(sem executivo)"
        nucleo = r[idx["Núcleo"]].strip() or "(sem núcleo)"
        if nucleo == "DEFINIR":
            nucleo = "(sem núcleo)"
        campanha = r[idx["Campanha"]].split("\n")[0][:120] if idx.get("Campanha") is not None else ""
        bruto = parse_money(r[idx["Bruto"]]) or 0
        liquido = parse_money(r[idx["Líquido"]]) or 0
        producao = parse_money(r[idx["Produção (-)"]]) or 0
        comissao = parse_money(r[idx["Comissão agência (-)"]]) or 0
        bv = parse_money(r[idx["BV (-)"]]) or 0
        lg = parse_money(r[idx["Líquido Growth"]])
        lg = lg if lg is not None else 0
        out.append({
            "mes": mes_key,
            "av_cr": r[idx["AV / CR"]].strip(),
            "cliente": r[idx["Cliente"]].strip(),
            "campanha": campanha,
            "cadastro": r[idx["Cadastro CGO"]].strip(),
            "vencimento": r[idx["Vencimento"]].strip(),
            "executivo": executivo,
            "nucleo": nucleo,
            "bruto": bruto,
            "liquido": liquido,
            "producao": producao,
            "comissao": comissao,
            "bv": bv,
            "liquido_growth": lg,
            "status": "",
        })
    return out


def build_metas():
    rows = fetch_csv(URL_METAS)
    header = rows[0]
    out = []
    for r in rows[1:]:
        name = r[0].strip()
        if not name:
            break  # fim do bloco de executivos reais (antes das linhas de total/notas)
        nucleo = r[1].strip() if len(r) > 1 else ""
        for i in range(12):
            col = 2 + i
            val = r[col] if col < len(r) else ""
            meta = parse_money(val)
            out.append({
                "executivo": name,
                "nucleo": nucleo,
                "mes": MONTHS_ORDER[i],
                "meta": meta if meta is not None else 0,
            })
    return out


def build_executivos():
    rows = fetch_csv(URL_EXECUTIVOS)
    out = []
    for r in rows[1:]:
        name = r[0].strip()
        if not name:
            break
        out.append({
            "executivo": name,
            "nucleo": r[1].strip() if len(r) > 1 else "",
            "comissionado": r[2].strip() if len(r) > 2 else "Não",
        })
    return out


def main():
    lancamentos = build_lancamentos()
    metas = build_metas()
    executivos = build_executivos()
    data = {"lancamentos": lancamentos, "metas": metas, "executivos": executivos}
    data_json = json.dumps(data, ensure_ascii=False)

    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    m = re.search(r"const DATA = (\{.*?\});\n", html, re.DOTALL)
    if not m:
        print("ERRO: bloco 'const DATA = ...' não encontrado em index.html", file=sys.stderr)
        sys.exit(1)

    new_html = html[:m.start(1)] + data_json + html[m.end(1):]

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(new_html)

    total_lg = sum(r["liquido_growth"] for r in lancamentos)
    print(f"Atualizado: {len(lancamentos)} vendas, {len(metas)} linhas de meta, "
          f"{len(executivos)} executivos. Líquido Growth total: R$ {total_lg:,.2f}")


if __name__ == "__main__":
    main()
