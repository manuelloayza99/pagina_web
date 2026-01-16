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

                # Convertir columnas numéricas una sola vez
                for col in ["voltaje", "corriente", "potencia"]:
                    df_hist[col] = pd.to_numeric(df_hist[col], errors='coerce')

                st.success(f"Reporte cargado: **{archivo_sel}**  ({len(df_hist)} registros)")

                # ── Último registro (valores más recientes) ──
                if not df_hist.empty:
                    ultimo = df_hist.iloc[-1]

                    st.subheader("Última medición registrada")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Voltaje", f"{ultimo['voltaje']:.2f} V" if pd.notna(ultimo['voltaje']) else "—")
                    m2.metric("Corriente", f"{ultimo['corriente']:.2f} A" if pd.notna(ultimo['corriente']) else "—")
                    m3.metric("Potencia", f"{ultimo['potencia']:.2f} W" if pd.notna(ultimo['potencia']) else "—")

                # ── Métricas agregadas (estadísticas generales) ──
                st.subheader("Resumen del período")
                h1, h2, h3, h4 = st.columns(4)
                h1.metric("Voltaje Máximo",   f"{df_hist['voltaje'].max():.2f} V"   if not df_hist['voltaje'].empty else "—")
                h2.metric("Voltaje Promedio", f"{df_hist['voltaje'].mean():.2f} V" if not df_hist['voltaje'].empty else "—")
                h3.metric("Potencia Promedio",f"{df_hist['potencia'].mean():.2f} W" if not df_hist['potencia'].empty else "—")
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
