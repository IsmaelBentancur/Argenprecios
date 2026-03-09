"""
Tests for Módulo 3 — The Promo Engine
Covers: parse_promo_text, calcular_precio_neto, ReglaDescuento model
"""

import unittest
from datetime import datetime, timedelta, timezone

from modules.promo_engine.models import DiaSemana, ReglaDescuento, TipoPromo
from modules.promo_engine.parser import calcular_precio_neto, parse_promo_text


class TestParsePromoText(unittest.TestCase):
    # --- DIRECTA ---
    def test_directa_simple(self):
        regla = parse_promo_text("20% de descuento en toda la compra", "COTO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.DIRECTA)
        self.assertEqual(regla.descuento_pct, 20.0)
        self.assertAlmostEqual(regla.factor_multiplicador, 0.8, places=5)

    def test_directa_off(self):
        regla = parse_promo_text("Hasta 30% OFF en productos seleccionados", "COTO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.DIRECTA)
        self.assertEqual(regla.descuento_pct, 30.0)

    def test_directa_coma_decimal(self):
        regla = parse_promo_text("12,5% de ahorro", "DISCO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.descuento_pct, 12.5)

    # --- MULTI_UNIT ---
    def test_multi_3x2(self):
        regla = parse_promo_text("3x2 en toda la línea", "COTO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.MULTI_UNIT)
        self.assertAlmostEqual(regla.factor_multiplicador, round(2 / 3, 6), places=5)

    def test_multi_3x2_uppercase(self):
        regla = parse_promo_text("Llevá 3 pagá 2 → 3X2 especial", "JUMBO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.MULTI_UNIT)

    def test_multi_2da_unidad(self):
        regla = parse_promo_text("2da unidad al 70%", "JUMBO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.MULTI_UNIT)
        self.assertEqual(regla.descuento_pct, 70.0)
        # factor = (100 + 70) / 200 = 0.85
        self.assertAlmostEqual(regla.factor_multiplicador, 0.85, places=5)

    def test_multi_segunda_unidad(self):
        regla = parse_promo_text("Segunda unidad al 50%", "VEA")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.MULTI_UNIT)
        self.assertEqual(regla.descuento_pct, 50.0)
        # factor = (100 + 50) / 200 = 0.75
        self.assertAlmostEqual(regla.factor_multiplicador, 0.75, places=5)

    def test_multi_nxm_generic(self):
        regla = parse_promo_text("4x3 en chocolates", "DIA")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.MULTI_UNIT)
        self.assertAlmostEqual(regla.factor_multiplicador, round(3 / 4, 6), places=5)

    def test_multi_nxm_ignores_invalid(self):
        # n=2, m=3 → m >= n, debe ignorarse como multi y caer en otra categoría
        regla = parse_promo_text("2x3 no es una promo válida", "COTO")
        # Should not create MULTI_UNIT since m > n
        if regla is not None:
            self.assertNotEqual(regla.tipo, TipoPromo.MULTI_UNIT)

    # --- BANCARIA ---
    def test_bancaria_con_banco(self):
        regla = parse_promo_text("20% de descuento con Banco Nación los lunes", "COTO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.BANCARIA)
        self.assertEqual(regla.banco, "Banco Nación")
        self.assertEqual(regla.descuento_pct, 20.0)
        self.assertEqual(regla.dia_semana, DiaSemana.LUNES)

    def test_bancaria_con_tarjeta(self):
        regla = parse_promo_text("25% de ahorro con Visa Débito", "COTO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.BANCARIA)
        self.assertEqual(regla.tarjeta, "Visa")
        self.assertEqual(regla.medio_pago, "debito")

    def test_bancaria_tope(self):
        regla = parse_promo_text("25% de ahorro con Visa Débito, tope $5.000", "DISCO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tope_reintegro, 5000.0)

    def test_bancaria_qr(self):
        regla = parse_promo_text("Hasta 30% OFF pagando con QR Mercado Pago", "JUMBO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.BANCARIA)
        self.assertEqual(regla.banco, "Mercado Pago")
        self.assertEqual(regla.medio_pago, "qr")

    def test_bancaria_dia_sabado(self):
        regla = parse_promo_text("15% con Mastercard los sábados", "VEA")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.dia_semana, DiaSemana.SABADO)

    def test_bancaria_dia_miercoles_sin_tilde(self):
        regla = parse_promo_text("10% descuento los miercoles con Cabal", "COTO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.dia_semana, DiaSemana.MIERCOLES)

    # --- FIDELIDAD ---
    def test_fidelidad_comunidad_coto(self):
        regla = parse_promo_text("Precio exclusivo Comunidad Coto 15%", "COTO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.tipo, TipoPromo.FIDELIDAD)
        self.assertEqual(regla.programa_fidelidad, "Comunidad Coto")
        self.assertEqual(regla.descuento_pct, 15.0)

    def test_fidelidad_club_la_nacion_sin_tilde(self):
        regla = parse_promo_text("Beneficio club la nacion 20%", "COTO")
        self.assertIsNotNone(regla)
        self.assertEqual(regla.programa_fidelidad, "Club La Nación")

    # --- NULL CASES ---
    def test_no_promo_retorna_none(self):
        self.assertIsNone(parse_promo_text("Producto sin promoción", "COTO"))

    def test_texto_vacio_retorna_none(self):
        self.assertIsNone(parse_promo_text("", "COTO"))

    # --- METADATA ---
    def test_cadena_id_preservada(self):
        regla = parse_promo_text("20% OFF", "JUMBO")
        self.assertEqual(regla.cadena_id, "JUMBO")

    def test_ean_preservado(self):
        regla = parse_promo_text("20% OFF", "COTO", ean="7790895007217")
        self.assertEqual(regla.ean, "7790895007217")

    def test_categoria_preservada(self):
        regla = parse_promo_text("20% OFF", "COTO", categoria="Bebidas")
        self.assertEqual(regla.categoria, "Bebidas")

    def test_texto_original_preservado(self):
        texto = "25% de ahorro con Visa Débito, tope $5.000"
        regla = parse_promo_text(texto, "COTO")
        self.assertEqual(regla.texto_original, texto)


class TestReglaDescuentoModel(unittest.TestCase):
    def _make_regla(self, **kwargs) -> ReglaDescuento:
        defaults = {
            "cadena_id": "COTO",
            "tipo": TipoPromo.DIRECTA,
            "texto_original": "test",
        }
        defaults.update(kwargs)
        return ReglaDescuento(**defaults)

    # --- calcular_precio_final ---
    def test_calcula_con_factor(self):
        regla = self._make_regla(factor_multiplicador=0.8)
        self.assertAlmostEqual(regla.calcular_precio_final(1000.0), 800.0)

    def test_calcula_con_pct(self):
        regla = self._make_regla(descuento_pct=20.0)
        self.assertAlmostEqual(regla.calcular_precio_final(1000.0), 800.0)

    def test_calcula_con_tope(self):
        regla = self._make_regla(descuento_pct=30.0, tope_reintegro=200.0)
        # 30% de 1000 = 300, pero tope=200 → precio final = 800
        self.assertAlmostEqual(regla.calcular_precio_final(1000.0), 800.0)

    def test_calcula_sin_descuento_retorna_lista(self):
        regla = self._make_regla()
        self.assertAlmostEqual(regla.calcular_precio_final(500.0), 500.0)

    def test_factor_tiene_prioridad_sobre_pct(self):
        # factor_multiplicador debe tener precedencia
        regla = self._make_regla(factor_multiplicador=0.5, descuento_pct=20.0)
        self.assertAlmostEqual(regla.calcular_precio_final(1000.0), 500.0)

    def test_resultado_redondeado_a_dos_decimales(self):
        regla = self._make_regla(descuento_pct=33.0)
        precio = regla.calcular_precio_final(100.0)
        self.assertEqual(precio, round(precio, 2))

    # --- esta_vigente ---
    def test_sin_fechas_siempre_vigente(self):
        regla = self._make_regla()
        self.assertTrue(regla.esta_vigente())

    def test_fecha_inicio_futura_no_vigente(self):
        regla = self._make_regla(
            fecha_inicio=datetime.now(tz=timezone.utc) + timedelta(days=1)
        )
        self.assertFalse(regla.esta_vigente())

    def test_fecha_fin_pasada_no_vigente(self):
        regla = self._make_regla(
            fecha_fin=datetime.now(tz=timezone.utc) - timedelta(days=1)
        )
        self.assertFalse(regla.esta_vigente())

    def test_dentro_del_rango_vigente(self):
        regla = self._make_regla(
            fecha_inicio=datetime.now(tz=timezone.utc) - timedelta(days=1),
            fecha_fin=datetime.now(tz=timezone.utc) + timedelta(days=1),
        )
        self.assertTrue(regla.esta_vigente())

    # --- to_dict ---
    def test_to_dict_contiene_claves_basicas(self):
        regla = self._make_regla(descuento_pct=15.0)
        d = regla.to_dict()
        for key in ("cadena_id", "tipo", "texto_original", "descuento_pct"):
            self.assertIn(key, d)

    def test_to_dict_tipo_es_string(self):
        regla = self._make_regla()
        d = regla.to_dict()
        self.assertIsInstance(d["tipo"], str)

    def test_to_dict_dia_semana_es_string_o_none(self):
        regla = self._make_regla(dia_semana=DiaSemana.LUNES)
        d = regla.to_dict()
        self.assertEqual(d["dia_semana"], "lunes")

        regla2 = self._make_regla()
        d2 = regla2.to_dict()
        self.assertIsNone(d2["dia_semana"])


class TestCalcularPrecioNeto(unittest.TestCase):
    def _regla(self, tipo, descuento_pct=None, factor=None, banco=None,
               tarjeta=None, programa=None, vigente=True) -> ReglaDescuento:
        fecha_fin = (
            datetime.now(tz=timezone.utc) + timedelta(days=1) if vigente
            else datetime.now(tz=timezone.utc) - timedelta(days=1)
        )
        return ReglaDescuento(
            cadena_id="COTO",
            tipo=tipo,
            texto_original="test",
            descuento_pct=descuento_pct,
            factor_multiplicador=factor,
            banco=banco,
            tarjeta=tarjeta,
            programa_fidelidad=programa,
            fecha_fin=fecha_fin,
        )

    def test_sin_reglas_retorna_precio_lista(self):
        self.assertEqual(calcular_precio_neto(1000.0, []), 1000.0)

    def test_aplica_directa(self):
        regla = self._regla(TipoPromo.DIRECTA, descuento_pct=20.0)
        self.assertAlmostEqual(calcular_precio_neto(1000.0, [regla]), 800.0)

    def test_elige_mejor_precio_entre_varias_reglas(self):
        r1 = self._regla(TipoPromo.DIRECTA, descuento_pct=10.0)
        r2 = self._regla(TipoPromo.DIRECTA, descuento_pct=25.0)
        self.assertAlmostEqual(calcular_precio_neto(1000.0, [r1, r2]), 750.0)

    def test_regla_vencida_no_aplica(self):
        regla = self._regla(TipoPromo.DIRECTA, descuento_pct=50.0, vigente=False)
        self.assertEqual(calcular_precio_neto(1000.0, [regla]), 1000.0)

    def test_bancaria_aplica_con_tarjeta_correcta(self):
        regla = self._regla(TipoPromo.BANCARIA, descuento_pct=20.0, banco="Banco Nación")
        precio = calcular_precio_neto(1000.0, [regla], tarjetas_usuario=["Banco Nación"])
        self.assertAlmostEqual(precio, 800.0)

    def test_bancaria_no_aplica_con_tarjeta_incorrecta(self):
        regla = self._regla(TipoPromo.BANCARIA, descuento_pct=20.0, banco="Banco Nación")
        precio = calcular_precio_neto(1000.0, [regla], tarjetas_usuario=["Visa"])
        self.assertEqual(precio, 1000.0)

    def test_bancaria_aplica_sin_filtro_tarjeta(self):
        # Si tarjetas_usuario=None, no filtra → aplica
        regla = self._regla(TipoPromo.BANCARIA, descuento_pct=20.0, banco="Banco Nación")
        precio = calcular_precio_neto(1000.0, [regla], tarjetas_usuario=None)
        self.assertAlmostEqual(precio, 800.0)

    def test_fidelidad_aplica_con_programa_correcto(self):
        regla = self._regla(TipoPromo.FIDELIDAD, descuento_pct=15.0, programa="Comunidad Coto")
        precio = calcular_precio_neto(1000.0, [regla], programas_usuario=["Comunidad Coto"])
        self.assertAlmostEqual(precio, 850.0)

    def test_fidelidad_no_aplica_con_programa_incorrecto(self):
        regla = self._regla(TipoPromo.FIDELIDAD, descuento_pct=15.0, programa="Comunidad Coto")
        precio = calcular_precio_neto(1000.0, [regla], programas_usuario=["Jumbo+"])
        self.assertEqual(precio, 1000.0)

    def test_fidelidad_aplica_sin_filtro_programa(self):
        regla = self._regla(TipoPromo.FIDELIDAD, descuento_pct=15.0, programa="Comunidad Coto")
        precio = calcular_precio_neto(1000.0, [regla], programas_usuario=None)
        self.assertAlmostEqual(precio, 850.0)


if __name__ == "__main__":
    unittest.main()
