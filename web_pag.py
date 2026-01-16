import streamlit as st
import pandas as pd
import boto3
import json
import time
import altair as alt

# ────────────────────────────────────────────────
# CONFIGURACIÓN AWS – usando Streamlit secrets
# ────────────────────────────────────────────────
try:
    s3 = boto3.client(
        's3',
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY"],
        aws_secret_access_key=st.secrets["AWS_SECRET_KEY"],
        region_name=st.secrets["AWS_REGION"]
    )
    BUCKET = st.secrets["AWS_BUCKET_NAME"]
except Exception as e:
    st.error("⚠️ No se pudieron cargar las credenciales AWS desde secrets.\n"
             "Verifica que estén definidas en .streamlit/secrets.toml o en Streamlit Cloud.")
    st.stop()

# ────────────────────────────────────────────────
# Configuración de página
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Sistema de Gestión Energética",
    layout="wide"
)

# ────────────────────────────────────────────────
# ESTILOS PERSONALIZADOS
# ────────────────────────────────────────────────
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetric"] {
        background-color: #ffffff !important;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────
# FUNCIONES DE APOYO
# ────────────────────────────────────────────────
def listar_archivos_csv_s3():
    try:
        response = s3.list_objects_v2(Bucket=BUCKET)
        archivos = [
            obj['Key'] for obj in response.get('Contents', [])
            if obj['Key'].startswith('registro_') and obj['Key'].endswith('.csv')
        ]
        return sorted(archivos, reverse=True)
    except Exception as e:
        st.sidebar.error(f"No se pudo listar archivos: {str(e)}")
        return []

def generar_grafico(df, variable, color, titulo_y, unidad=""):
    df[variable] = pd.to_numeric(df[variable], errors='coerce')
    df = df.dropna(subset=[variable])
    
    chart = alt.Chart(df).mark_line(
        color=color,
        strokeWidth=2,
        interpolate='monotone'
    ).encode(
        x=alt.X('hora:N', title='Tiempo', axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(f'{variable}:Q', title=f"{titulo_y} ({unidad})", scale=alt.Scale(zero=False)),
        tooltip=['hora', variable]
    ).properties(height=350)
    
    return chart + chart.mark_point(size=50, color=color, fill='white')

# ────────────────────────────────────────────────
# NAVEGACIÓN LATERAL
# ────────────────────────────────────────────────
st.sidebar.title("Menú de Control")
opcion = st.sidebar.radio("Seleccione una vista:", ["⚡ Tiempo Real (JSON)", "📅 Histórico (CSV)"])

st.sidebar.markdown("---")
st.sidebar.caption(f"Bucket: **{BUCKET}**")
st.sidebar.caption(f"Región: **{st.secrets.get('AWS_REGION', 'no especificada')}**")

# ────────────────────────────────────────────────
# VISTA 1: TIEMPO REAL
# ────────────────────────────────────────────────
if opcion == "⚡ Tiempo Real (JSON)":
    st.title("Telemetría Energética en Vivo")
    st.caption(f"Monitoreo en tiempo real – bucket: {BUCKET}")

    if 'historial_vivo' not in st.session_state:
        st.session_state.historial_vivo = pd.DataFrame(
            columns=["hora", "voltaje", "corriente", "potencia"]
        )

    placeholder_status = st.empty()
    placeholder_metrics = st.empty()
    placeholder_charts = st.empty()
    placeholder_table = st.empty()

    if st.sidebar.button("Reiniciar Gráfico y Sesión"):
        st.session_state.historial_vivo = pd.DataFrame(
            columns=["hora", "voltaje", "corriente", "potencia"]
        )
        st.rerun()

    while True:
        try:
            obj = s3.get_object(Bucket=BUCKET, Key="ultimo_dato.json")
            contenido = obj['Body'].read().decode('utf-8').strip()

            if contenido:
                dato_actual = json.loads(contenido)
                placeholder_status.empty()

                if st.session_state.historial_vivo.empty or \
                   dato_actual.get('hora') != st.session_state.historial_vivo.iloc[-1]['hora']:

                    nuevo_punto = pd.DataFrame([{
                        'hora': dato_actual.get('hora', '—'),
                        'voltaje': float(dato_actual.get('voltaje', 0)),
                        'corriente': float(dato_actual.get('corriente', 0)),
                        'potencia': float(dato_actual.get('potencia', 0))
                    }])

                    st.session_state.historial_vivo = pd.concat(
                        [st.session_state.historial_vivo, nuevo_punto],
                        ignore_index=True
                    ).tail(30)

                with placeholder_metrics.container():
                    if not st.session_state.historial_vivo.empty:
                        ult = st.session_state.historial_vivo.iloc[-1]
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Voltaje Actual", f"{ult['voltaje']:.2f} V")
                        m2.metric("Corriente Actual", f"{ult['corriente']:.2f} A")
                        m3.metric("Potencia Actual", f"{ult['potencia']:.2f} W")

                with placeholder_charts.container():
                    col1, col2 = st.columns(2)
                    with col1:
                        st.altair_chart(
                            generar_grafico(st.session_state.historial_vivo, 'voltaje', '#FF4B4B', 'Tensión', 'V'),
                            use_container_width=True
                        )
                    with col2:
                        st.altair_chart(
                            generar_grafico(st.session_state.historial_vivo, 'potencia', '#2ECC71', 'Potencia', 'W'),
                            use_container_width=True
                        )

                with placeholder_table.container():
                    st.subheader("Registros de la sesión actual (últimos 30)")
                    st.dataframe(
                        st.session_state.historial_vivo.sort_index(ascending=False),
                        use_container_width=True
                    )

        except Exception:
            placeholder_status.info("🔄 Sincronizando datos... (esperando nuevo JSON)")

        time.sleep(2)

# ────────────────────────────────────────────────
# VISTA 2: HISTÓRICO
# ────────────────────────────────────────────────
else:
    st.title("Historial de Consumo")

    archivos_csv = listar_archivos_csv_s3()

    if archivos_csv:
        archivo_sel = st.selectbox("Seleccione un reporte diario:", archivos_csv)

        if st.button("Cargar y Analizar Reporte"):
            try:
                obj = s3.get_object(Bucket=BUCKET, Key=archivo_sel)
                df_hist = pd.read_csv(
                    obj['Body'],
                    names=["fecha", "hora", "voltaje", "corriente", "potencia", "sd"],
                    on_bad_lines='skip'
                )

                # Convertir columnas numéricas
                for col in ["voltaje", "corriente", "potencia"]:
                    df_hist[col] = pd.to_numeric(df_hist[col], errors='coerce')

                st.success(f"Reporte cargado: **{archivo_sel}**  ({len(df_hist)} registros)")

                # Última medición (valores más recientes)
                if not df_hist.empty:
                    ultimo = df_hist.iloc[-1]
                    st.subheader("Última medición registrada")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Voltaje", f"{ultimo['voltaje']:.2f} V" if pd.notna(ultimo['voltaje']) else "—")
                    m2.metric("Corriente", f"{ultimo['corriente']:.2f} A" if pd.notna(ultimo['corriente']) else "—")
                    m3.metric("Potencia", f"{ultimo['potencia']:.2f} W" if pd.notna(ultimo['potencia']) else "—")

                # Resumen estadístico
                st.subheader("Resumen del período")
                h1, h2, h3, h4 = st.columns(4)
                h1.metric("Voltaje Máximo",   f"{df_hist['voltaje'].max():.2f} V"   if not df_hist['voltaje'].isna().all() else "—")
                h2.metric("Voltaje Promedio", f"{df_hist['voltaje'].mean():.2f} V" if not df_hist['voltaje'].isna().all() else "—")
                h3.metric("Potencia Promedio",f"{df_hist['potencia'].mean():.2f} W" if not df_hist['potencia'].isna().all() else "—")
                h4.metric("Registros Totales", len(df_hist))

                # Gráficos
                st.altair_chart(
                    generar_grafico(df_hist, 'voltaje', '#1f77b4', 'Voltaje', 'V'),
                    use_container_width=True
                )
                st.altair_chart(
                    generar_grafico(df_hist, 'potencia', '#27ae60', 'Potencia', 'W'),
                    use_container_width=True
                )

                # Tabla completa
                st.subheader("Tabla completa del reporte")
                st.dataframe(df_hist, use_container_width=True)

            except Exception as e:
                st.error(f"Error al procesar el archivo:\n{str(e)}")

    else:
        st.warning("No se encontraron archivos CSV con prefijo 'registro_' en el bucket.")
