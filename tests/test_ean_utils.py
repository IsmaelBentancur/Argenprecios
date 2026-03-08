"""
Tests for modules/harvester/ean_utils.py
Covers: validate_gtin, is_internal_coto_id, slugify
"""

import unittest

from modules.harvester.ean_utils import is_internal_coto_id, slugify, validate_gtin


class TestValidateGtin(unittest.TestCase):
    # --- GTIN-13 válidos ---
    def test_gtin13_valido(self):
        self.assertTrue(validate_gtin("7790895007217"))
        self.assertTrue(validate_gtin("7790895064661"))

    def test_gtin13_check_digit_cero(self):
        # GTIN-13 con check digit = 0 (todos ceros es el caso más simple)
        self.assertTrue(validate_gtin("0000000000000"))

    # --- GTIN-8 válidos ---
    def test_gtin8_valido(self):
        self.assertTrue(validate_gtin("12345670"))

    # --- Inválidos: check digit incorrecto ---
    def test_gtin13_check_digit_incorrecto(self):
        self.assertFalse(validate_gtin("7790895007218"))  # último dígito cambiado

    def test_gtin8_check_digit_incorrecto(self):
        self.assertFalse(validate_gtin("12345671"))

    # --- Inválidos: longitud incorrecta ---
    def test_longitud_7_invalida(self):
        self.assertFalse(validate_gtin("1234567"))

    def test_longitud_9_invalida(self):
        self.assertFalse(validate_gtin("123456789"))

    def test_longitud_12_invalida(self):
        self.assertFalse(validate_gtin("123456789012"))

    def test_longitud_14_invalida(self):
        self.assertFalse(validate_gtin("12345678901234"))

    # --- Inválidos: caracteres no numéricos ---
    def test_letras_invalido(self):
        self.assertFalse(validate_gtin("ABC1234567890"))

    def test_con_guion_invalido(self):
        self.assertFalse(validate_gtin("779-0895007217"))

    def test_con_espacio_invalido(self):
        self.assertFalse(validate_gtin("779 0895007217"))

    # --- Edge cases ---
    def test_vacio_invalido(self):
        self.assertFalse(validate_gtin(""))

    def test_none_invalido(self):
        self.assertFalse(validate_gtin(None))


class TestIsInternalCotoId(unittest.TestCase):
    def test_id_interno_8_digitos_falla_gtin(self):
        self.assertTrue(is_internal_coto_id("00566098"))

    def test_gtin13_real_no_es_interno(self):
        self.assertFalse(is_internal_coto_id("7790895007217"))

    def test_gtin8_real_no_es_interno(self):
        # GTIN-8 válido que no empieza con "00" → no es interno
        self.assertFalse(is_internal_coto_id("12345670"))

    def test_gtin8_valido_con_prefijo_00_es_interno(self):
        # Empieza con "00" → marcado como interno aunque pase la validación GTIN
        # Necesitamos un GTIN-8 válido que empiece con "00"
        # Calculamos el check digit para "0000000X"
        # body = 0,0,0,0,0,0,0 → total = 0*3+0+0*3+0+0*3+0+0 = 0 → expected = 0
        self.assertTrue(is_internal_coto_id("00000000"))

    def test_codigo_no_numerico_es_interno(self):
        self.assertTrue(is_internal_coto_id("ABCDEFGH"))

    def test_longitud_incorrecta_es_interno(self):
        self.assertTrue(is_internal_coto_id("123456"))


class TestSlugify(unittest.TestCase):
    def test_texto_simple(self):
        self.assertEqual(slugify("coca cola"), "coca-cola")

    def test_mayusculas_a_minusculas(self):
        self.assertEqual(slugify("Leche Entera"), "leche-entera")

    def test_acentos_removidos(self):
        self.assertEqual(slugify("jamón serrano"), "jamon-serrano")
        self.assertEqual(slugify("arroz con leche"), "arroz-con-leche")

    def test_caracteres_especiales_a_guion(self):
        self.assertEqual(slugify("pan & manteca"), "pan-manteca")

    def test_espacios_multiples_a_un_guion(self):
        self.assertEqual(slugify("pan   blanco"), "pan-blanco")

    def test_max_len(self):
        texto_largo = "a" * 100
        result = slugify(texto_largo, max_len=10)
        self.assertEqual(len(result), 10)

    def test_max_len_default_60(self):
        texto_largo = "palabra " * 20
        result = slugify(texto_largo)
        self.assertLessEqual(len(result), 60)

    def test_sin_guion_al_inicio_o_fin(self):
        result = slugify("  producto  ")
        self.assertFalse(result.startswith("-"))
        self.assertFalse(result.endswith("-"))

    def test_numeros_preservados(self):
        self.assertIn("7up", slugify("7UP"))


if __name__ == "__main__":
    unittest.main()
