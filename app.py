from flask import Flask, render_template, request
import pyodbc

app = Flask(__name__)

conn_str = (
    "DRIVER={SQL Server};"
    "SERVER=TU_SERVIDOR;"
    "DATABASE=Cardif;"
    "UID=TU_USUARIO;"
    "PWD=TU_PASSWORD;"
)

# ============================================================
# LIMPIEZA TEXTO
# ============================================================
def clean(txt):
    return " ".join((txt or "").split()).strip().upper()

def clean_label(txt):
    v = " ".join((txt or "").split()).strip()
    return v if v else "PEND_GESTIONAR"

# ============================================================
# FECHA BASE
# ============================================================
def fecha_base():
    return "TRY_CONVERT(DATE, REPLACE(A.[FechaUltimaGestion],'-','/'), 103)"

# ============================================================
# CLASIFICACION NPS
# ============================================================
def clasificar_nps(val):
    try:
        n = float(val)
        if n <= 6:
            return "Detractor"
        elif n <= 8:
            return "Neutro"
        else:
            return "Promotor"
    except:
        return None

# ============================================================
# BUILD QUERY PRINCIPAL CON TODOS LOS FILTROS
# ============================================================
def build_query(mes, semana, pais, lob, nombre_completo, nombre_superv, fecha_encuesta):
    f = fecha_base()

    query = f"""
    SELECT
        A.[ENC.Responsabilidad],
        A.[GestionNivelII],
        A.[GestionNivelIII],
        A.[NPS],
        A.[ENC.Nueva calificación],
        A.[HoraCreacion],
        A.[Pais],
        A.[Split N],
        B.[lob],
        B.[NombreCompleto],
        B.[NombreSuperv],
        A.[Fecha Encuesta]
    FROM [Cardif].[dbo].[tbCallBackNps] AS A WITH (NOLOCK)
    LEFT JOIN [Cardif].[dbo].[tbHeadCountTotal] AS B
        ON A.[UsuarioUltimaGestion] = B.[idcuenta]
    WHERE A.[FechaUltimaGestion] IS NOT NULL
    """

    if mes:
        query += f" AND DATENAME(MONTH, {f}) = '{mes}'"

    if semana:
        query += f"""
        AND CONVERT(VARCHAR(10),
            DATEADD(WEEK, DATEDIFF(WEEK,0,{f}),0),23
        ) = '{semana}'
        """

    if pais:
        query += f" AND A.[Pais] = '{pais}'"

    if lob:
        query += f" AND B.[lob] = '{lob}'"

    if nombre_completo:
        query += f" AND B.[NombreCompleto] = '{nombre_completo}'"

    if nombre_superv:
        query += f" AND B.[NombreSuperv] = '{nombre_superv}'"

    if fecha_encuesta:
        query += f" AND CONVERT(DATE, A.[Fecha Encuesta], 103) = '{fecha_encuesta}'"

    return query

# ============================================================
# GET DATA PRINCIPAL
# ============================================================
def get_data(mes, semana, pais, lob, nombre_completo, nombre_superv, fecha_encuesta):
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()

    cur.execute(build_query(mes, semana, pais, lob, nombre_completo, nombre_superv, fecha_encuesta))
    rows = cur.fetchall()

    # --- Tabla 1: Responsabilidad + GestionNivelII ---
    grp1 = {}
    for r in rows:
        resp = clean_label(r[0])
        niv2 = clean_label(r[1])
        key = (resp, niv2)
        grp1[key] = grp1.get(key, 0) + 1

    total1 = sum(grp1.values())
    tabla1 = sorted([
        {
            "responsabilidad": k[0],
            "nivel2": k[1],
            "total": v,
            "participacion": round((v / total1) * 100, 1) if total1 else 0
        }
        for k, v in grp1.items()
    ], key=lambda x: x["total"], reverse=True)

    # --- Tabla 2: Responsabilidad + GestionNivelII + GestionNivelIII ---
    grp2 = {}
    for r in rows:
        resp = clean_label(r[0])
        niv2 = clean_label(r[1])
        niv3 = clean_label(r[2])
        key = (resp, niv2, niv3)
        grp2[key] = grp2.get(key, 0) + 1

    total2 = sum(grp2.values())
    tabla2 = sorted([
        {
            "responsabilidad": k[0],
            "nivel2": k[1],
            "nivel3": k[2],
            "total": v,
            "participacion": round((v / total2) * 100, 1) if total2 else 0
        }
        for k, v in grp2.items()
    ], key=lambda x: x["total"], reverse=True)

    # --- Pastel: ENC.Responsabilidad ---
    grp_resp = {}
    for r in rows:
        resp = clean_label(r[0])
        grp_resp[resp] = grp_resp.get(resp, 0) + 1

    total_resp = sum(grp_resp.values())
    pastel_resp = [
        {
            "label": k,
            "total": v,
            "participacion": round((v / total_resp) * 100, 1) if total_resp else 0
        }
        for k, v in sorted(grp_resp.items(), key=lambda x: x[1], reverse=True)
    ]

    # --- NPS principal ---
    grp_nps = {"Promotor": 0, "Neutro": 0, "Detractor": 0, "Sin dato": 0}
    for r in rows:
        cat = clasificar_nps(r[3])
        if cat:
            grp_nps[cat] += 1
        else:
            grp_nps["Sin dato"] += 1

    total_nps = sum(grp_nps.values())
    prom_pct = round((grp_nps["Promotor"] / total_nps) * 100, 1) if total_nps else 0
    det_pct = round((grp_nps["Detractor"] / total_nps) * 100, 1) if total_nps else 0
    score_nps = round(prom_pct - det_pct, 1)

    tabla_nps = [
        {
            "categoria": cat,
            "total": grp_nps[cat],
            "participacion": round((grp_nps[cat] / total_nps) * 100, 1) if total_nps else 0
        }
        for cat in ["Promotor", "Neutro", "Detractor", "Sin dato"]
    ]

    # --- NPS x Split N ---
    grp_split = {}
    for r in rows:
        cat = clasificar_nps(r[3])
        split = clean_label(r[7])
        if cat:
            key = (split, cat)
            grp_split[key] = grp_split.get(key, 0) + 1

    total_split = sum(grp_split.values())
    splits_unicos = sorted(set(k[0] for k in grp_split))
    tabla_split = []
    for sp in splits_unicos:
        prom = grp_split.get((sp, "Promotor"), 0)
        neut = grp_split.get((sp, "Neutro"), 0)
        detr = grp_split.get((sp, "Detractor"), 0)
        tot = prom + neut + detr
        p_pct = round((prom / tot) * 100, 1) if tot else 0
        d_pct = round((detr / tot) * 100, 1) if tot else 0
        tabla_split.append({
            "split": sp,
            "promotor": prom,
            "neutro": neut,
            "detractor": detr,
            "total": tot,
            "participacion": round((tot / total_split) * 100, 1) if total_split else 0,
            "nps_score": round(p_pct - d_pct, 1)
        })

    # --- NPS Re-encuesta (ENC.Nueva calificación) ---
    grp_re = {"Promotor": 0, "Neutro": 0, "Detractor": 0, "Sin dato": 0}
    for r in rows:
        cat = clasificar_nps(r[4])
        if cat:
            grp_re[cat] += 1
        else:
            grp_re["Sin dato"] += 1

    total_re = sum(grp_re.values())
    prom_re = round((grp_re["Promotor"] / total_re) * 100, 1) if total_re else 0
    det_re = round((grp_re["Detractor"] / total_re) * 100, 1) if total_re else 0
    score_re = round(prom_re - det_re, 1)

    tabla_re = [
        {
            "categoria": cat,
            "total": grp_re[cat],
            "participacion": round((grp_re[cat] / total_re) * 100, 1) if total_re else 0
        }
        for cat in ["Promotor", "Neutro", "Detractor", "Sin dato"]
    ]

    # --- Heatmap HoraCreacion (hora x día semana) ---
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    heatmap = {}
    for r in rows:
        hora_raw = r[5]
        if hora_raw:
            try:
                hora_str = str(hora_raw)
                hora = int(hora_str.split(":")[0]) if ":" in hora_str else int(str(hora_raw)[:2])
            except:
                continue
        else:
            continue
        key = hora
        heatmap[key] = heatmap.get(key, 0) + 1

    heatmap_data = [{"hora": h, "total": heatmap.get(h, 0)} for h in range(6, 23)]

    cur.close()
    conn.close()

    return {
        "tabla1": tabla1,
        "tabla1_top10": tabla1[:10],
        "tabla2": tabla2,
        "tabla2_top10": tabla2[:10],
        "pastel_resp": pastel_resp,
        "tabla_nps": tabla_nps,
        "score_nps": score_nps,
        "tabla_split": tabla_split,
        "tabla_re": tabla_re,
        "score_re": score_re,
        "heatmap_data": heatmap_data,
        "total_registros": len(rows)
    }

# ============================================================
# FILTROS DINÁMICOS
# ============================================================
def get_filter_options():
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT DATENAME(MONTH, TRY_CONVERT(DATE, REPLACE(A.[FechaUltimaGestion],'-','/'),103))
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        WHERE A.[FechaUltimaGestion] IS NOT NULL
    """)
    months = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute("""
        SELECT DISTINCT CONVERT(VARCHAR(10),
            DATEADD(WEEK, DATEDIFF(WEEK,0,
                TRY_CONVERT(DATE, REPLACE(A.[FechaUltimaGestion],'-','/'),103)
            ),0),23)
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        WHERE A.[FechaUltimaGestion] IS NOT NULL
        ORDER BY 1 DESC
    """)
    weeks = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute("""
        SELECT DISTINCT A.[Pais]
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        WHERE A.[Pais] IS NOT NULL AND A.[Pais] != ''
        ORDER BY 1
    """)
    paises = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute("""
        SELECT DISTINCT B.[lob]
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        LEFT JOIN Cardif.dbo.tbHeadCountTotal B ON A.[UsuarioUltimaGestion] = B.[idcuenta]
        WHERE B.[lob] IS NOT NULL AND B.[lob] != ''
        ORDER BY 1
    """)
    lobs = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute("""
        SELECT DISTINCT B.[NombreCompleto]
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        LEFT JOIN Cardif.dbo.tbHeadCountTotal B ON A.[UsuarioUltimaGestion] = B.[idcuenta]
        WHERE B.[NombreCompleto] IS NOT NULL AND B.[NombreCompleto] != ''
        ORDER BY 1
    """)
    agentes = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute("""
        SELECT DISTINCT B.[NombreSuperv]
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        LEFT JOIN Cardif.dbo.tbHeadCountTotal B ON A.[UsuarioUltimaGestion] = B.[idcuenta]
        WHERE B.[NombreSuperv] IS NOT NULL AND B.[NombreSuperv] != ''
        ORDER BY 1
    """)
    supervisores = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute("""
        SELECT DISTINCT CONVERT(VARCHAR(10), TRY_CONVERT(DATE, A.[Fecha Encuesta], 103), 23)
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        WHERE A.[Fecha Encuesta] IS NOT NULL
        ORDER BY 1 DESC
    """)
    fechas_enc = [r[0] for r in cur.fetchall() if r[0]]

    cur.close()
    conn.close()

    return {
        "months": months,
        "weeks": weeks,
        "paises": paises,
        "lobs": lobs,
        "agentes": agentes,
        "supervisores": supervisores,
        "fechas_enc": fechas_enc
    }

# ============================================================
# ROUTE PRINCIPAL
# ============================================================
@app.route("/", methods=["GET"])
def index():
    mes = request.args.get("mes")
    semana = request.args.get("semana")
    pais = request.args.get("pais")
    lob = request.args.get("lob")
    nombre_completo = request.args.get("nombre_completo")
    nombre_superv = request.args.get("nombre_superv")
    fecha_encuesta = request.args.get("fecha_encuesta")

    filtros = get_filter_options()
    data = get_data(mes, semana, pais, lob, nombre_completo, nombre_superv, fecha_encuesta)

    return render_template(
        "index.html",
        **data,
        **filtros,
        mes=mes,
        semana=semana,
        pais=pais,
        lob=lob,
        nombre_completo=nombre_completo,
        nombre_superv=nombre_superv,
        fecha_encuesta=fecha_encuesta
    )

# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    print("🚀 DASHBOARD BNP PARIBAS CARDIF — INICIANDO")
    app.run(debug=True)
