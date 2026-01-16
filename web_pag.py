import streamlit as st
import pandas as pd
import boto3
import json
import time
import altair as alt

# --- CONFIGURACIÓN AWS (USANDO STREAMLIT SECRETS) ---
# En GitHub, este código no tendrá las llaves. Se leerán desde Streamlit Cloud.
try:
    s3 = boto3.client(
        's3', 
        AWS_ACCESS_KEY=st.secrets["AWS_ACCESS_KEY"], 
        AWS_SECRET_KEY=st.secrets["AWS_SECRET_KEY"], 
        AWS_REGION=st.secrets["AWS_REGION"]
    )
    AWS_BUCKET_NAME= st.secrets["AWS_BUCKET_NAME"]
except Exception as e:
    st.error("⚠️ Error de Configuración: No se encontraron las credenciales en secretos.")
    st.stop()

# Configuración de página
# Inicializar estados de conexión y lectura
if 'conexion_s3' not in st.session_state:
    st.session_state.conexion_s3 = "Desconocido"
if 'estado_json' not in st.session_state:
    st.session_state.estado_json = "Pendiente"
if 'estado_csv' not in st.session_state:
    st.session_state.estado_csv = "Pendiente"

try:
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name=REGION)
    st.session_state.conexion_s3 = "Conectado"
except Exception as e:
    st.error(f"Error de Conexion AWS: {e}")
    st.session_state.conexion_s3 = "Desconectado"
    st.stop()

st.set_page_config(page_title="Sistema de Gestion Energetica", layout="wide")

# --- ESTILOS PROFESIONALES ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetric"] { background-color: #ffffff !important; padding: 20px; border-radius: 10px; border: 1px solid #dee2e6; }
    [data-testid="stMetricLabel"] { color: #31333F !important; }
    [data-testid="stMetricValue"] { color: #1a1c23 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- NAVEGACIÓN ---
st.sidebar.title("Panel de Control")
# Indicador de conectividad en la sidebar
if st.session_state.conexion_s3 == "Conectado":
    st.sidebar.success("Estado Conexión S3: Conectado")
elif st.session_state.conexion_s3 == "Desconectado":
    st.sidebar.error("Estado Conexión S3: Desconectado")
else:
    st.sidebar.info("Estado Conexión S3: Desconocido")

# Indicadores de lectura JSON y CSV
if st.session_state.estado_json == "Leyendo correctamente":
    st.sidebar.success("Estado JSON: Leyendo correctamente")
elif st.session_state.estado_json == "Error":
    st.sidebar.error("Estado JSON: Error al leer")
else:
    st.sidebar.info("Estado JSON: Pendiente")

if st.session_state.estado_csv == "Leyendo correctamente":
    st.sidebar.success("Estado CSV: Leyendo correctamente")
elif st.session_state.estado_csv == "Error":
    st.sidebar.error("Estado CSV: Error al leer")
else:
    st.sidebar.info("Estado CSV: Pendiente")

opcion = st.sidebar.radio("Seleccione vista:", ["Tiempo Real", "Historico"])

# Contenedor Maestro para evitar que se peguen elementos
main_placeholder = st.empty()

if opcion == "Tiempo Real":
    main_placeholder.empty()  # Limpiar contenido residual
    if 'historial_vivo' not in st.session_state:
        st.session_state.historial_vivo = pd.DataFrame(columns=["hora", "voltaje", "corriente", "potencia", "sd"])
        st.session_state.consumo_acumulado = 0.0  # Nuevo: Consumo acumulado

    # Controles adicionales (eliminé el slider de frecuencia)
    pausa = st.sidebar.button("Pausar/Reanudar")
    if 'pausado' not in st.session_state:
        st.session_state.pausado = False
    if pausa:
        st.session_state.pausado = not st.session_state.pausado

    while opcion == "Tiempo Real" and not st.session_state.pausado:
        with main_placeholder.container():
            st.title("Telemetria Energetica en Tiempo Real")
            try:
                obj = s3.get_object(Bucket=BUCKET, Key="ultimo_dato.json")
                dato = json.loads(obj['Body'].read().decode('utf-8'))
                st.session_state.conexion_s3 = "Conectado"  # Actualizar estado en éxito
                st.session_state.estado_json = "Leyendo correctamente"  # JSON leído correctamente
                
                if st.session_state.historial_vivo.empty or dato['hora'] != st.session_state.historial_vivo.iloc[-1]['hora']:
                    nuevo = pd.DataFrame([{'hora': dato['hora'], 'voltaje': float(dato.get('voltaje', 0)), 
                                          'corriente': float(dato.get('corriente', 0)), 'potencia': float(dato.get('potencia', 0)), 
                                          'sd': str(dato.get('sd', '0'))}])
                    st.session_state.historial_vivo = pd.concat([st.session_state.historial_vivo, nuevo], ignore_index=True).tail(30)
                    # Actualizar consumo acumulado (frecuencia fija en 2 seg)
                    st.session_state.consumo_acumulado += float(dato.get('potencia', 0)) * (2 / 3600)

                ult = st.session_state.historial_vivo.iloc[-1]
                
                # METRICAS SIMPLIFICADAS: Solo Voltaje, Corriente, Potencia y SD
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Voltaje", f"{ult['voltaje']:.3f} V")
                m2.metric("Corriente", f"{ult['corriente']:.3f} A")
                m3.metric("Potencia", f"{ult['potencia']:.3f} W")
                m4.metric("SD", ult['sd'])

                # Métricas adicionales
                a1, a2 = st.columns(2)
                a1.metric("Consumo Acumulado", f"{st.session_state.consumo_acumulado:.4f} Wh")
                tiempo_op = len(st.session_state.historial_vivo) * 2 / 3600  # Frecuencia fija en 2 seg
                a2.metric("Tiempo de Operación", f"{tiempo_op:.2f} horas")

                # Alertas
                if ult['voltaje'] < 220:
                    st.warning("Alerta: Voltaje bajo detectado!")

                st.subheader("Tendencia Instantanea - Voltaje")
                chart_voltaje = alt.Chart(st.session_state.historial_vivo).mark_line(color='blue').encode(
                    x=alt.X('hora:N', title='Tiempo'), y=alt.Y('voltaje:Q', title='Voltaje (V)', scale=alt.Scale(zero=False))
                ).properties(height=300)  # Aumentado a 300
                st.altair_chart(chart_voltaje, use_container_width=True)

                st.subheader("Tendencia Instantanea - Corriente")
                chart_corriente = alt.Chart(st.session_state.historial_vivo).mark_line(color='red').encode(
                    x=alt.X('hora:N', title='Tiempo'), y=alt.Y('corriente:Q', title='Corriente (A)', scale=alt.Scale(zero=False))
                ).properties(height=300)  # Aumentado a 300
                st.altair_chart(chart_corriente, use_container_width=True)

                st.subheader("Tendencia Instantanea - Potencia")
                chart_potencia = alt.Chart(st.session_state.historial_vivo).mark_line(color='green').encode(
                    x=alt.X('hora:N', title='Tiempo'), y=alt.Y('potencia:Q', title='Potencia (W)', scale=alt.Scale(zero=False))
                ).properties(height=300)  # Aumentado a 300
                st.altair_chart(chart_potencia, use_container_width=True)

                st.subheader("Registros de la Sesion Actual")
                st.dataframe(st.session_state.historial_vivo.sort_index(ascending=False), use_container_width=True, key="tabla_real_time")

                # Exportar datos
                if st.button("Descargar Historial Actual como CSV"):
                    csv = st.session_state.historial_vivo.to_csv(index=False)
                    st.download_button("Descargar", csv, "historial_real_time.csv", "text/csv")

            except Exception:
                st.session_state.conexion_s3 = "Desconectado"  # Actualizar estado en error
                st.session_state.estado_json = "Error"  # Error al leer JSON
                st.info("Sincronizando flujo de datos...")
            
            time.sleep(2)  # Frecuencia fija en 2 segundos
            if opcion != "Tiempo Real": break

else:
    # SECCION HISTORICO TOTALMENTE INDEPENDIENTE
    main_placeholder.empty()  # Limpiar contenido residual
    with main_placeholder.container():
        st.title("Analisis de Datos Historicos")
        try:
            response = s3.list_objects_v2(Bucket=BUCKET)
            st.session_state.conexion_s3 = "Conectado"  # Actualizar estado en éxito
            archivos = sorted([obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.csv')], reverse=True)
        except Exception:
            st.session_state.conexion_s3 = "Desconectado"  # Actualizar estado en error
            archivos = []
            st.error("Error al acceder a archivos históricos. Verifique la conexión.")
        
        if archivos:
            archivo_sel = st.selectbox("Seleccione reporte para analisis:", archivos)  # Solo esta opción, sin filtros

            if st.button("Generar Reporte Detallado"):
                try:
                    obj = s3.get_object(Bucket=BUCKET, Key=archivo_sel)
                    st.session_state.conexion_s3 = "Conectado"  # Actualizar estado en éxito
                    df = pd.read_csv(obj['Body'], names=["fecha", "hora", "voltaje", "corriente", "potencia", "sd"])
                    df['voltaje'] = pd.to_numeric(df['voltaje'], errors='coerce')
                    df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
                    # Sin filtros aplicados
                    st.session_state.estado_csv = "Leyendo correctamente"  # CSV leído correctamente
                    
                    # METRICAS NUEVAS HISTORICO
                    h1, h2, h3, h4 = st.columns(4)
                    h1.metric("Voltaje Maximo", f"{df['voltaje'].max():.2f} V")
                    h2.metric("Voltaje Minimo", f"{df['voltaje'].min():.2f} V")
                    h3.metric("Estabilidad (SDV)", f"{df['voltaje'].std():.3f}")
                    energia = (df['potencia'].sum() * 5) / 3600
                    h4.metric("Energia Total", f"{energia:.4f} Wh")

                    # Métricas adicionales
                    p1, p2 = st.columns(2)
                    p1.metric("Promedio Potencia", f"{df['potencia'].mean():.2f} W")
                    tiempo_total = len(df) * 5 / 3600  # Asumiendo 5 seg por fila
                    p2.metric("Tiempo Total Operación", f"{tiempo_total:.2f} horas")

                    # Correlación manual usando pandas (sin scipy)
                    if len(df) > 1:
                        corr = df['voltaje'].corr(df['corriente'])
                        st.metric("Correlación V-I", f"{corr:.2f}")

                    # Gráficos separados como en Tiempo Real
                    st.subheader("Tendencia Historica - Voltaje")
                    chart_voltaje_hist = alt.Chart(df).mark_line(color='blue').encode(
                        x=alt.X('hora:N', title='Tiempo'), y=alt.Y('voltaje:Q', title='Voltaje (V)', scale=alt.Scale(zero=False))
                    ).properties(height=300)
                    st.altair_chart(chart_voltaje_hist, use_container_width=True)

                    st.subheader("Tendencia Historica - Corriente")
                    chart_corriente_hist = alt.Chart(df).mark_line(color='red').encode(
                        x=alt.X('hora:N', title='Tiempo'), y=alt.Y('corriente:Q', title='Corriente (A)', scale=alt.Scale(zero=False))
                    ).properties(height=300)
                    st.altair_chart(chart_corriente_hist, use_container_width=True)

                    st.subheader("Tendencia Historica - Potencia")
                    chart_potencia_hist = alt.Chart(df).mark_line(color='green').encode(
                        x=alt.X('hora:N', title='Tiempo'), y=alt.Y('potencia:Q', title='Potencia (W)', scale=alt.Scale(zero=False))
                    ).properties(height=300)
                    st.altair_chart(chart_potencia_hist, use_container_width=True)

                    st.subheader("Analisis de Estabilidad de Voltaje")
                    hist = alt.Chart(df).mark_bar(color='#555555').encode(
                        x=alt.X("voltaje:Q", bin=alt.Bin(maxbins=15), title="Rango de Voltaje"),
                        y=alt.Y('count()', title='Frecuencia')
                    ).properties(height=300)
                    st.altair_chart(hist, use_container_width=True)

                    # Gráfico adicional: Scatter Voltaje vs Corriente
                    st.subheader("Relación Voltaje-Corriente")
                    scatter = alt.Chart(df).mark_circle().encode(
                        x='voltaje:Q', y='corriente:Q', tooltip=['voltaje', 'corriente']
                    ).properties(height=300)
                    st.altair_chart(scatter, use_container_width=True)

                    # Exportar datos filtrados
                    if st.button("Descargar Datos Filtrados como CSV"):
                        csv = df.to_csv(index=False)
                        st.download_button("Descargar", csv, "datos_filtrados.csv", "text/csv")
                except Exception:
                    st.session_state.conexion_s3 = "Desconectado"  # Actualizar estado en error
                    st.session_state.estado_csv = "Error"  # Error al leer CSV
                    st.error("Error al cargar el archivo seleccionado. Verifique la conexión.")

