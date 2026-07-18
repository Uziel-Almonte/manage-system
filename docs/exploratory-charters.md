# Exploratory Testing — Day 34

## Charter 1 — Edge cases de SKU al crear/editar productos
**Misión:** Explorar el comportamiento del sistema ante variaciones inusuales de SKU
**Área:** Endpoint/formulario de creación y edición de productos
**Tiempo:** 30 min

Ideas a probar:
- SKU con mayúsculas vs minúsculas ("ABC-123" vs "abc-123") — ¿el sistema los trata como duplicados o no?
- SKU con espacios al inicio/final (" ABC-123 ")
- SKU vacío o compuesto solo de espacios
- SKU en el límite de longitud (50 caracteres) y por encima
- Copiar y pegar un SKU ya existente en el formulario de edición
- Caracteres especiales, tildes, unicode o emojis en el SKU
- Cambiar el SKU de un producto existente al de otro producto ya creado

## Charter 2 — Permisos entre roles (worker vs manager)
**Misión:** Explorar si alice_worker puede acceder a funciones reservadas a kratos_boss
**Área:** Rutas protegidas por rol vía Keycloak
**Tiempo:** 30 min

Ideas a probar:
- Intentar eliminar o editar productos autenticado como worker
- Acceder directamente por URL a rutas de administración sin pasar por el menú/UI
- Reusar/manipular el token JWT de un rol en una sesión con el otro rol
- Ver qué pasa si el token expira a mitad de una operación (crear producto, editar stock)

## Charter 3 — Integridad de datos y stock tras operaciones encadenadas
**Misión:** Explorar inconsistencias entre productos, movimientos de stock y auditoría
**Área:** products / stock_movements / audit_logs
**Tiempo:** 30 min

Ideas a probar:
- Crear un producto, registrar movimientos de stock, y luego eliminar el producto — ¿qué pasa con los stock_movements asociados? (recuerda que tienes cascade delete en la FK)
- Registrar un movimiento de stock que deje qty en negativo
- Verificar si cada acción relevante queda reflejada en audit_logs
- Editar min_stock y qty simultáneamente desde dos pestañas/sesiones distintas