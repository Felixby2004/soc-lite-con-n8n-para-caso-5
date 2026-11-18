# Monitoreo de accesos del Caso 5

## Demostración local

Desde la carpeta `soc-lite`, con Docker Desktop iniciado, ejecuta
`.\scripts\deploy-demo.ps1`. Entra a http://localhost:8080/access con la cuenta
de demostración del README y selecciona **Cargar demostración**.

El origen `demo-vpn` contiene siete accesos simulados. El evento `travel`
alcanza 90 puntos por velocidad geográfica y dispositivo nuevo. El evento
`night` alcanza 50 por horario y dispositivo. El evento `vpn-control`
conserva 0 puntos aunque su ubicación reportada cambie. Cargar la
demostración de nuevo reutiliza los siete eventos. La muestra se activa
mediante `DEMO_MODE=true` y su puntaje es independiente de los indicadores IP.

**Ver evidencia** muestra los puntos de cada regla, la cantidad de registros
disponibles al evaluar el acceso y el perfil actual. Con permiso de alertas
puedes abrir la alerta asociada y solicitar el triaje de SOC Lite. En modo
demo, el proveedor de triaje es simulado. Con LangChain y Ollama configurados,
el agente usa el resumen de señales de la alerta para explicar el caso y
sugerir acciones. La ingesta crea alertas para revisión humana.

## Evaluación, revisión y simulación

En **Evaluación** selecciona **Demostración simulada** para consultar los siete
casos con etiquetas fijas. El desplazamiento `travel` representa un acceso
anómalo y `night` representa mantenimiento legítimo con un equipo nuevo.
Con el umbral 50, la matriz muestra un verdadero positivo, un falso positivo
y cinco verdaderos negativos. Con el umbral 95, el acceso anómalo pasa a
ser un falso negativo.

En **Operación** elige el período. Abre **Ver evidencia** en cualquier acceso,
incluidos los que quedaron por debajo del umbral, y registra una etiqueta
**Esperado** o **Anómalo** según la evidencia disponible. La nota es opcional.
Pueden revisar el Administrador, el Jefe de SOC y el Analista SOC. La
revisión queda auditada. Las etiquetas se usan para evaluar las reglas.

La distribución de puntajes y la cobertura de campos incluyen todos los
accesos del ámbito seleccionado. La matriz, precisión, sensibilidad,
especificidad y F1 se calculan sobre los accesos con etiqueta. Una métrica
sin denominador aparece como **Sin base**. Los resultados de operación
describen el subconjunto revisado y dependen de cómo se eligieron los eventos.
**Comparar umbral** aplica un punto de corte alternativo a los puntajes
guardados. El umbral operativo sigue siendo 50.

En **Importar JSON**, adjunta un archivo con un solo evento y selecciona
**Evaluar un acceso sin guardar**. Se usa el mismo cálculo que en la ingesta.
La vista muestra puntaje, severidad y contribuciones. El acceso y la alerta
solo se crean cuando eliges importar.

**Exportar** descarga la evaluación seleccionada en PDF, Word o Excel. Los
reportes incluyen matriz, métricas, cobertura y una gráfica de puntajes.
PDF y Word incluyen la gráfica a 600 ppp. Excel incluye una gráfica editable.
La exportación usa datos agregados y requiere permiso `reports:export`.

## Modelos de detección

En **Monitoreo de accesos → Modelos** puedes recorrer las siete fases con
datos de autenticación. La demo de modelos genera 1 200 filas sintéticas
reproducibles, separadas de los siete escenarios de las reglas. En
**Operación revisada** se usan los eventos del período con una etiqueta
humana guardada. La vista muestra las clases, la disponibilidad de
atributos y los días de cada partición. La etiqueta de revisión es el
objetivo. Los atributos se obtienen de lo que estaba disponible al puntuar
el evento. La identidad de la cuenta, la nota de revisión y el puntaje
heurístico total quedan fuera de las entradas del modelo.

1. **Datos.** Importa los accesos en JSON. Revisa eventos con y sin alerta
   en **Eventos y anomalías**. Consulta la composición y cobertura en **Modelos**.
2. **Entrenamiento.** Elige regresión logística o árbol de decisión, semilla y
   ensayos. El trabajador separa días UTC en 70 % desarrollo, 15 % validación y
   15 % prueba. Se requiere que ambas clases estén presentes en cada
   partición y en los pliegues. Sobre desarrollo usa cinco pliegues externos
   temporales, con tres internos para Optuna en cada uno. El umbral que
   maximiza F1 se elige en validación. La prueba se evalúa al final de cada
   ejecución. Consultar repetidamente la misma prueba puede sesgar futuras
   decisiones sobre qué modelo elegir.
3. **Evaluación.** Las curvas ROC y precisión-sensibilidad, matrices y métricas
   comparan el modelo con las reglas de SOC Lite sobre los mismos eventos
   de prueba. La diferencia de exactitud tiene un intervalo bootstrap
   agrupado por día UTC y una prueba de permutación de signos por bloque.
   La inferencia estadística depende de la representatividad y de la
   dependencia entre bloques.
4. **Explicabilidad.** La inferencia informa cuánto cambia el puntaje al
   reemplazar un atributo por su mediana de desarrollo y dejar los demás
   fijos. Las diferencias describen el comportamiento local del modelo y
   pueden interactuar.
5. **Reportes.** Exporta la evaluación entrenada en PDF, Word o Excel. PDF
   y Word incorporan las curvas a 600 ppp y Excel incluye gráficas editables.
6. **Inferencia.** Pega el JSON de un evento en una ejecución completada.
   Consulta el puntaje del modelo, su severidad orientativa, el umbral y el
   puntaje heurístico. La simulación registra la operación en la bitácora.
7. **Optimización.** **Seguimiento de Optuna** muestra la precisión promedio
   de los ensayos, los parámetros, el mejor valor de cada búsqueda y la
   configuración final. Cada ejecución guarda sus resultados, los avances y
   la huella SHA-256 de la muestra en PostgreSQL.

Administrador y Jefe de SOC pueden iniciar el entrenamiento. La cola admite
una ejecución activa por base de datos. Si el trabajador se reinicia durante
un entrenamiento, la ejecución queda marcada como interrumpida para poder
lanzar otra. El detector operativo sigue usando las reglas vigentes. Los
resultados simulados verifican el recorrido y dejan pendiente la evaluación
con accesos operativos revisados.

## Ingesta de VPN o Active Directory

Importa un archivo JSON en la interfaz o envía el mismo cuerpo a
`POST /api/v1/access/events/ingest` con el encabezado `X-Ingest-Key`.
Usa un origen estable por conector y un identificador estable por registro.
El adaptador debe normalizar los identificadores de cuentas a partir de su
directorio de origen. El siguiente ejemplo muestra una conexión directa con
metadatos de ubicación entregados por la fuente.

```json
{
  "source": "vpn-corporativa",
  "events": [
    {
      "event_id": "vpn-90210",
      "account": "empresa\\usuario",
      "occurred_at": "2026-10-09T08:05:00-05:00",
      "outcome": "success",
      "source_ip": "192.0.2.10",
      "device_id": "portatil-01",
      "network": "direct",
      "location": { "latitude": -12.05, "longitude": -77.04, "accuracy_km": 10 }
    }
  ]
}
```

Cada lote admite entre 1 y 250 eventos. Son obligatorios `event_id`, `account`,
`occurred_at` con zona horaria y `outcome` (`success` o `failure`). Si el
conector desconoce el tipo de red, omite el campo `network` o usa `unknown`.
Los otros valores admitidos son `direct`, `vpn` y `proxy`. Envía
`location` únicamente si el origen conoce las coordenadas y su margen de error.

Los lotes se evalúan por fecha. Reintentar el mismo evento devuelve un
duplicado omitido. Reusar un identificador con otros datos devuelve HTTP 409
y revierte el lote. Los eventos tardíos se evalúan con el historial anterior
a su fecha. Las decisiones previamente guardadas conservan su puntaje.

El [flujo de n8n](../n8n/soc_lite_access_monitoring_workflow.json) consulta cada
cinco minutos un adaptador HTTP de VPN o Active Directory. Configura la URL
del adaptador y sus credenciales en **Consultar accesos de VPN o AD**, y una
credencial Header Auth con `X-Ingest-Key` en **Enviar a SOC Lite**.
El adaptador entrega lotes normalizados y puede volver a incluir eventos ya
enviados. El flujo viene inactivo. Se requiere un adaptador para la fuente
real. La muestra pública OpenSSH de **Datos reales** usa su propio módulo y
conserva las limitaciones temporales del registro original.

## Puntaje y permisos

El perfil se calcula por cuenta y origen con hasta los 100 accesos exitosos
más recientes de los 30 días anteriores al evento. Los accesos que generaron
una anomalía quedan fuera del perfil. Las horas se interpretan en la zona
`TIMEZONE` configurada en el backend.

| Señal | Puntos | Condición |
| --- | ---: | --- |
| Velocidad geográfica | 60 | Conexiones directas con margen de error de hasta 50 km. Se compara con el último acceso elegible en las 12 h anteriores y se descuentan ambos márgenes. Se requieren al menos 500 km y 900 km/h. |
| Horario atípico | 20 | Al menos tres accesos históricos y ninguna hora observada dentro de dos horas de la hora actual, considerando medianoche. |
| Dispositivo nuevo | 30 | Al menos tres accesos históricos con identificador de dispositivo y un dispositivo ausente en ese historial. |
| Fallos previos | 35 | Al menos cinco fallos de la cuenta y el origen en los quince minutos anteriores a un acceso exitoso. |
| Indicador IP vigente | 60 | Coincidencia exacta con una IPv4 o IPv6 activa al importar. Aplica a accesos exitosos y fallidos. |

El total se limita a 100. A partir de 50 se registra una anomalía y se crea
una alerta. La severidad inicial es media (50–69), alta (70–84) o crítica
(85–100). Los umbrales son heurísticos y quedan disponibles en el código
para calibrarlos con eventos etiquetados de la organización.

**Administrador** y **Jefe de SOC** pueden importar y gestionar indicadores.
**Analista SOC** puede consultar perfiles y anomalías e importar accesos. Los
indicadores requieren referencia y vigencia de 1 a 365 días. Se pueden renovar
o revocar. Las operaciones del módulo se registran en la bitácora.

## Actualización de PostgreSQL

El arranque de una base nueva en Docker aplica la migración. En la demo,
`deploy-demo.ps1` también la aplica sobre un volumen existente. Para otros
despliegues con una base existente, ejecuta la migración con el rol dueño del
esquema, después de crear la base y sus roles y antes de usar el módulo.

```powershell
psql -X -v ON_ERROR_STOP=1 -U soclite -d soclite -f db/03-access-monitoring.sql
psql -X -v ON_ERROR_STOP=1 -U soclite -d soclite -f db/04-access-evaluation.sql
psql -X -v ON_ERROR_STOP=1 -U soclite -d soclite -f db/05-access-models.sql
```

Las migraciones conservan los datos existentes y pueden volver a ejecutarse.
