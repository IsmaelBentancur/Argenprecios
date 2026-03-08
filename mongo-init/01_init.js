// Inicialización de colecciones y datos semilla para Argenprecios
db = db.getSiblingDB('argenprecios');

// Cadenas activas (comercios_config)
db.comercios_config.insertMany([
  {
    cadena_id: "COTO",
    nombre: "Coto CICSA",
    url_base: "https://www.cotodigital3.com.ar",
    activo: true,
    adaptador: "coto",
    prioridad: 1,
    creado_en: new Date()
  },
  {
    cadena_id: "CARREFOUR",
    nombre: "Carrefour Argentina",
    url_base: "https://www.carrefour.com.ar",
    activo: true,
    adaptador: "carrefour",
    prioridad: 2,
    creado_en: new Date()
  }
]);

// Índice único en reglas_descuento para evitar duplicados
db.reglas_descuento.createIndex(
  { cadena_id: 1, tipo: 1, banco: 1, tarjeta: 1, programa_fidelidad: 1, dia_semana: 1, ean: 1 },
  { name: "idx_regla_unica" }
);

print("✔ comercios_config inicializado con COTO y CARREFOUR");
print("✔ Índice reglas_descuento creado");
