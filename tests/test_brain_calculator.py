"""
Tests for modules/brain/calculator.py — pure/sync functions only.
Async functions that require MongoDB are not tested here.
Covers: _pct_to_factor, _extract_pct, _extract_tope, _regla_aplica,
        _hydrate_reglas, PrecioCadena and ComparativaEAN construction.
"""

import unittest
from datetime import datetime, timezone

from modules.brain.calculator import (
    ComparativaEAN,
    PrecioCadena,
    _hydrate_reglas,
    _regla_aplica,
)
from modules.promo_engine.models import DiaSemana, ReglaDescuento, TipoPromo
from modules.promo_engine.parser import _extract_pct, _extract_tope, _pct_to_factor


class TestPctHelpers(unittest.TestCase):
    def test_pct_to_factor_20(self):
        self.assertAlmostEqual(_pct_to_factor(20.0), 0.8, places=5)

    def test_pct_to_factor_100(self):
        self.assertAlmostEqual(_pct_to_factor(100.0), 0.0, places=5)

    def test_pct_to_factor_0(self):
        self.assertAlmostEqual(_pct_to_factor(0.0), 1.0, places=5)

    def test_pct_to_factor_33(self):
        self.assertAlmostEqual(_pct_to_factor(33.0), round(1 - 33 / 100, 6), places=5)

    def test_extract_pct_entero(self):
        self.assertEqual(_extract_pct("20% de descuento"), 20.0)

    def test_extract_pct_decimal_punto(self):
        self.assertEqual(_extract_pct("12.5%"), 12.5)

    def test_extract_pct_decimal_coma(self):
        self.assertEqual(_extract_pct("12,5%"), 12.5)

    def test_extract_pct_sin_pct_retorna_none(self):
        self.assertIsNone(_extract_pct("sin descuento"))

    def test_extract_pct_toma_primer_match(self):
        # Con dos porcentajes, toma el primero
        self.assertEqual(_extract_pct("10% y luego 20%"), 10.0)


class TestExtractTope(unittest.TestCase):
    def test_tope_con_punto_de_miles(self):
        self.assertEqual(_extract_tope("tope $5.000"), 5000.0)

    def test_tope_sin_signo_pesos(self):
        self.assertEqual(_extract_tope("tope 1000"), 1000.0)

    def test_tope_con_decimales(self):
        self.assertEqual(_extract_tope("tope $2.500,50"), 2500.5)

    def test_sin_tope_retorna_none(self):
        self.assertIsNone(_extract_tope("20% de descuento"))


class TestReglaAplica(unittest.TestCase):
    def _make_regla(self, tipo, banco=None, tarjeta=None, programa=None) -> ReglaDescuento:
        return ReglaDescuento(
            cadena_id="COTO",
            tipo=tipo,
            texto_original="test",
            banco=banco,
            tarjeta=tarjeta,
            programa_fidelidad=programa,
        )

    def test_directa_siempre_aplica(self):
        regla = self._make_regla(TipoPromo.DIRECTA)
        self.assertTrue(_regla_aplica(regla, tarjetas=None, programas=None))
        self.assertTrue(_regla_aplica(regla, tarjetas=["Visa"], programas=[]))

    def test_bancaria_sin_filtro_aplica(self):
        regla = self._make_regla(TipoPromo.BANCARIA, banco="Banco Nación")
        self.assertTrue(_regla_aplica(regla, tarjetas=None, programas=None))

    def test_bancaria_con_banco_correcto(self):
        regla = self._make_regla(TipoPromo.BANCARIA, banco="Banco Nación")
        self.assertTrue(_regla_aplica(regla, tarjetas=["Banco Nación"], programas=None))

    def test_bancaria_con_banco_incorrecto(self):
        regla = self._make_regla(TipoPromo.BANCARIA, banco="Banco Nación")
        self.assertFalse(_regla_aplica(regla, tarjetas=["Visa"], programas=None))

    def test_bancaria_match_parcial_en_banco(self):
        # "nación" en "Banco Nación" → match
        regla = self._make_regla(TipoPromo.BANCARIA, banco="Banco Nación")
        self.assertTrue(_regla_aplica(regla, tarjetas=["nación"], programas=None))

    def test_bancaria_tarjeta_correcta(self):
        regla = self._make_regla(TipoPromo.BANCARIA, tarjeta="Visa")
        self.assertTrue(_regla_aplica(regla, tarjetas=["Visa"], programas=None))

    def test_fidelidad_sin_filtro_aplica(self):
        regla = self._make_regla(TipoPromo.FIDELIDAD, programa="Comunidad Coto")
        self.assertTrue(_regla_aplica(regla, tarjetas=None, programas=None))

    def test_fidelidad_con_programa_correcto(self):
        regla = self._make_regla(TipoPromo.FIDELIDAD, programa="Comunidad Coto")
        self.assertTrue(_regla_aplica(regla, tarjetas=None, programas=["Comunidad Coto"]))

    def test_fidelidad_con_programa_incorrecto(self):
        regla = self._make_regla(TipoPromo.FIDELIDAD, programa="Comunidad Coto")
        self.assertFalse(_regla_aplica(regla, tarjetas=None, programas=["Mi Carrefour"]))

    def test_fidelidad_case_insensitive(self):
        regla = self._make_regla(TipoPromo.FIDELIDAD, programa="Comunidad Coto")
        self.assertTrue(_regla_aplica(regla, tarjetas=None, programas=["comunidad coto"]))


class TestHydrateReglas(unittest.TestCase):
    def _raw(self, **kwargs) -> dict:
        base = {
            "cadena_id": "COTO",
            "tipo": "directa",
            "texto_original": "test",
        }
        base.update(kwargs)
        return base

    def test_hidrata_regla_directa(self):
        reglas = _hydrate_reglas([self._raw(descuento_pct=20.0)])
        self.assertEqual(len(reglas), 1)
        self.assertEqual(reglas[0].tipo, TipoPromo.DIRECTA)
        self.assertEqual(reglas[0].descuento_pct, 20.0)

    def test_hidrata_regla_bancaria_con_todos_los_campos(self):
        raw = self._raw(
            tipo="bancaria",
            banco="Banco Nación",
            tarjeta="Visa",
            medio_pago="debito",
            dia_semana="lunes",
            tope_reintegro=5000.0,
            descuento_pct=25.0,
        )
        reglas = _hydrate_reglas([raw])
        self.assertEqual(len(reglas), 1)
        r = reglas[0]
        self.assertEqual(r.tipo, TipoPromo.BANCARIA)
        self.assertEqual(r.banco, "Banco Nación")
        self.assertEqual(r.tarjeta, "Visa")
        self.assertEqual(r.medio_pago, "debito")
        self.assertEqual(r.dia_semana, DiaSemana.LUNES)
        self.assertEqual(r.tope_reintegro, 5000.0)

    def test_ignora_regla_con_tipo_invalido(self):
        raw = self._raw(tipo="tipo_inexistente")
        reglas = _hydrate_reglas([raw])
        self.assertEqual(len(reglas), 0)

    def test_lista_vacia(self):
        self.assertEqual(_hydrate_reglas([]), [])

    def test_multiples_reglas(self):
        raws = [
            self._raw(tipo="directa"),
            self._raw(tipo="bancaria", banco="Visa"),
            self._raw(tipo="fidelidad", programa_fidelidad="Comunidad Coto"),
        ]
        reglas = _hydrate_reglas(raws)
        self.assertEqual(len(reglas), 3)

    def test_regla_con_ean_none(self):
        raw = self._raw(ean=None)
        reglas = _hydrate_reglas([raw])
        self.assertIsNone(reglas[0].ean)

    def test_regla_con_ean(self):
        raw = self._raw(ean="7790895007217")
        reglas = _hydrate_reglas([raw])
        self.assertEqual(reglas[0].ean, "7790895007217")


class TestDataclasses(unittest.TestCase):
    def test_precio_cadena_construccion(self):
        pc = PrecioCadena(
            cadena_id="COTO",
            precio_lista=1000.0,
            precio_oferta=900.0,
            precio_neto=800.0,
            precio_por_unidad=None,
            unidad_medida=None,
            ahorro_pct=20.0,
            reglas_aplicadas=["directa: 20%"],
        )
        self.assertEqual(pc.cadena_id, "COTO")
        self.assertEqual(pc.ahorro_pct, 20.0)

    def test_comparativa_ean_construccion(self):
        pc = PrecioCadena(
            cadena_id="COTO",
            precio_lista=1000.0,
            precio_oferta=None,
            precio_neto=1000.0,
            precio_por_unidad=None,
            unidad_medida=None,
            ahorro_pct=0.0,
            reglas_aplicadas=[],
        )
        comp = ComparativaEAN(
            ean="7790895007217",
            nombre="Producto Test",
            cadenas=[pc],
            mejor_cadena="COTO",
            mejor_precio_neto=1000.0,
            capturado_en=datetime.now(tz=timezone.utc),
        )
        self.assertEqual(comp.ean, "7790895007217")
        self.assertEqual(len(comp.cadenas), 1)


if __name__ == "__main__":
    unittest.main()
