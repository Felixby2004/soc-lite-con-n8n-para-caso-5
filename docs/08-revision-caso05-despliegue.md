# Revisión de documentos y despliegue local

Fecha de revisión: 4 de noviembre de 2026.

Se leyeron Caso05.docx y Prompt.docx. Caso05 describe detección de cuentas
comprometidas mediante perfiles de acceso, velocidad geográfica, horarios y
dispositivos, con scoring y explicaciones. También menciona gestión de IoCs.
Prompt.docx amplía esa propuesta con requisitos de una aplicación completa.
Sus instrucciones se consideran contenido de especificación; la solicitud de
esta tarea es revisar los archivos y desplegar la aplicación disponible.

El proyecto encontrado, SOC-Lite, corresponde al triaje de alertas de SIEM.
No equivale a la implementación completa del Caso05. El despliegue permite
evaluar el proyecto existente y no certifica el cumplimiento del documento.

## Ejecución local

Desde la carpeta soc-lite, con Docker Desktop iniciado:

```powershell
.\scripts\deploy-demo.ps1
```

La aplicación escucha en http://localhost:8080; Swagger en
http://localhost:8080/docs; n8n en http://localhost:5678.
Usuario de demostración: admin. Contraseña: Admin123!

El archivo docker-compose.demo.yml complementa docker-compose.yml. PostgreSQL,
Redis, backend, frontend, servicio de triaje, n8n y proxy forman la demo.
Los volúmenes existentes se conservan. Las credenciales del seed corresponden
a datos sintéticos. La demo usa HTTP y publica sus puertos solo en loopback.
PostgreSQL usa el volumen separado postgres_demo_data y n8n usa
n8n_demo_data con SQLite; los volúmenes anteriores permanecen intactos.

El triaje usa DEMO_MODE=true: produce una evaluación determinista basada en
reglas y se identifica como proveedor mock, modelo demo-heuristic-v1.
No es una explicación generada por un LLM. No requiere Ollama, modelo ni API
keys. Las acciones sugeridas no ejecutan bloqueos reales. Se deshabilitan las
notificaciones externas y la inteligencia de amenazas externa en esta demo.
Los workflows n8n se encuentran montados en /workflows y no se activan
automáticamente. La consola n8n puede requerir su configuración inicial.

## Diferencias respecto de Prompt.docx

| Área | Situación del proyecto disponible |
| --- | --- |
| Login, roles, usuarios, dashboard, alertas, incidentes, auditoría y reportes | Hay módulos implementados; consultar las verificaciones del despliegue. |
| Perfil individual de accesos, access_logs y anomalías UBA | No están implementados como módulos del Caso05. |
| Baseline scikit-learn y reentrenamiento | No implementados. |
| Gestión completa de IoCs con TTL, STIX/TAXII y relaciones | Hay indicadores asociados a triajes; falta el módulo completo solicitado. |
| Scheduler interno, conectores VPN/AD/EDR y cola de errores | No implementados con el alcance del documento. |
| Almacenamiento MinIO/S3 y URLs firmadas | El proyecto almacena reportes en un volumen local. |
| Argon2 | El proyecto existente usa bcrypt. |
| LangFlow, OpenTelemetry y todos los entregables de CI/CD | No se acredita su implementación completa. |
| Producción | Requiere completar los módulos faltantes, validar adaptadores, secretos, TLS y pruebas; cambiar variables no completa esas funciones. |

Para probar la integración Ollama existente se debe desactivar DEMO_MODE en
el servicio de triaje, habilitar los servicios del perfil llm y descargar un
modelo compatible. Esto solo habilita el triaje LLM del proyecto; no añade
los módulos faltantes del Caso05.

## Operación

```powershell
docker compose -f docker-compose.yml -f docker-compose.demo.yml ps
docker compose -f docker-compose.yml -f docker-compose.demo.yml logs --tail 100
docker compose -f docker-compose.yml -f docker-compose.demo.yml stop
```

No usar down -v si se desean conservar los datos.

## Verificaciones realizadas

Se construyeron las imágenes y el frontend superó TypeScript y Vite. Las tres
pruebas de arranque validaron importación de rutas, relaciones ORM e
identificadores UUID compatibles con PostgreSQL. La prueba funcional
scripts/smoke-demo.ps1 verificó readiness, login, perfil, dashboard, listados de
alertas, incidentes, usuarios y roles, bitácora, estadísticas de triaje,
rotación de refresh token, triaje persistido, reportes PDF/DOCX/XLSX,
denegación RBAC con HTTP 403 para visor y cierre de sesión.

Se comprobó visualmente el acceso al dashboard con la cuenta sintética admin.
Estas pruebas cubren el despliegue y los recorridos indicados; no constituyen
una validación exhaustiva de cada CRUD o de los workflows n8n.
