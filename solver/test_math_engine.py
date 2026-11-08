import unittest

from math_engine import EngineInputError, compute


class MathEngineTests(unittest.TestCase):
    def test_simplify_algebra(self):
        result = compute({"problem": "soddalashtiring: 2*x + 3*x"})
        self.assertEqual(result["result"], "5*x")

    def test_raw_algebra_expression(self):
        result = compute({"problem": "2x + 3x"})
        self.assertEqual(result["result"], "5*x")

    def test_factorization(self):
        result = compute({"problem": "factor x^2 - 1"})
        self.assertEqual(result["result"], "(x - 1)*(x + 1)")

    def test_quadratic_equation(self):
        result = compute({"problem": "Solve 2*x^2 - 5*x - 3 = 0"})
        self.assertEqual({variants[0] for variants in result["canonical"]}, {"x=-1/2", "x=3"})

    def test_derivative(self):
        result = compute({"problem": "derivative of x^3 + 2*x"})
        self.assertEqual(result["result"], "3*x**2 + 2")
        self.assertNotIn("\x0c", " ".join(result["steps"]))
        self.assertIn(r"\frac", " ".join(result["steps"]))

    def test_integral(self):
        result = compute({"problem": "integral of x^2 dx"})
        self.assertEqual(result["result"], "x**3/3")

    def test_definite_integral(self):
        result = compute({"problem": "integral of x^2 from 0 to 2"})
        self.assertEqual(result["result"], "8/3")

    def test_uzbek_derivative(self):
        result = compute({"problem": "x^3 + 2*x ning hosilasini toping"})
        self.assertEqual(result["result"], "3*x**2 + 2")

    def test_derivative_respects_requested_variable(self):
        result = compute({"problem": "Find derivative of x*y with respect to y"})
        self.assertEqual(result["result"], "x")

    def test_integral_respects_differential(self):
        result = compute({"problem": "integral of x*y dy"})
        self.assertEqual(result["result"], "x*y**2/2")

    def test_equation_respects_requested_variable(self):
        result = compute({"problem": "Solve for y: x + y = 3"})
        self.assertEqual(result["result"], "[y=3 - x]")

    def test_limit(self):
        result = compute({"problem": "limit of (x^2 - 1)/(x - 1) as x -> 1"})
        self.assertEqual(result["result"], "2")

    def test_boolean_vector_identifies_essential_and_dummy_arguments(self):
        result = compute({"problem": "Determine muhim va soxta argumentlar: f(x) = (10101010)"})
        self.assertEqual(result["domain"], "discrete")
        self.assertEqual(result["operation"], "boolean_vector")
        self.assertIn("muhim: x_3", result["result"])
        self.assertIn("soxta/fiktiv: x_1, x_2", result["result"])
        self.assertIn("~x3", result["result"])

    def test_boolean_vector_analyzes_all_subproblems(self):
        result = compute({"problem": "Boolean argument test: 1. f(x̃^3) = (10101010) 2. f(x̃^3) = (10011001)"})
        self.assertEqual(result["result"].count("Vektor "), 2)
        self.assertIn("muhim: x_3", result["result"])
        self.assertIn("muhim: x_2, x_3", result["result"])
        self.assertIn("soxta/fiktiv: x_1", result["result"])
        self.assertEqual(len(result["steps"]), 6)

    def test_boolean_vector_supports_two_and_four_variable_lengths(self):
        two_variables = compute({"problem": "Find Boolean DNF for f(x) = (1001)"})
        four_variables = compute({"problem": "Find Boolean KNF for f(x) = (0110100110010110)"})
        self.assertIn("2 o‘zgaruvchi", two_variables["result"])
        self.assertIn("4 o‘zgaruvchi", four_variables["result"])

    def test_matrix_determinant(self):
        result = compute({"problem": "Find determinant [[1, 2], [3, 4]]"})
        self.assertEqual(result["result"], "-2")

    def test_matrix_transpose(self):
        result = compute({"problem": "transpose matrix [[1, 2], [3, 4]]"})
        self.assertEqual(result["result"], "Matrix([\n[1, 3],\n[2, 4]])")

    def test_matrix_multiplication(self):
        result = compute({"problem": "multiply matrices [[1, 2], [3, 4]] and [[2, 0], [1, 2]]"})
        self.assertEqual("".join(result["result"].split()), "Matrix([[4,4],[10,8]])")

    def test_matrix_addition(self):
        result = compute({"problem": "add matrices [[1, 2], [3, 4]] and [[2, 0], [1, 2]]"})
        self.assertEqual("".join(result["result"].split()), "Matrix([[3,2],[4,6]])")

    def test_rejects_python_execution(self):
        with self.assertRaises(EngineInputError):
            compute({"problem": "simplify __import__('os').system('whoami')"})

    def test_rejects_non_square_determinant(self):
        with self.assertRaises(EngineInputError):
            compute({"problem": "determinant [[1, 2, 3], [4, 5, 6]]"})


if __name__ == "__main__":
    unittest.main()
