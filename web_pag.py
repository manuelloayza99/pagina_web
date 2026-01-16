# app.py
import streamlit as st
import pandas as pd
import boto3
import json
import time
import altair as alt

# ── CREDENCIALES ── NUNCA en el código ────────────────────────────────
# Usar st.secrets (en .streamlit/secrets.toml o en variables de entorno en la nube)
try:
    AWS_KEY    = st.secrets["aws"]["access_key_id"]
    AWS_SECRET = st.secrets["aws"]["secret_access_key"]
    BUCKET     = st.secrets["aws"]["bucket_name"]
    REGION     = st.secrets["aws"].get("region", "us-east-2")
except Exception:
    st.error("Faltan credenciales AWS en st.secrets")
    st.stop()

# Cliente S3 cacheado
@st.cache_resource
def get_s3():
    return boto3.client(
        's3',
        aws_access_key_id=AWS_KEY,
        aws_secret_access_key=AWS_SECRET,
        region_name=REGION
    )

s3 = get_s3()

# Estados iniciales
defaults = {
    'conexion_s3': "Desconocido",
    'estado_json': "Pendiente",
    'estado_csv': "Pendiente",
    'pausado': False,
    'historial_vivo': pd.DataFrame(columns=["hora", "voltaje", "corriente", "potencia", "sd"]),
    'consumo_acumulado': 0.0
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Página ───────────────────────────────────────────────────────────
st.set_page_config(page_title="Gestión Energética", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetric"] {
        background: white;
        padding: 16px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
    }
    </style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────
st.sidebar.title("Panel de Control")

# Estados visuales
st.sidebar.success("S3: Conectado") if st.session_state.conexion_s3 == "Conectado" else \
st.sidebar.error("S3: Desconectado") if st.session_state.conexion_s3 == "Desconectado" else \
st.sidebar.info("S3: Desconocido")

st.sidebar.success("JSON: OK") if st.session_state.estado_json == "Leyendo correctamente" else \
st.sidebar.error("JSON: Error") if st.session_state.estado_json == "Error" else \
st.sidebar.info("JSON: Pendiente")

st.sidebar.success("CSV: OK") if st.session_state.estado_csv == "Leyendo correctamente" else \
st.sidebar.error("CSV: Error") if st.session_state.estado_csv == "Error" else \
st.sidebar.info("CSV: Pendiente")

vista = st.sidebar.radio("Vista", ["Tiempo Real", "Histórico"])

if vista == "Tiempo Real":
    if st.sidebar.button("⏸️ Pausar" if not st.session_state.pausado else "▶️ Reanudar"):
        st.session_state.pausado = not st.session_state.pausado
        st.rerun()

# ── Contenido principal ──────────────────────────────────────────────
if vista == "Tiempo Real":

    st.title("Telemetría en Tiempo Real")

    if st.session_state.pausado:
        st.info("Actualización pausada")
        st.button("Reanudar", type="primary")
    else:
        placeholder = st.empty()

        with placeholder.container():
            try:
                obj = s3.get_object(Bucket=BUCKET, Key="ultimo_dato.json")
                dato = json.loads(obj['Body'].read().decode())

                st.session_state.conexion_s3 = "Conectado"
                st.session_state.estado_json = "Leyendo correctamente"

                # Evitar duplicados por hora
                if st.session_state.historial_vivo.empty or dato.get('hora') != st.session_state.historial_vivo.iloc[-1]['hora']:
                    row = {
                        'hora': dato['hora'],
                        'voltaje': float(dato.get('voltaje', 0)),
                        'corriente': float(dato.get('corriente', 0)),
                        'potencia': float(dato.get('potencia', 0)),
                        'sd': str(dato.get('sd', '0'))
                    }
                    st.session_state.historial_vivo = pd.concat([
                        st.session_state.historial_vivo,
                        pd.DataFrame([row])
                    ], ignore_index=True).tail(60)  # últimos 60 puntos (~2 min)

                    # Consumo (asumiendo ~2 s entre lecturas)
                    st.session_state.consumo_acumulado += row['potencia'] * (2 / 3600)

                ult = st.session_state.historial_vivo.iloc[-1]

                cols = st.columns(4)
                cols[0].metric("Voltaje", f"{ult['voltaje']:.3f} V")
                cols[1].metric("Corriente", f"{ult['corriente']:.3f} A")
                cols[2].metric("Potencia", f"{ult['potencia']:.3f} W")
                cols[3].metric("SD", ult['sd'])

                cols2 = st.columns(2)
                cols2[0].metric("Consumo Acum.", f"{st.session_state.consumo_acumulado:.4f} Wh")
                cols2[1].metric("Tiempo op.", f"{len(st.session_state.historial_vivo)*2/3600:.2f} h")

                if ult['voltaje'] < 220:
                    st.warning("⚠️ Voltaje bajo detectado")

                for var, color, titulo in [
                    ("voltaje", "blue", "Voltaje"),
                    ("corriente", "red", "Corriente"),
                    ("potencia", "green", "Potencia")
                ]:
                    st.subheader(f"Tendencia – {titulo}")
                    ch = alt.Chart(st.session_state.historial_vivo).mark_line(color=color).encode(
                        x=alt.X('hora:N', title="Hora"),
                        y=alt.Y(f"{var}:Q", title=f"{titulo}", scale=alt.Scale(zero=False))
                    ).properties(height=280)
                    st.altair_chart(ch, use_container_width=True)

                st.subheader("Registros recientes")
                st.dataframe(st.session_state.historial_vivo.sort_index(ascending=False), use_container_width=True, hide_index=True)

                if st.button("Descargar sesión actual"):
                    st.download_button(
                        "Descargar CSV",
                        st.session_state.historial_vivo.to_csv(index=False),
                        "historial_tiempo_real.csv",
                        "text/csv"
                    )

            except Exception as e:
                st.session_state.conexion_s3 = "Desconectado"
                st.session_state.estado_json = "Error"
                st.info("Reconectando...")

        # Espera y rerun (solo si no pausado)
        if not st.session_state.pausado:
            time.sleep(2.0)
            st.rerun()

else:  # Histórico

    st.title("Análisis Histórico")

    try:
        resp = s3.list_objects_v2(Bucket=BUCKET)
        archivos = sorted(
            [o['Key'] for o in resp.get('Contents', []) if o['Key'].endswith('.csv')],
            reverse=True
        )
        st.session_state.conexion_s3 = "Conectado"
    except:
        st.session_state.conexion_s3 = "Desconectado"
        archivos = []
        st.error("No se pudo listar archivos")

    if archivos:
        sel = st.selectbox("Archivo", archivos)

        if st.button("Cargar y analizar", type="primary"):
            try:
                obj = s3.get_object(Bucket=BUCKET, Key=sel)
                df = pd.read_csv(obj['Body'], names=["fecha","hora","voltaje","corriente","potencia","sd"])
                df['voltaje'] = pd.to_numeric(df['voltaje'], errors='coerce')
                df['potencia'] = pd.to_numeric(df['potencia'], errors='coerce')
                df['corriente'] = pd.to_numeric(df['corriente'], errors='coerce')

                st.session_state.estado_csv = "Leyendo correctamente"

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("V máx", f"{df['voltaje'].max():.2f} V")
                c2.metric("V mín", f"{df['voltaje'].min():.2f} V")
                c3.metric("Estabilidad (std)", f"{df['voltaje'].std():.3f}")
                energia = df['potencia'].sum() * 5 / 3600
                c4.metric("Energía total", f"{energia:.4f} Wh")

                c5, c6 = st.columns(2)
                c5.metric("Potencia prom.", f"{df['potencia'].mean():.2f} W")
                c6.metric("Tiempo total", f"{len(df)*5/3600:.2f} h")

                if len(df) > 1:
                    st.metric("Corr. V-I", f"{df['voltaje'].corr(df['corriente']):.2f}")

                for var, color, tit in [("voltaje","blue","Voltaje"), ("corriente","red","Corriente"), ("potencia","green","Potencia")]:
                    st.subheader(f"Tendencia – {tit}")
                    ch = alt.Chart(df).mark_line(color=color).encode(
                        x='hora:N', y=f"{var}:Q", scale=alt.Scale(zero=False)
                    ).properties(height=280)
                    st.altair_chart(ch, use_container_width=True)

                st.subheader("Distribución Voltaje")
                hist = alt.Chart(df).mark_bar(color='#555').encode(
                    x=alt.X("voltaje:Q", bin=alt.Bin(maxbins=20)),
                    y='count()'
                ).properties(height=300)
                st.altair_chart(hist, use_container_width=True)

                st.download_button(
                    "Descargar datos",
                    df.to_csv(index=False),
                    f"{sel.replace('.csv','')}_procesado.csv",
                    "text/csv"
                )

            except Exception as e:
                st.session_state.estado_csv = "Error"
                st.error(f"Error al leer archivo: {e}")
    else:
        st.info("No hay archivos .csv en el bucket")
