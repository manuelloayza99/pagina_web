# app.py
import streamlit as st
import pandas as pd
import boto3
import json
import time
import altair as alt

# ────────────────────────────────────────────────
#  CONFIGURACIÓN AWS - USAR st.secrets (NO HARDCODEAR)
# ────────────────────────────────────────────────
try:
    ACCESS_KEY = st.secrets["aws"]["access_key_id"]
    SECRET_KEY = st.secrets["aws"]["secret_access_key"]
    BUCKET     = st.secrets["aws"]["bucket"]
    REGION     = st.secrets["aws"].get("region", "us-east-2")
except Exception as e:
    st.error("No se encuentran las credenciales AWS en st.secrets. Configúralas en .streamlit/secrets.toml (local) o en la plataforma de despliegue.")
    st.stop()

# Cliente S3 (cacheado para no recrearlo cada rerun)
@st.cache_resource
def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=REGION
    )

s3 = get_s3_client()

# ────────────────────────────────────────────────
#  Estados de sesión
# ────────────────────────────────────────────────
if 'conexion_s3' not in st.session_state:
    st.session_state.conexion_s3 = "Desconocido"
if 'estado_json' not in st.session_state:
    st.session_state.estado_json = "Pendiente"
if 'estado_csv' not in st.session_state:
    st.session_state.estado_csv = "Pendiente"
if 'historial_vivo' not in st.session_state:
    st.session_state.historial_vivo = pd.DataFrame(columns=["hora", "voltaje", "corriente", "potencia", "sd"])
    st.session_state.consumo_acumulado = 0.0
if 'pausado' not in st.session_state:
    st.session_state.pausado = False


st.set_page_config(page_title="Sistema de Gestión Energética", layout="wide")

# ────────────────────────────────────────────────
#  ESTILOS
# ────────────────────────────────────────────────
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetric"] {
        background-color: #ffffff !important;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
    }
    </style>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────
#  SIDEBAR
# ────────────────────────────────────────────────
st.sidebar.title("Panel de Control")

# Indicadores de estado
if st.session_state.conexion_s3 == "Conectado":
    st.sidebar.success("Conexión S3: Conectado")
else:
    st.sidebar.error("Conexión S3: Desconectado")

if st.session_state.estado_json == "Leyendo correctamente":
    st.sidebar.success("JSON: OK")
elif st.session_state.estado_json == "Error":
    st.sidebar.error("JSON: Error")
else:
    st.sidebar.info("JSON: Pendiente")

if st.session_state.estado_csv == "Leyendo correctamente":
    st.sidebar.success("CSV: OK")
elif st.session_state.estado_csv == "Error":
    st.sidebar.error("CSV: Error")
else:
    st.sidebar.info("CSV: Pendiente")


opcion = st.sidebar.radio("Seleccione vista:", ["Tiempo Real", "Histórico"])

# Botón pausar solo visible en Tiempo Real
if opcion == "Tiempo Real":
    if st.sidebar.button("Pausar / Reanudar"):
        st.session_state.pausado = not st.session_state.pausado
        st.rerun()  # Refresca inmediatamente


# ────────────────────────────────────────────────
#  CONTENIDO PRINCIPAL
# ────────────────────────────────────────────────
placeholder = st.empty()

if opcion == "Tiempo Real":
    placeholder.empty()

    with placeholder.container():
        st.title("Telemetría Energética en Tiempo Real")

        if st.session_state.pausado:
            st.info("Actualización pausada. Presiona 'Reanudar' en la sidebar.")
        else:
            try:
                obj = s3.get_object(Bucket=BUCKET, Key="ultimo_dato.json")
                dato = json.loads(obj['Body'].read().decode('utf-8'))

                st.session_state.conexion_s3 = "Conectado"
                st.session_state.estado_json = "Leyendo correctamente"

                # Agregar solo si es nuevo
                if st.session_state.historial_vivo.empty or dato['hora'] != st.session_state.historial_vivo.iloc[-1]['hora']:
                    nuevo = pd.DataFrame([{
                        'hora': dato['hora'],
                        'voltaje': float(dato.get('voltaje', 0)),
                        'corriente': float(dato.get('corriente', 0)),
                        'potencia': float(dato.get('potencia', 0)),
                        'sd': str(dato.get('sd', '0'))
                    }])
                    st.session_state.historial_vivo = pd.concat(
                        [st.session_state.historial_vivo, nuevo], ignore_index=True
                    ).tail(60)  # Puedes aumentar a 100–200 si quieres más historia

                    st.session_state.consumo_acumulado += float(dato.get('potencia', 0)) * (2 / 3600)

                ult = st.session_state.historial_vivo.iloc[-1]

                # Métricas
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Voltaje", f"{ult['voltaje']:.3f} V")
                m2.metric("Corriente", f"{ult['corriente']:.3f} A")
                m3.metric("Potencia", f"{ult['potencia']:.3f} W")
                m4.metric("SD", ult['sd'])

                a1, a2 = st.columns(2)
                a1.metric("Consumo Acumulado", f"{st.session_state.consumo_acumulado:.4f} Wh")
                a2.metric("Tiempo de Operación", f"{len(st.session_state.historial_vivo) * 2 / 3600:.2f} horas")

                if ult['voltaje'] < 220:
                    st.warning("Alerta: Voltaje bajo detectado!")

                # Gráficos
                for var, color, title in [
                    ('voltaje', 'blue', 'Voltaje'),
                    ('corriente', 'red', 'Corriente'),
                    ('potencia', 'green', 'Potencia')
                ]:
                    st.subheader(f"Tendencia Instantánea - {title}")
                    chart = alt.Chart(st.session_state.historial_vivo).mark_line(color=color).encode(
                        x=alt.X('hora:N', title='Tiempo'),
                        y=alt.Y(f'{var}:Q', title=f'{title} ({var[0].upper()})', scale=alt.Scale(zero=False))
                    ).properties(height=300)
                    st.altair_chart(chart, use_container_width=True)

                st.subheader("Registros de la Sesión Actual")
                st.dataframe(st.session_state.historial_vivo.sort_index(ascending=False), use_container_width=True)

                if st.button("Descargar Historial Actual como CSV"):
                    csv = st.session_state.historial_vivo.to_csv(index=False).encode('utf-8')
                    st.download_button("Descargar", csv, "historial_real_time.csv", "text/csv")

            except Exception as e:
                st.session_state.conexion_s3 = "Desconectado"
                st.session_state.estado_json = "Error"
                st.info("Intentando reconectar... (se actualizará automáticamente)")

            # Espera y rerun automático (solo si no está pausado)
            if not st.session_state.pausado:
                time.sleep(2)
                st.rerun()

else:  # Histórico
    placeholder.empty()

    with placeholder.container():
        st.title("Análisis de Datos Históricos")

        try:
            response = s3.list_objects_v2(Bucket=BUCKET)
            archivos = sorted(
                [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.csv')],
                reverse=True
            )
            st.session_state.conexion_s3 = "Conectado"
        except Exception:
            st.session_state.conexion_s3 = "Desconectado"
            archivos = []
            st.error("No se pudo listar archivos. Verifica conexión.")

        if archivos:
            archivo_sel = st.selectbox("Seleccione reporte:", archivos)

            if st.button("Generar Reporte Detallado", type="primary"):
                try:
                    obj = s3.get_object(Bucket=BUCKET, Key=archivo_sel)
                    df = pd.read_csv(obj['Body'], names=["fecha", "hora", "voltaje", "corriente", "potencia", "sd"])
                    df['voltaje'] = pd.to_numeric(df['voltaje'], errors='coerce')
                    df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')

                    st.session_state.estado_csv = "Leyendo correctamente"

                    # Métricas
                    h1, h2, h3, h4 = st.columns(4)
                    h1.metric("Voltaje Máximo", f"{df['voltaje'].max():.2f} V")
                    h2.metric("Voltaje Mínimo", f"{df['voltaje'].min():.2f} V")
                    h3.metric("Estabilidad (std)", f"{df['voltaje'].std():.3f}")
                    energia = (df['potencia'].sum() * 5) / 3600
                    h4.metric("Energía Total", f"{energia:.4f} Wh")

                    p1, p2 = st.columns(2)
                    p1.metric("Promedio Potencia", f"{df['potencia'].mean():.2f} W")
                    p2.metric("Tiempo Total", f"{len(df) * 5 / 3600:.2f} horas")

                    if len(df) > 1:
                        corr = df['voltaje'].corr(df['corriente'])
                        st.metric("Correlación V-I", f"{corr:.2f}")

                    # Gráficos (similar a tiempo real)
                    for var, color, title in [
                        ('voltaje', 'blue', 'Voltaje'),
                        ('corriente', 'red', 'Corriente'),
                        ('potencia', 'green', 'Potencia')
                    ]:
                        st.subheader(f"Tendencia Histórica - {title}")
                        chart = alt.Chart(df).mark_line(color=color).encode(
                            x=alt.X('hora:N', title='Tiempo'),
                            y=alt.Y(f'{var}:Q', title=f'{title}', scale=alt.Scale(zero=False))
                        ).properties(height=300)
                        st.altair_chart(chart, use_container_width=True)

                    st.subheader("Análisis de Estabilidad de Voltaje")
                    hist = alt.Chart(df).mark_bar(color='#555555').encode(
                        x=alt.X("voltaje:Q", bin=alt.Bin(maxbins=15), title="Rango de Voltaje"),
                        y=alt.Y('count()', title='Frecuencia')
                    ).properties(height=300)
                    st.altair_chart(hist, use_container_width=True)

                    st.subheader("Relación Voltaje-Corriente")
                    scatter = alt.Chart(df).mark_circle().encode(
                        x='voltaje:Q', y='corriente:Q', tooltip=['voltaje', 'corriente']
                    ).properties(height=300)
                    st.altair_chart(scatter, use_container_width=True)

                    # Descarga
                    if st.button("Descargar Datos como CSV"):
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button("Descargar", csv, "datos_historicos.csv", "text/csv")

                except Exception:
                    st.session_state.estado_csv = "Error"
                    st.error("Error al cargar el archivo. Verifica conexión.")
        else:
            st.info("No hay archivos .csv disponibles en el bucket.")
