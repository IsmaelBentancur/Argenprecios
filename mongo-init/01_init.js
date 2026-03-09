// Inicialización de colecciones y datos semilla para Argenprecios
db = db.getSiblingDB('argenprecios');

// Cadenas activas (comercios_config)
db.comercios_config.insertMany([
  {
    cadena_id: "COTO",
    nombre: "Coto CICSA",
    url_base: "https://www.cotodigital.com.ar",
    activo: true,
    adaptador: "coto",
    prioridad: 1,
    creado_en: new Date()
  },
  {
    cadena_id: 'JUMBO',
    nombre: 'Jumbo',
    url_base: 'https://www.jumbo.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 3,
    creado_en: new Date()
  },
  {
    cadena_id: 'DISCO',
    nombre: 'Disco',
    url_base: 'https://www.disco.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 4,
    creado_en: new Date()
  },
  {
    cadena_id: 'VEA',
    nombre: 'Vea',
    url_base: 'https://www.vea.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 5,
    creado_en: new Date()
  },
  {
    cadena_id: 'DIA',
    nombre: 'Dia',
    url_base: 'https://diaonline.supermercadosdia.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 6,
    creado_en: new Date()
  },
  {
    cadena_id: 'CHANGOMAS',
    nombre: 'ChangoMas',
    url_base: 'https://www.masonline.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 7,
    creado_en: new Date()
  },
  {
    cadena_id: 'FARMACITY',
    nombre: 'Farmacity',
    url_base: 'https://www.farmacity.com',
    activo: true,
    adaptador: 'vtex',
    prioridad: 8,
    creado_en: new Date()
  },
  {
    cadena_id: 'JOSIMAR',
    nombre: 'Josimar',
    url_base: 'https://www.josimar.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 9,
    creado_en: new Date()
  },
  {
    cadena_id: 'LIBERTAD',
    nombre: 'Libertad',
    url_base: 'https://www.hiperlibertad.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 10,
    creado_en: new Date()
  },
  {
    cadena_id: 'TOLEDO',
    nombre: 'Toledo',
    url_base: 'https://www.toledodigital.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 11,
    creado_en: new Date()
  },
  {
    cadena_id: 'ELNENE',
    nombre: 'El Nene',
    url_base: 'https://www.grupoelnene.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 12,
    creado_en: new Date()
  },
  {
    cadena_id: 'CORDIEZ',
    nombre: 'Cordiez',
    url_base: 'https://www.cordiez.com.ar',
    activo: true,
    adaptador: 'vtex',
    prioridad: 13,
    creado_en: new Date()
  }
]);

// índice único en reglas_descuento para evitar duplicados
db.reglas_descuento.createIndex(
  { cadena_id: 1, tipo: 1, banco: 1, tarjeta: 1, programa_fidelidad: 1, dia_semana: 1, ean: 1 },
  { name: "idx_regla_unica" }
);

print("âœ” comercios_config inicializado con COTO y cadenas VTEX ");
print("âœ” índice reglas_descuento creado");






