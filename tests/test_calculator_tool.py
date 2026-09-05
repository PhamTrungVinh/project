from tools.calculator_tool import calculator_tool


def test_calculator_basic_arithmetic():
    assert calculator_tool.invoke({"expression": "2 + 2"}) == "Result: 4"
    assert calculator_tool.invoke({"expression": "100 / 4"}) == "Result: 25.0"
    assert calculator_tool.invoke({"expression": "3 * (4 + 5)"}) == "Result: 27"


def test_calculator_math_operations():
    assert calculator_tool.invoke({"expression": "2 ** 3"}) == "Result: 8"
    assert calculator_tool.invoke({"expression": "10 - 4.5"}) == "Result: 5.5"


def test_calculator_invalid_expression():
    result = calculator_tool.invoke({"expression": "invalid_syntax++"})
    assert result.startswith("Error:")
