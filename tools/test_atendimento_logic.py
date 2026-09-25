from __future__ import annotations

import unittest

from tools.refresh_atendimento_facts import key_text, status_type


class AtendimentoLogicTest(unittest.TestCase):
    def test_status_type_respects_operational_exclusions(self) -> None:
        self.assertEqual(status_type("Funil de Liderancas", "Qualquer", None), "lideranca")
        self.assertEqual(status_type("Vendas", "Comunicacao interna", None), "interno")
        self.assertEqual(status_type("Vendas", "Venda ganha", 142), "ganha")
        self.assertEqual(status_type("Vendas", "Venda perdida", 143), "perdida")
        self.assertEqual(status_type("Vendas", "Negociacao", 123), "andamento")

    def test_key_text_normalizes_labels_for_dimensions(self) -> None:
        self.assertEqual(key_text("Indicação / WhatsApp"), "indicacao_whatsapp")
        self.assertEqual(key_text(""), "sem_valor")


if __name__ == "__main__":
    unittest.main()
