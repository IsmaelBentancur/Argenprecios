"""
Tests for POST /api/feedback
Covers: FeedbackInput model validation, endpoint behaviour (mocked DB).
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from modules.control import FeedbackInput, FEEDBACK_TIPOS

# Shared mock DB used by all endpoint tests
_mock_db = MagicMock()
_mock_db.feedback.insert_one = AsyncMock(return_value=MagicMock(inserted_id="fake_id"))
_patcher = patch("modules.control.get_db", return_value=_mock_db)


# ---------------------------------------------------------------------------
# Model validation tests (no I/O)
# ---------------------------------------------------------------------------

class TestFeedbackInput(unittest.TestCase):
    def test_valido_sugerencia(self):
        f = FeedbackInput(mensaje="Agregar filtro por precio", tipo="sugerencia")
        self.assertEqual(f.tipo, "sugerencia")
        self.assertEqual(f.mensaje, "Agregar filtro por precio")

    def test_valido_bug(self):
        f = FeedbackInput(mensaje="El botón no funciona", tipo="bug")
        self.assertEqual(f.tipo, "bug")

    def test_valido_otro(self):
        f = FeedbackInput(mensaje="Consulta general", tipo="otro")
        self.assertEqual(f.tipo, "otro")

    def test_tipo_default_es_otro(self):
        f = FeedbackInput(mensaje="Hola")
        self.assertEqual(f.tipo, "otro")

    def test_tipo_invalido_lanza_error(self):
        with self.assertRaises(ValidationError):
            FeedbackInput(mensaje="Test", tipo="queja")

    def test_mensaje_vacio_lanza_error(self):
        with self.assertRaises(ValidationError):
            FeedbackInput(mensaje="", tipo="otro")

    def test_mensaje_demasiado_largo_lanza_error(self):
        with self.assertRaises(ValidationError):
            FeedbackInput(mensaje="x" * 1001, tipo="otro")

    def test_mensaje_exactamente_1000_caracteres_valido(self):
        f = FeedbackInput(mensaje="x" * 1000, tipo="otro")
        self.assertEqual(len(f.mensaje), 1000)

    def test_todos_los_tipos_validos(self):
        for tipo in FEEDBACK_TIPOS:
            f = FeedbackInput(mensaje="test", tipo=tipo)
            self.assertEqual(f.tipo, tipo)


# ---------------------------------------------------------------------------
# Endpoint tests (mocked DB)
# ---------------------------------------------------------------------------

class TestFeedbackEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _patcher.start()
        from main import app
        cls.client = TestClient(app, raise_server_exceptions=True)
        cls.mock_db = _mock_db

    @classmethod
    def tearDownClass(cls):
        _patcher.stop()

    def setUp(self):
        # Reset call history between tests
        self.mock_db.feedback.insert_one.reset_mock()

    def test_post_feedback_retorna_ok(self):
        res = self.client.post("/api/feedback", json={"mensaje": "Muy buena app", "tipo": "sugerencia"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_post_feedback_sin_tipo_usa_default(self):
        res = self.client.post("/api/feedback", json={"mensaje": "Comentario sin tipo"})
        self.assertEqual(res.status_code, 200)

    def test_post_feedback_mensaje_vacio_retorna_422(self):
        res = self.client.post("/api/feedback", json={"mensaje": "", "tipo": "otro"})
        self.assertEqual(res.status_code, 422)

    def test_post_feedback_tipo_invalido_retorna_422(self):
        res = self.client.post("/api/feedback", json={"mensaje": "Test", "tipo": "invalido"})
        self.assertEqual(res.status_code, 422)

    def test_post_feedback_sin_mensaje_retorna_422(self):
        res = self.client.post("/api/feedback", json={"tipo": "bug"})
        self.assertEqual(res.status_code, 422)

    def test_post_feedback_mensaje_largo_retorna_422(self):
        res = self.client.post("/api/feedback", json={"mensaje": "x" * 1001, "tipo": "otro"})
        self.assertEqual(res.status_code, 422)

    def test_post_feedback_llama_insert_one(self):
        self.client.post("/api/feedback", json={"mensaje": "Probando", "tipo": "bug"})
        self.mock_db.feedback.insert_one.assert_called_once()
        doc = self.mock_db.feedback.insert_one.call_args[0][0]
        self.assertEqual(doc["mensaje"], "Probando")
        self.assertEqual(doc["tipo"], "bug")
        self.assertIn("capturado_en", doc)

    def test_post_feedback_todos_los_tipos_validos(self):
        for tipo in sorted(FEEDBACK_TIPOS):
            res = self.client.post("/api/feedback", json={"mensaje": "Test", "tipo": tipo})
            self.assertEqual(res.status_code, 200, f"Falló con tipo={tipo}")


if __name__ == "__main__":
    unittest.main()
