from compliance_agents.ocr_eval import numbers, page_metrics, spearman


def test_numbers_keep_formatting_that_matters_in_contracts():
    assert numbers("R$ 47.760,00 em 12 meses, 5% até 31/07/2027.") == {"47.760,00": 1, "12": 1, "5%": 1, "31/07/2027": 1}


def test_page_metrics_perfect_and_missing_number():
    m = page_metrics("Garantia de 5% do valor.", "garantia de 5% do valor.")
    assert m["cer"] == 0 and m["word_recall"] == 1 and m["number_recall"] == 1
    m = page_metrics("Garantia de 5% do valor.", "Garantia de S% do valor.")
    assert m["number_recall"] == 0 and m["cer"] > 0


def test_spearman():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert spearman([1, 2], [1, 2]) is None


def test_numbers_split_across_lines_are_joined():
    assert numbers("cláusula 14.\r\n3 A contratada") == numbers("cláusula 14.3 A contratada")
