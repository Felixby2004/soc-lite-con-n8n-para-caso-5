# Integración de datos reales de Loghub OpenSSH

La aplicación incorpora la muestra oficial OpenSSH_2k.log de Loghub. Los autores
describen registros recogidos de un servidor OpenSSH real de laboratorio durante
más de 28 días. Se importa la muestra de 2000 líneas publicada por ellos, no el
corpus completo de 655146 líneas. No se generan ni simulan eventos para esta fuente.

Fuente: https://github.com/logpai/loghub/tree/master/OpenSSH

Versión fijada: 374038faa4ca122dd7ca0730372c0b78f76f8597

SHA-256: 1e4912727fa88245113d41b16a0cd25ceadba7f931e1c406542885b91254264f

El archivo original, licencia, descripción y manifiesto están en
backend/datasets/loghub-openssh. El manifiesto conserva la URL exacta de descarga,
versión, fecha de obtención, tamaño, conteo y referencia bibliográfica.
La licencia permite investigación y uso académico con atribución; no se afirma
una autorización comercial general.

## Uso

Abrir http://localhost:8080/datasets e iniciar sesión. El menú Datos reales
presenta exclusivamente registros de esta fuente. Un administrador puede usar
Importar dataset; los usuarios autorizados pueden consultar, revisar cada log y
exportar el conjunto con su procedencia en JSON. La exportación requiere
reports:export y la importación settings:write. La consulta requiere alerts:read.

Los datos se guardan en PostgreSQL, tabla soclite.alerts, con source_name
Loghub OpenSSH · registros reales y raw_payload.data_origin=public_dataset.
El registro de integración y su manifiesto se conservan en soclite.integrations.
Los módulos existentes siguen funcionando. Las métricas del dashboard operativo
y sus reportes generales incluyen todas las fuentes; el panel Datos reales y
su exportación JSON excluyen la demo. El listado Alertas permite filtrar por
procedencia; en esa vista se bloquea la exportación general para evitar exportar
por error datos de otras fuentes.

## Fidelidad y límites

Cada línea se guarda intacta en full_log y raw_payload.original_line, con número
de línea, hash del archivo, commit y hora original. El importador verifica el
SHA-256 y la cantidad de líneas antes de escribir, valida las 2000 líneas y usa
una clave determinista archivo-línea con ON CONFLICT para impedir duplicados.
Un bloqueo transaccional evita carreras entre importaciones simultáneas.

El formato original contiene mes, día y hora, pero no año ni zona horaria.
No se inventan esos campos: occurred_at es el instante de importación y la
hora original se preserva por separado. Las tendencias del dashboard operativo
representan la carga de los registros históricos, no la actividad actual de
ese servidor. El campo SLA generado por la infraestructura es de la aplicación,
no un resultado histórico medido en Loghub.

El parser identifica fallos, usuarios inválidos, accesos aceptados, cierres,
advertencias de DNS y otros mensajes. Las severidades son reglas locales de
priorización; no etiquetas del dataset. No se inventan IP de destino, coordenadas,
usuarios corporativos, ground truth ni veredictos. La muestra no trae etiquetas
verificadas de ataques o cuentas comprometidas y no demuestra recall, precisión,
F1 ni reducción real de falsos positivos. Tampoco garantiza representatividad.

El motor de triaje del despliegue sigue en DEMO_MODE=true y usa una heurística
simulada. Cargar registros reales no transforma esa evaluación en inferencia
LLM ni en validación científica. La importación no activa automáticamente
triaje, notificaciones, consultas de IP a proveedores ni acciones de bloqueo.

## Reproducción y pruebas

```powershell
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build --wait
.\scripts\smoke-public-dataset.ps1
```

El script autentica, importa, repite la importación, comprueba conteos,
procedencia, evidencia original, ausencia de veredictos inventados, exportación
JSON y denegación de importación para el rol visor. Usa las cuentas locales
de demostración; no necesita credenciales externas.

Pruebas unitarias: backend/tests/test_public_dataset.py valida el archivo
oficial completo, el parser, rechazo de datos modificados y rechazo de líneas
mal formadas. La importación real se verifica contra la base desplegada.

Referencia: Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu y Michael R. Lyu.
Loghub A Large Collection of System Log Datasets for AI-driven Log Analytics.
IEEE International Symposium on Software Reliability Engineering, 2023.
https://arxiv.org/abs/2008.06448

## Resultado verificado de la carga inicial

Se importaron 2000 filas nuevas; la repetición añadió cero y reconoció las
2000 existentes. Se observaron 30 IP distintas y 64 nombres de usuario.
El parser clasificó 1025 registros de fallo de autenticación, 624 de otros
tipos, 230 de usuario inválido, 85 de advertencia DNS, 35 de conexión cerrada
y uno de acceso aceptado. Una sesión puede producir varios mensajes; no son
conteos de intentos únicos. Los cinco registros previos de otras fuentes
permanecen excluidos del panel y de la exportación del dataset.

Pasaron siete pruebas unitarias/de arranque, la construcción TypeScript/Vite y
la prueba de integración smoke-public-dataset.ps1 sobre la base desplegada.
