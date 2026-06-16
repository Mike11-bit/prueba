from flask import Flask, render_template, request
import pyodbc

app = Flask(__name__)

conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
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
# BUILD QUERY CON FILTROS
# ============================================================
def build_query(mes, semana, pais, lob, nombre_completo, nombre_superv, fecha_encuesta):
    f = fecha_base()

    query = f"""
    SELECT
        A.[ENC.Responsabilidad],
        A.GestionNivelII,
        A.GestionNivelIII,
        1 AS Total,
        DATENAME(MONTH, {f}) AS Mes,
        CONVERT(VARCHAR(10),
            DATEADD(WEEK, DATEDIFF(WEEK,0,{f}),0),23
        ) AS Semana,
        A.[NPS],
        A.[Pais],
        A.[Split N],
        B.[lob],
        B.[NombreCompleto],
        B.[NombreSuperv],
        A.[Fecha Encuesta]
    FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
    LEFT JOIN Cardif.dbo.tbHeadCountTotal AS B
        ON A.[UsuarioUltimaGestion] = B.[idcuenta]
    WHERE A.FechaUltimaGestion IS NOT NULL
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
# GET DATA - TABLAS ORIGINALES + NPS
# ============================================================
def get_data(mes, semana, pais, lob, nombre_completo, nombre_superv, fecha_encuesta):
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()

    cur.execute(build_query(mes, semana, pais, lob, nombre_completo, nombre_superv, fecha_encuesta))
    rows = cur.fetchall()

    # ── AGRUPACION ORIGINAL (Responsabilidad + NivelII + NivelIII) ──
    grouped = {}
    total_general = 0

    for r in rows:
        key = (
            clean(r[0]),
            clean(r[1]),
            clean(r[2])
        )
        grouped[key] = grouped.get(key, 0) + 1

    data = []
    for k, v in grouped.items():
        total_general += v
        data.append({
            "responsabilidad": k[0],
            "motivo": k[1],
            "detalle": k[2],
            "total": v,
            "participacion": 0
        })

    cur.close()
    conn.close()

    # Ordenar mayor a menor
    data.sort(key=lambda x: x["total"], reverse=True)

    # Calcular participacion
    for r in data:
        r["participacion"] = round((r["total"] / total_general) * 100, 1) if total_general else 0

    # ── NPS ──
    grp_nps = {"Promotor": 0, "Neutro": 0, "Detractor": 0, "Sin dato": 0}
    for r in rows:
        cat = clasificar_nps(r[6])
        if cat:
            grp_nps[cat] += 1
        else:
            grp_nps["Sin dato"] += 1

    total_nps = sum(grp_nps.values())
    prom_pct = round((grp_nps["Promotor"] / total_nps) * 100, 1) if total_nps else 0
    det_pct  = round((grp_nps["Detractor"] / total_nps) * 100, 1) if total_nps else 0
    score_nps = round(prom_pct - det_pct, 1)

    tabla_nps = [
        {
            "categoria": cat,
            "total": grp_nps[cat],
            "participacion": round((grp_nps[cat] / total_nps) * 100, 1) if total_nps else 0
        }
        for cat in ["Promotor", "Neutro", "Detractor", "Sin dato"]
    ]

    # ── PASTEL RESPONSABILIDAD ──
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

    return data, total_general, tabla_nps, score_nps, pastel_resp

# ============================================================
# FILTROS DINAMICOS
# ============================================================
def get_filter_options():
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()

    f = fecha_base()

    cur.execute(f"""
        SELECT DISTINCT DATENAME(MONTH, {f})
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        WHERE A.FechaUltimaGestion IS NOT NULL
    """)
    months = [r[0] for r in cur.fetchall() if r[0]]

    cur.execute(f"""
        SELECT DISTINCT CONVERT(VARCHAR(10),
            DATEADD(WEEK, DATEDIFF(WEEK,0,{f}),0),23)
        FROM Cardif.dbo.tbCallBackNps A WITH (NOLOCK)
        WHERE A.FechaUltimaGestion IS NOT NULL
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
    mes            = request.args.get("mes")
    semana         = request.args.get("semana")
    pais           = request.args.get("pais")
    lob            = request.args.get("lob")
    nombre_completo= request.args.get("nombre_completo")
    nombre_superv  = request.args.get("nombre_superv")
    fecha_encuesta = request.args.get("fecha_encuesta")

    filtros = get_filter_options()
    data, total, tabla_nps, score_nps, pastel_resp = get_data(
        mes, semana, pais, lob, nombre_completo, nombre_superv, fecha_encuesta
    )

    return render_template(
        "index.html",
        data=data,
        top10=data[:10],
        total=total,
        tabla_nps=tabla_nps,
        score_nps=score_nps,
        pastel_resp=pastel_resp,
        mes=mes,
        semana=semana,
        pais=pais,
        lob=lob,
        nombre_completo=nombre_completo,
        nombre_superv=nombre_superv,
        fecha_encuesta=fecha_encuesta,
        **filtros
    )

# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    print("🚀 Dashboard Cardif iniciando...")
    app.run(host="0.0.0.0", port=5000, debug=True)
