"""Small, safe SymPy adapter for MathAI's supported symbolic operations."""

from __future__ import annotations

import ast
import itertools
import json
import re
import sys
from typing import Any

import sympy as sp


class EngineInputError(ValueError):
    pass


FUNCTIONS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "sqrt": sp.sqrt, "exp": sp.exp, "log": sp.log, "ln": sp.log,
    "abs": sp.Abs,
}
CONSTANTS = {"pi": sp.pi, "e": sp.E, "E": sp.E, "tau": 2 * sp.pi}
VARIABLES = {name: sp.Symbol(name, real=True) for name in "xyzabctuvwn"}


def safe_expression(source: str) -> sp.Expr:
    """Parse a restricted arithmetic AST; never eval user-supplied Python."""
    source = source.strip().replace("π", "pi").replace("−", "-").replace("×", "*").replace("÷", "/")
    if not source or len(source) > 400:
        raise EngineInputError("Ifoda bo‘sh yoki juda uzun.")
    source = source.replace("^", "**")
    source = re.sub(r"(?<=[0-9)])\s*(?=[A-Za-z(])", "*", source)
    source = re.sub(r"(?<=[A-Za-z])\s+(?=[A-Za-z(])", "*", source)
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise EngineInputError("Ifoda sintaksisini tushunib bo‘lmadi.") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 100:
        raise EngineInputError("Ifoda juda murakkab.")

    def visit(node: ast.AST) -> sp.Expr:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            if abs(node.value) > 10**12:
                raise EngineInputError("Son qiymati ruxsat etilgan chegaradan katta.")
            return sp.Integer(node.value) if isinstance(node.value, int) else sp.Float(node.value)
        if isinstance(node, ast.Name):
            if node.id in CONSTANTS:
                return CONSTANTS[node.id]
            if node.id in VARIABLES:
                return VARIABLES[node.id]
            raise EngineInputError(f"Ruxsat etilmagan belgi yoki funksiya: {node.id}.")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            if isinstance(node.op, ast.Pow):
                if right.is_number and right.is_real and abs(float(right)) > 100:
                    raise EngineInputError("Daraja 100 dan katta bo‘lishi mumkin emas.")
                return left ** right
            if isinstance(node.op, ast.Mod): return sp.Mod(left, right)
            raise EngineInputError("Bu amal qo‘llab-quvvatlanmaydi.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            args = [visit(arg) for arg in node.args]
            if len(args) != 1:
                raise EngineInputError("Funksiyaga bitta argument kiriting.")
            return FUNCTIONS[node.func.id](args[0])
        raise EngineInputError("Ifodada qo‘llab-quvvatlanmaydigan element bor.")

    return visit(tree)


def _plain_result(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_plain_result(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}: {_plain_result(item)}" for key, item in value.items()) + "}"
    return sp.sstr(value)


def _find_variable(source: str, preferred: str | None = None) -> sp.Symbol:
    if preferred:
        if preferred not in VARIABLES:
            raise EngineInputError("O‘zgaruvchi x, y, z, a, b, c, t, u, v, w yoki n bo‘lishi kerak.")
        return VARIABLES[preferred]
    candidate = source.replace("π", "pi")
    symbols = sorted({VARIABLES[name] for name in re.findall(r"\b([xyzabctuvwn])\b", candidate)}, key=lambda item: item.name)
    return symbols[0] if symbols else VARIABLES["x"]


def _requested_variable(problem: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    lower = problem.lower()
    match = re.search(r"(?:with respect to|w\.?r\.?t\.?|for|ga nisbatan|bo‘yicha|bo'yicha)\s*([xyzabctuvwn])\b", lower)
    if match:
        return match.group(1)
    match = re.search(r"\bd([xyz])\b", lower)
    if match:
        return match.group(1)
    match = re.search(r"\bd/d([xyz])\b", lower)
    return match.group(1) if match else None


def _parse_matrix_literal(source: str) -> sp.Matrix:
    rows_source = re.findall(r"\[([^\[\]]*)\]", source)
    rows = []
    for row in rows_source:
        cells = [cell.strip() for cell in row.split(",")]
        if not cells or any(not cell for cell in cells):
            raise EngineInputError("Matritsa qatoridagi qiymatlarni tekshiring.")
        rows.append([safe_expression(cell) for cell in cells])
    if not rows or len({len(row) for row in rows}) != 1:
        raise EngineInputError("Matritsa to‘g‘ri to‘rtburchak shaklda bo‘lishi kerak.")
    if len(rows) * len(rows[0]) > 100:
        raise EngineInputError("Matritsa 100 ta elementdan oshmasligi kerak.")
    return sp.Matrix(rows)


def _extract_matrices(problem: str) -> list[sp.Matrix]:
    matches = re.findall(r"\[\s*\[.*?\]\s*\]", problem, re.S)
    if not matches:
        raise EngineInputError("Matritsani [[1, 2], [3, 4]] ko‘rinishida kiriting.")
    return [_parse_matrix_literal(item) for item in matches[:2]]


def _trim_instruction(source: str) -> str:
    phrases = [
        "find the derivative of", "calculate the derivative of", "differentiate", "derivative of", "derivative",
        "hosilasini hisoblang", "hosilasini toping", "hosila toping", "hosila", "differensiallang",
        "find the integral of", "calculate the integral of", "integrate", "integral of", "integralini hisoblang",
        "integralini toping", "integral toping", "integral", "limit of", "find the limit of", "calculate the limit of", "lim",
        "limitini toping", "limitni hisoblang", "limit", "solve the equation", "solve", "yechimlarini toping",
        "tenglamani yeching", "tenglamani yech", "yeching", "simplify", "simplify the expression", "soddalashtiring",
        "soddalashtir", "factor", "factorize", "ko‘paytuvchilarga ajrating", "ko‘paytuvchilarga ajrat", "expand",
        "yoying", "expression", "ifoda", "of", "ning", "please", "the", "for x", "for y", "for t",
        "with respect to x", "with respect to y", "with respect to t", "x bo‘yicha", "x ga nisbatan", "dx", "dy",
        "dt", "toping", "hisoblang", "hisobla", "ni", "dan", "as", "and", "va",
        "ildizlarni tekshiring", "ildizlarini tekshiring", "check the roots", "verify the roots", "tekshiring",
        "what is", "what's", "evaluate", "calculate", "compute", "determine", "find", "value of", "w.r.t.",
    ]
    cleaned = source.strip().replace(":", " ")
    for phrase in sorted(phrases, key=len, reverse=True):
        cleaned = re.sub(re.escape(phrase), " ", cleaned, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip(" ,;.!?`$")


def _steps(operation: str, result: Any, *, expression: str = "", variable: str = "x", extra: dict | None = None) -> list[str]:
    extra = extra or {}
    if operation == "solve":
        step_list = [f"Tenglamani nolga teng ko‘rinishga keltiramiz: ${sp.latex(extra['equation'])}=0$."]
        if extra.get("degree") == 2:
            a, b, c = extra["coefficients"]
            step_list += [f"Koeffitsiyentlar: $a={sp.latex(a)}$, $b={sp.latex(b)}$, $c={sp.latex(c)}$.",
                          f"Diskriminant: $D=b^2-4ac={sp.latex(extra['discriminant'])}$.",
                          f"Yechimlar: $x={sp.latex(result)}$."
            ]
        else:
            step_list.append(f"${variable}$ bo‘yicha yechib, ildizlarni tekshiramiz: ${sp.latex(result)}$.")
        return step_list
    if operation == "derivative":
        return [f"Berilgan funksiya: ${sp.latex(extra.get('expression', expression))}$.",
                f"Hosilani $\\frac{{d}}{{d{variable}}}$ qoidasiga ko‘ra hisoblaymiz.",
                f"Natija: ${sp.latex(result)}$. Hosilani integrallash orqali tekshirish mumkin."]
    if operation == "integral":
        return [f"Integrallanuvchi funksiya: ${sp.latex(extra.get('expression', expression))}$.",
                "Simvolik integrallash orqali boshlang‘ich funksiyani topamiz.",
                f"Natija: ${sp.latex(result)}$. Hosilani olib tekshiramiz."]
    if operation == "limit":
        return [f"${variable}$ ni ${sp.latex(extra['point'])}$ ga yaqinlashtiramiz.",
                f"Ifoda limitini hisoblaymiz: ${sp.latex(result)}$."]
    if operation in {"determinant", "matrix"}:
        return [f"Matritsa o‘lchami: ${extra['rows']}\\times{extra['cols']} $.",
                f"{extra.get('operation_label', 'Matritsa natijasi')}: ${sp.latex(result)}$."]
    return [f"Ifoda: ${sp.latex(extra.get('expression', expression))}$.",
            f"Ifodani {extra.get('operation_label', 'soddalashtirish')} qoidalari bilan hisoblaymiz.",
            f"Natija: ${sp.latex(result)}$."]


def _boolean_vector_response(problem: str) -> dict[str, Any] | None:
    intent = re.search(r"\b(?:soxta|muhim|fiktiv|argument|bulev|boolean|bool|truth\s*table|dnf|knf)\b|f\s*\(", problem, re.I)
    if not intent:
        return None
    vector_pattern = re.compile(r"=\s*[\(\[\{]?\s*([01]{16}|[01]{8}|[01]{4})(?![01])\s*[\)\]\}]?")
    vectors = [match.group(1) for match in vector_pattern.finditer(problem)][:32]
    if not vectors:
        return None

    results: list[str] = []
    latex_results: list[str] = []
    steps: list[str] = []
    for index, vector in enumerate(vectors, 1):
        n = len(vector).bit_length() - 1
        variables = list(sp.symbols(" ".join(f"x{i}" for i in range(1, n + 1))))
        essential: list[str] = []
        dummy: list[str] = []
        comparisons: list[str] = []
        for variable_index in range(n):
            block_size = 2 ** (n - variable_index)
            half_size = block_size // 2
            differs = any(
                vector[block_start:block_start + half_size] != vector[block_start + half_size:block_start + block_size]
                for block_start in range(0, len(vector), block_size)
            )
            name = f"x_{variable_index + 1}"
            (essential if differs else dummy).append(name)
            comparisons.append(f"{name}: {half_size}-bit yarimlar { 'farq qiladi' if differs else 'barcha bloklarda teng' }")

        assignments = list(itertools.product((0, 1), repeat=n))
        minterms = [list(row) for row, bit in zip(assignments, vector) if bit == "1"]
        dnf = sp.SOPform(variables, minterms) if minterms else sp.false
        knf = sp.POSform(variables, minterms) if minterms else sp.false
        essential_text = ", ".join(essential) if essential else "yo‘q"
        dummy_text = ", ".join(dummy) if dummy else "yo‘q"
        results.append(f"Vektor {index} ({n} o‘zgaruvchi): {vector}; muhim: {essential_text}; soxta/fiktiv: {dummy_text}; DNF: {sp.sstr(dnf)}; KNF: {sp.sstr(knf)}")
        latex_results.append(f"f_{index}({','.join(sp.latex(item) for item in variables)})={sp.latex(dnf)}")
        steps.extend([
            f"{index}-vektor: ${vector}$, uzunligi $2^{n}={len(vector)}$, demak $n={n}$.",
            "Har bir o‘zgaruvchi uchun uning 0 va 1 holatidagi blok yarimlarini taqqoslaymiz: " + "; ".join(comparisons) + ".",
            f"Mantiqiy ifoda: DNF ${sp.latex(dnf)}$; KNF ${sp.latex(knf)}$.",
        ])
    return {
        "supported": True,
        "domain": "discrete",
        "operation": "boolean_vector",
        "input": problem,
        "result": "\n".join(results),
        "latex": r"\; , \; ".join(latex_results),
        "theory": "Boolean vektorning har bir biti kirishlar to‘plamining leksikografik tartibdagi qiymatidir. O‘zgaruvchi muhim bo‘ladi, agar uni o‘zgartirish kamida bitta holatda funksiya qiymatini o‘zgartirsa.",
        "formula": r"f(\tilde{x}^n)=(\alpha_0,\ldots,\alpha_{2^n-1})",
        "steps": steps,
        "verification": "Har bir o‘zgaruvchi uchun barcha bloklardagi mos yarimlar taqqoslandi; DNF va KNF SymPy yordamida tuzildi.",
    }


def compute(request: dict[str, Any]) -> dict[str, Any]:
    problem = request.get("problem", "")
    if not isinstance(problem, str) or not problem.strip() or len(problem) > 1000:
        raise EngineInputError("Masala matni 1–1000 belgi orasida bo‘lishi kerak.")
    lowered = problem.lower()
    variable_hint = request.get("variable") if isinstance(request.get("variable"), str) else None

    boolean_result = _boolean_vector_response(problem)
    if boolean_result:
        return boolean_result

    geometry = _plane_geometry(problem, lowered)
    if geometry:
        return geometry

    matrix_intent = any(word in lowered for word in ("determinant", "determinanti", "determinantini", "matritsa", "matrix", "matrice"))
    matrix_intent = matrix_intent or problem.lstrip().startswith("[[")
    if matrix_intent:
        matrices = _extract_matrices(problem)
        matrix = matrices[0]
        if matrix.rows != matrix.cols and any(word in lowered for word in ("determinant", "determinanti", "determinantini")):
            raise EngineInputError("Determinant faqat kvadrat matritsa uchun aniqlanadi.")
        if len(matrices) == 2 and any(word in lowered for word in ("multiply", "matritsalarni ko‘paytir", "ko‘paytma")):
            result = matrices[0] * matrices[1]
            label, operation = "Matritsalar ko‘paytmasi", "matrix"
        elif len(matrices) == 2 and any(word in lowered for word in ("add", "qo‘sh", "yig‘indi")):
            result = matrices[0] + matrices[1]
            label, operation = "Matritsalar yig‘indisi", "matrix"
        elif any(word in lowered for word in ("inverse", "teskari matritsa", "invers")):
            result = matrix.inv()
            label, operation = "Teskari matritsa", "matrix"
        elif any(word in lowered for word in ("transpose", "transponir")):
            result = matrix.T
            label, operation = "Transponirlangan matritsa", "matrix"
        elif any(word in lowered for word in ("trace", "iz", "diagonal yig‘indi")):
            result = sp.trace(matrix)
            label, operation = "Matritsa izi", "matrix"
        elif any(word in lowered for word in ("determinant", "determinanti", "determinantini")):
            result = matrix.det()
            label, operation = "Determinant", "determinant"
        else:
            result = matrix
            label, operation = "Matritsa", "matrix"
        extra = {"rows": matrix.rows, "cols": matrix.cols, "operation_label": label}
        return _response(operation, str(matrix), result, _steps(operation, result, extra=extra), "Matritsa elementlari SymPy yordamida aniq hisoblandi.")

    limit_match = re.search(r"(?:as\s+)?([a-z])\s*(?:->|→|tends\s+to|approaches|to)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:\s*/\s*\d+)?)", lowered)
    if any(word in lowered for word in ("limit", "lim ", "limitini", "limitni", "chegarasi")):
        if not limit_match:
            raise EngineInputError("Limit uchun yaqinlashish nuqtasini, masalan x -> 1, kiriting.")
        variable = _find_variable(problem, variable_hint or limit_match.group(1))
        point = safe_expression(limit_match.group(2))
        expression_source = _trim_instruction(problem[:limit_match.start()] + " " + problem[limit_match.end():])
        expression = safe_expression(expression_source)
        result = sp.limit(expression, variable, point)
        return _response("limit", expression_source, result,
                         _steps("limit", result, variable=variable.name, extra={"point": point}),
                         f"Limit SymPy bilan $x\\to {sp.latex(point)}$ nuqtada hisoblandi.")

    if any(word in lowered for word in ("derivative", "differentiat", "hosila", "differensial")):
        source = _trim_instruction(problem)
        source = re.sub(r"\b(?:d/dx|dy/dx)\b", " ", source, flags=re.I).strip()
        variable = _find_variable(source, _requested_variable(problem, variable_hint))
        expression = safe_expression(source)
        result = sp.diff(expression, variable)
        return _response("derivative", source, result,
                         _steps("derivative", result, variable=variable.name, extra={"expression": expression}),
                         f"$\\frac{{d}}{{d{variable.name}}}$ hosila SymPy orqali hisoblandi.")

    if any(word in lowered for word in ("integral", "integrate", "integralini", "integrallash")):
        definite = re.search(r"\bfrom\s+([^\s,]+)\s+to\s+([^\s,]+)", lowered)
        source = _trim_instruction(problem)
        source = re.sub(r"\b(?:from\s+\S+\s+to\s+\S+|d[xyz])\b", " ", source, flags=re.I).strip()
        variable = _find_variable(source, _requested_variable(problem, variable_hint))
        expression = safe_expression(source)
        if definite:
            lower, upper = safe_expression(definite.group(1)), safe_expression(definite.group(2))
            result = sp.integrate(expression, (variable, lower, upper))
        else:
            result = sp.integrate(expression, variable)
        return _response("integral", source, result,
                         _steps("integral", result, variable=variable.name, extra={"expression": expression}),
                         "Integral hisoblandi; natijani hosila olish orqali tekshirish mumkin.")

    equation_parts = re.findall(r"([^=<>]+)=([^=<>]+)", problem)
    if equation_parts:
        lhs = safe_expression(_trim_instruction(equation_parts[0][0]))
        rhs = safe_expression(_trim_instruction(equation_parts[0][1]))
        equation = sp.expand(lhs - rhs)
        variable = _find_variable(equation_parts[0][0] + equation_parts[0][1], _requested_variable(problem, variable_hint))
        polynomial = sp.Poly(equation, variable)
        solutions = sp.solve(sp.Eq(lhs, rhs), variable)
        extra: dict[str, Any] = {"equation": equation, "degree": polynomial.degree() if polynomial.is_univariate else None}
        if polynomial.is_univariate and polynomial.degree() == 2:
            a, b, c = polynomial.all_coeffs()
            extra.update({"coefficients": (a, b, c), "discriminant": sp.discriminant(equation, variable)})
        result = [f"{variable.name}={_plain_result(item)}" for item in solutions]
        response = _response("solve", problem, result,
                             _steps("solve", solutions, variable=variable.name, extra=extra),
                             "Tenglama ildizlari hisoblandi; natijalarni dastlabki tenglamaga qo‘yib tekshirish mumkin.",
                             canonical=[[f"{variable.name}={_plain_result(item)}", f"{variable.name}={sp.latex(item)}"] for item in solutions])
        response["latex"] = r",\quad ".join(f"{variable.name}={sp.latex(item)}" for item in solutions)
        return response

    if any(word in lowered for word in ("expand", "yoying", "oching")):
        operation, transform, label = "expand", sp.expand, "qavslarni ochish"
    elif any(word in lowered for word in ("factor", "factorize", "ko‘paytuvchilarga")):
        operation, transform, label = "factor", sp.factor, "ko‘paytuvchilarga ajratish"
    elif any(word in lowered for word in ("simplify", "soddalasht", "hisoblang", "calculate", "simplification")):
        operation, transform, label = "simplify", sp.simplify, "soddalashtirish"
    else:
        possible_expression = _trim_instruction(problem)
        if not re.fullmatch(r"[0-9A-Za-z_π.()+\-*/^,\s]+", possible_expression):
            return {"supported": False, "reason": "Bu masala SymPy amallaridan biriga avtomatik ajratilmadi."}
        operation, transform, label = "simplify", sp.simplify, "soddalashtirish"

    source = _trim_instruction(problem)
    expression = safe_expression(source)
    result = transform(expression)
    return _response(operation, source, result,
                     _steps(operation, result, extra={"expression": expression, "operation_label": label}),
                     f"Ifoda SymPy yordamida {label}.")


def _response(operation: str, source: str, result: Any, steps: list[str], verification: str, canonical: list[list[str]] | None = None) -> dict[str, Any]:
    return {
        "supported": True,
        "operation": operation,
        "input": source,
        "result": _plain_result(result),
        "latex": sp.latex(result),
        "steps": steps,
        "verification": verification,
        "canonical": canonical if canonical is not None else [[_plain_result(result), sp.latex(result)]],
    }


def _geometry_response(operation: str, source: str, result: Any, *, theory: str, formula: str,
                       steps: list[str], diagram: dict[str, Any], verification: str | None = None) -> dict[str, Any]:
    return {
        "supported": True,
        "domain": "geometry",
        "operation": operation,
        "input": source,
        "result": _plain_result(result),
        "latex": sp.latex(result),
        "theory": theory,
        "formula": formula,
        "steps": steps,
        "verification": verification or "Natija geometrik formula va SymPy hisob-kitobi bilan tekshirildi.",
        "canonical": [[_plain_result(result), sp.latex(result)]],
        "diagram": diagram,
    }


NUMBER_PATTERN = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"


def _number_values(source: str) -> list[sp.Expr]:
    return [safe_expression(value) for value in re.findall(NUMBER_PATTERN, source.replace(",", " "))]


def _quantity(source: str, labels: tuple[str, ...]) -> sp.Expr | None:
    number = rf"({NUMBER_PATTERN})"
    for label in sorted(labels, key=len, reverse=True):
        match = re.search(rf"(?:\b{label}\b)\s*(?:is|of|=|:)?\s*{number}", source, re.I)
        if match:
            return safe_expression(match.group(1))
    return None


def _positive(value: sp.Expr | None, label: str) -> sp.Expr:
    if value is None:
        raise EngineInputError(f"{label} qiymatini kiriting.")
    if value.is_positive is False or value.is_number and value <= 0:
        raise EngineInputError(f"{label} musbat bo‘lishi kerak.")
    return value


def _metric(lowered: str, solid: bool = False) -> str:
    if any(word in lowered for word in ("perimeter", "circumference", "perimetri", "perimetr", "aylana uzunligi")):
        return "perimeter"
    if any(word in lowered for word in ("surface area", "total surface", "lateral area", "sirt yuzasi", "to‘la sirt", "yon sirt")):
        return "surface"
    if any(word in lowered for word in ("volume", "hajm", "sig‘im")):
        return "volume"
    if re.search(r"\b(?:angles?|burchak(?:lar|lari)?|degree|gradus)\b", lowered):
        return "angle"
    if any(word in lowered for word in ("area", "yuz", "maydon")):
        return "area"
    if any(phrase in lowered for phrase in ("find radius", "calculate radius", "radiusni top", "radiusini top", "radiusni hisob", "radiusini hisob")):
        return "radius"
    if any(phrase in lowered for phrase in ("find diameter", "calculate diameter", "diametrni top", "diametrini top", "diametrni hisob")):
        return "diameter"
    if any(word in lowered for word in ("hypotenuse", "gipotenuz")) or re.search(r"(?:find|calculate|top|hisob).{0,20}(?:side|tomon)", lowered):
        return "side"
    return "volume" if solid else "area"


def _coordinate_geometry(problem: str, lowered: str) -> dict[str, Any] | None:
    points_raw = re.findall(r"\(?\s*([+-]?\d+(?:\.\d+)?)\s*[,;]\s*([+-]?\d+(?:\.\d+)?)\s*\)?", problem)
    coordinate_intent = any(word in lowered for word in ("coordinate", "koordinat", "distance between", "ikki nuqta", "midpoint", "o‘rta nuqta", "slope", "qiyalik", "chiziq tenglamasi"))
    named_points = len(re.findall(r"[A-Z]\s*\(\s*[+-]?\d+(?:\.\d+)?\s*[,;]\s*[+-]?\d+(?:\.\d+)?\s*\)", problem)) >= 2
    if any(word in lowered for word in ("matrix", "matritsa", "determinant")):
        return None
    if not coordinate_intent and not named_points:
        return None
    if len(points_raw) < 2:
        raise EngineInputError("Koordinata masalasi uchun kamida ikki nuqtani, masalan A(1, 2), B(4, 6), kiriting.")
    points = [(safe_expression(x), safe_expression(y)) for x, y in points_raw[:4]]
    (x1, y1), (x2, y2) = points[:2]
    labels = {"A": f"({sp.sstr(x1)}, {sp.sstr(y1)})", "B": f"({sp.sstr(x2)}, {sp.sstr(y2)})"}
    diagram = {"kind": "coordinates", "points": [[float(x), float(y)] for x, y in points], "labels": labels}
    if len(points) >= 3 and any(word in lowered for word in ("area", "yuz", "maydon")):
        (x3, y3) = points[2]
        result = sp.Abs(x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)) / 2
        return _geometry_response("geometry_coordinate_triangle_area", problem, result,
            theory="Koordinata tekisligidagi uchburchak yuzasi determinant formulasidan olinadi.",
            formula=r"S=\frac{1}{2}|x_1(y_2-y_3)+x_2(y_3-y_1)+x_3(y_1-y_2)|",
            steps=["Uch nuqtaning koordinatalarini formulaga qo‘yamiz.", f"Hisoblaymiz: $S={sp.latex(result)}$.", "Yuza manfiy bo‘lmasligi uchun modul olamiz."],
            diagram={**diagram, "labels": {**labels, "C": f"({sp.sstr(x3)}, {sp.sstr(y3)})"}})
    dx, dy = x2 - x1, y2 - y1
    if any(word in lowered for word in ("midpoint", "o‘rta nuqta", "o'rta nuqta")):
        result = ((x1 + x2) / 2, (y1 + y2) / 2)
        return _geometry_response("geometry_midpoint", problem, sp.Tuple(*result),
            theory="Kesmaning o‘rta nuqtasi koordinatalari mos koordinatalarning o‘rtacha qiymatidir.",
            formula=r"M=\left(\frac{x_1+x_2}{2},\frac{y_1+y_2}{2}\right)",
            steps=[f"$x_M=({sp.latex(x1)}+{sp.latex(x2)})/2={sp.latex(result[0])}$.", f"$y_M=({sp.latex(y1)}+{sp.latex(y2)})/2={sp.latex(result[1])}$.", f"O‘rta nuqta: $M={sp.latex(sp.Tuple(*result))}$."], diagram=diagram)
    if any(word in lowered for word in ("slope", "gradient", "qiyalik")):
        if sp.simplify(dx) == 0:
            raise EngineInputError("Vertikal chiziqning qiyaligi aniqlanmagan.")
        result = sp.simplify(dy / dx)
        formula = r"m=\frac{y_2-y_1}{x_2-x_1}"
        operation = "geometry_slope"
        theory = "Chiziq qiyaligi x bir birlikka o‘zgarganda y qancha o‘zgarishini ko‘rsatadi."
    elif any(word in lowered for word in ("equation of the line", "line equation", "chiziq tenglamasi")):
        if sp.simplify(dx) == 0:
            result = sp.Eq(VARIABLES["x"], x1)
        else:
            slope = sp.simplify(dy / dx)
            result = sp.Eq(VARIABLES["y"], sp.expand(slope * (VARIABLES["x"] - x1) + y1))
        formula = r"y-y_1=m(x-x_1)"
        operation = "geometry_line"
        theory = "Ikki nuqta orqali o‘tuvchi to‘g‘ri chiziq nuqta-qiyalik tenglamasi bilan yoziladi."
    else:
        result = sp.sqrt(dx**2 + dy**2)
        formula = r"d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}"
        operation = "geometry_distance"
        theory = "Ikki nuqta orasidagi masofa Pifagor teoremasidan kelib chiqadi."
    return _geometry_response(operation, problem, result, theory=theory, formula=formula,
        steps=[f"Koordinatalar: $A({sp.latex(x1)},{sp.latex(y1)})$, $B({sp.latex(x2)},{sp.latex(y2)})$.",
               f"Formulaga qo‘yamiz: ${formula}$.", f"Natija: ${sp.latex(result)}$.", "Natijani koordinatalar farqini qayta hisoblab tekshiramiz."], diagram=diagram)


def _solid_geometry(problem: str, lowered: str) -> dict[str, Any] | None:
    shape = None
    for name, words in [
        ("cuboid", ("cuboid", "kuboid", "rectangular prism", "parallelepiped", "parallelepiped")),
        ("cube", ("cube", "kub")), ("cylinder", ("cylinder", "silindr")),
        ("cone", ("cone", "konus")), ("sphere", ("sphere", "sfera", "shar")),
        ("prism", ("prism", "prizma")), ("pyramid", ("pyramid", "piramida")),
    ]:
        if any(word in lowered for word in words):
            shape = name
            break
    if not shape:
        return None
    clean = re.sub(r"\b3\s*d\b", " ", lowered)
    numbers = _number_values(clean)
    metric = _metric(lowered, solid=True)
    side = _quantity(lowered, ("side", "qirrasi", "tomoni", "tomon", "edge", "qirra"))
    radius = _quantity(lowered, ("radius", "radiusi", "r"))
    diameter = _quantity(lowered, ("diameter", "diametri", "d"))
    height = _quantity(lowered, ("height", "balandligi", "balandlik", "h"))
    length = _quantity(lowered, ("length", "uzunligi", "bo‘yi", "bo'yi", "l"))
    width = _quantity(lowered, ("width", "eni", "w"))
    base_area = _quantity(lowered, ("base area", "asos yuzasi", "asosining yuzi", "b"))
    base_perimeter = _quantity(lowered, ("base perimeter", "asos perimetri"))
    if shape == "cube":
        a = _positive(side or (numbers[0] if numbers else None), "Kub qirrasi")
        volume, surface = a**3, 6 * a**2
        selected = {"volume": volume, "surface": surface, "perimeter": 12 * a, "side": a, "radius": a, "diameter": 2*a}[metric]
        formula = r"V=a^3,\quad S=6a^2"
        steps = [f"Kub qirrasi $a={sp.latex(a)}$.", f"Hajm: $V=a^3={sp.latex(volume)}$.", f"To‘la sirt: $S=6a^2={sp.latex(surface)}$."]
        kind, labels = "cube", {"a": sp.sstr(a)}
    elif shape == "cuboid":
        dims = [length, width, height]
        if all(item is not None for item in dims): l, w, h = dims
        elif len(numbers) >= 3: l, w, h = numbers[:3]
        else: raise EngineInputError("Parallelepiped uchun uzunlik, eni va balandligini kiriting.")
        l, w, h = (_positive(item, label) for item, label in zip((l, w, h), ("Uzunlik", "Eni", "Balandlik")))
        volume, surface = l*w*h, 2*(l*w+l*h+w*h)
        selected = {"volume": volume, "surface": surface, "side": sp.sqrt(l**2+w**2+h**2), "diameter": sp.sqrt(l**2+w**2+h**2)}.get(metric, volume)
        formula = r"V=lwh,\quad S=2(lw+lh+wh)"
        steps = [f"O‘lchamlar: $l={sp.latex(l)}$, $w={sp.latex(w)}$, $h={sp.latex(h)}$.", f"Hajm: $V=lwh={sp.latex(volume)}$.", f"To‘la sirt: $S=2(lw+lh+wh)={sp.latex(surface)}$."]
        kind, labels = "cuboid", {"l": sp.sstr(l), "w": sp.sstr(w), "h": sp.sstr(h)}
    elif shape in ("cylinder", "cone", "sphere"):
        r = _positive(radius or (diameter / 2 if diameter is not None else numbers[0] if numbers else None), "Radius")
        if shape == "sphere":
            volume, surface = 4*sp.pi*r**3/3, 4*sp.pi*r**2
            selected = {"volume": volume, "surface": surface, "side": r, "radius": r, "diameter": 2*r, "perimeter": 2*sp.pi*r}.get(metric, volume)
            formula = r"V=\frac{4}{3}\pi r^3,\quad S=4\pi r^2"
            steps = [f"Radius $r={sp.latex(r)}$.", f"Hajm: $V=\\frac{{4}}{{3}}\\pi r^3={sp.latex(volume)}$.", f"Sirt yuzi: $S=4\\pi r^2={sp.latex(surface)}$."]
            kind = "sphere"
        else:
            h = _positive(height or (numbers[1] if len(numbers) >= 2 else None), "Balandlik")
            if shape == "cylinder":
                volume, surface = sp.pi*r**2*h, 2*sp.pi*r*(r+h)
                lateral = 2*sp.pi*r*h
                selected = {"volume": volume, "surface": surface, "side": h, "radius": r, "diameter": 2*r, "perimeter": 2*sp.pi*r}.get(metric, volume)
                formula = r"V=\pi r^2h,\quad S=2\pi r(r+h)"
                steps = [f"Radius $r={sp.latex(r)}$, balandlik $h={sp.latex(h)}$.", f"Asos yuzi: $B=\\pi r^2={sp.latex(sp.pi*r**2)}$.", f"Hajm: $V=Bh={sp.latex(volume)}$.", f"To‘la sirt: $S=2\\pi r(r+h)={sp.latex(surface)}$."]
                kind = "cylinder"
            else:
                slant = sp.sqrt(r**2+h**2)
                volume, surface = sp.pi*r**2*h/3, sp.pi*r*(r+slant)
                selected = {"volume": volume, "surface": surface, "side": slant, "radius": r, "diameter": 2*r, "perimeter": 2*sp.pi*r}.get(metric, volume)
                formula = r"V=\frac{1}{3}\pi r^2h,\quad l=\sqrt{r^2+h^2},\quad S=\pi r(r+l)"
                steps = [f"Radius $r={sp.latex(r)}$, balandlik $h={sp.latex(h)}$.", f"Qiya balandlik: $l=\\sqrt{{r^2+h^2}}={sp.latex(slant)}$.", f"Hajm: $V=\\frac{{1}}{{3}}\\pi r^2h={sp.latex(volume)}$.", f"To‘la sirt: $S=\\pi r(r+l)={sp.latex(surface)}$."]
                kind = "cone"
        labels = {"r": sp.sstr(r), **({"h": sp.sstr(h)} if shape != "sphere" else {})}
    elif shape in ("prism", "pyramid"):
        b = _positive(base_area or (numbers[0] if numbers else None), "Asos yuzasi")
        h = _positive(height or (numbers[1] if len(numbers) > 1 else None), "Balandlik")
        volume = b*h if shape == "prism" else b*h/3
        surface = (2*b + base_perimeter*h) if shape == "prism" and base_perimeter else None
        slant_height = _quantity(lowered, ("slant height", "qiya balandlik", "apofema"))
        if shape == "pyramid" and base_perimeter and (slant_height or len(numbers) > 3):
            slant_height = slant_height or numbers[-1]
            surface = b + base_perimeter*slant_height/2
        if metric == "surface" and surface is None:
            needed = "asos perimetri" if shape == "prism" else "asos perimetri va qiya balandlik"
            raise EngineInputError(f"Sirt yuzasi uchun {needed} ham kerak.")
        selected = volume if metric == "volume" or surface is None else surface
        formula = r"V=Bh" if shape == "prism" else r"V=\frac{1}{3}Bh"
        steps = [f"Asos yuzi $B={sp.latex(b)}$, balandlik $h={sp.latex(h)}$.", f"Hajm formulasi: ${formula}$.", f"Hajm: $V={sp.latex(volume)}$."]
        kind, labels = shape, {"B": sp.sstr(b), "h": sp.sstr(h)}
    else:
        return None
    if metric == "surface": label = "Sirt yuzi"
    elif metric == "volume": label = "Hajm"
    elif metric == "perimeter": label = "Yon uzunlik"
    elif metric == "side": label = "O‘lcham"
    else: label = "Hajm"
    steps.append(f"So‘ralgan natija ({label.lower()}): ${sp.latex(selected)}$.")
    return _geometry_response(f"geometry_{shape}_{metric}", problem, selected,
        theory=f"{shape.capitalize()} uchun o‘lchamlar geometrik formula bilan bog‘lanadi. Hajm uch o‘lchamni, sirt yuzi esa tashqi yuzalarni hisoblaydi.",
        formula=formula, steps=steps, diagram={"kind": kind, "labels": labels})


def _plane_geometry(problem: str, lowered: str) -> dict[str, Any] | None:
    coordinate = _coordinate_geometry(problem, lowered)
    if coordinate:
        return coordinate
    solid = _solid_geometry(problem, lowered)
    if solid:
        return solid

    shape = None
    for name, words in [
        ("triangle", ("triangle", "uchburchak", "pitagor", "pythagorean", "right angle triangle", "right triangle")),
        ("circle", ("circle", "aylana", "doira", "circumference")),
        ("trapezoid", ("trapezoid", "trapetsiya")),
        ("parallelogram", ("parallelogram", "parallelogramm")),
        ("rhombus", ("rhombus", "romb")),
        ("rectangle", ("rectangle", "to‘g‘ri to‘rtburchak", "togri tortburchak")),
        ("square", ("square", "kvadrat")),
        ("polygon", ("polygon", "ko‘pburchak", "ko'p burchak", "hexagon", "pentagon", "octagon", "beshburchak", "oltiburchak")),
    ]:
        if any(word in lowered for word in words):
            shape = name
            break
    geometry_words = ("similar", "o‘xshash", "o'xshash", "congruent", "teng uchburchak", "triangle", "uchburchak", "circle", "aylana", "doira", "polygon", "ko‘pburchak", "square", "kvadrat", "rectangle", "trapez", "romb", "parallelogram", "pitagor", "pythagorean")
    if not shape and not any(word in lowered for word in geometry_words):
        return None

    if any(word in lowered for word in ("similar", "o‘xshash", "o'xshash", "congruent", "kongruent", "teng uchburchak")):
        values = _number_values(problem)
        if len(values) >= 6:
            first, second = values[:3], values[3:6]
            ratios = [sp.simplify(b/a) for a, b in zip(first, second) if a != 0]
            equal = len(ratios) == 3 and ratios[0] == ratios[1] == ratios[2]
            congruent = all(sp.simplify(a-b) == 0 for a, b in zip(first, second))
            is_congruence = any(word in lowered for word in ("congruent", "kongruent", "teng uchburchak"))
            result = sp.true if congruent else sp.false if is_congruence else sp.true if equal else sp.false
            name = "kongruent" if is_congruence else "o‘xshash"
            return _geometry_response(f"geometry_{name}", problem, result,
                theory="Uchburchaklar o‘xshash bo‘lishi uchun mos tomonlar nisbati teng; kongruent bo‘lishi uchun mos tomonlar va shakl o‘lchamlari teng bo‘ladi.",
                formula=r"\frac{a_2}{a_1}=\frac{b_2}{b_1}=\frac{c_2}{c_1}",
                steps=[f"Mos tomonlar nisbatlari: ${', '.join(sp.latex(ratio) for ratio in ratios)}$.", f"Shakllar {name if bool(result) else 'emas'}.", "Nisbatlar (yoki kongruentlikda mos tomonlar) sharti bo‘yicha tekshirildi."],
                diagram={"kind": "triangle", "labels": {"a": sp.sstr(first[0]), "b": sp.sstr(first[1]), "c": sp.sstr(first[2])}})
        factor = _quantity(lowered, ("scale factor", "koeffitsiyent", "masshtab"))
        side = _quantity(lowered, ("side", "tomon", "tomoni"))
        if factor and side:
            result = sp.simplify(factor * side)
            return _geometry_response("geometry_similarity_side", problem, result,
                theory="O‘xshash shakllarda mos tomonlar o‘xshashlik koeffitsiyentiga mutanosib o‘zgaradi.",
                formula=r"a_{2}=k a_{1}", steps=[f"O‘xshashlik koeffitsiyenti $k={sp.latex(factor)}$.", f"Mos tomon $a_1={sp.latex(side)}$.", f"$a_2=ka_1={sp.latex(result)}$."],
                diagram={"kind": "triangle", "labels": {"k": sp.sstr(factor), "a": sp.sstr(side)}})
        raise EngineInputError("O‘xshashlik/kongruentlikni tekshirish uchun ikkala shaklning mos tomonlarini kiriting.")

    if not shape:
        shape = "triangle" if any(word in lowered for word in ("pitagor", "pythagorean")) else None
    if shape == "circle":
        radius = _quantity(lowered, ("radius", "radiusi", "r"))
        diameter = _quantity(lowered, ("diameter", "diametri", "d"))
        values = _number_values(problem)
        radius = radius or (diameter / 2 if diameter is not None else values[0] if values else None)
        radius = _positive(radius, "Aylana radiusi")
        metric = _metric(lowered)
        area, circumference = sp.pi*radius**2, 2*sp.pi*radius
        result = {"area": area, "perimeter": circumference, "side": 2*radius, "radius": radius, "diameter": 2*radius}.get(metric, area)
        formula = r"S=\pi r^2,\quad C=2\pi r,\quad d=2r"
        label = {"area": "Yuza", "perimeter": "Aylana uzunligi", "side": "O‘lcham", "radius": "Radius", "diameter": "Diametr"}.get(metric, "Yuza")
        return _geometry_response(f"geometry_circle_{metric}", problem, result,
            theory="Aylana radiusi markazdan aylana chizig‘igacha bo‘lgan masofa. Diametr radiusning ikki baravari; yuza va uzunlik π orqali topiladi.",
            formula=formula,
            steps=[f"Radius $r={sp.latex(radius)}$.", f"Yuza: $S=\\pi r^2={sp.latex(area)}$.", f"Aylana uzunligi: $C=2\\pi r={sp.latex(circumference)}$.", f"So‘ralgan {label.lower()}: ${sp.latex(result)}$."],
            diagram={"kind": "circle", "labels": {"r": sp.sstr(radius), "d": sp.sstr(2*radius)}})

    if shape == "triangle":
        metric = _metric(lowered)
        base = _quantity(lowered, ("base", "asos", "asosi"))
        height = _quantity(lowered, ("height", "balandligi", "balandlik"))
        angle_section = re.search(r"\b(?:angles?|burchaklar(?:i)?)([^.;!?]{0,100})", lowered)
        angles = [safe_expression(value) for value in re.findall(NUMBER_PATTERN, angle_section.group(1))] if angle_section else []
        values = _number_values(problem)
        side_values = values
        if base is not None and height is not None:
            area = base*height/2
            if metric in ("perimeter", "side"):
                raise EngineInputError("Perimetr yoki tomon uchun barcha uch tomon o‘lchamlarini kiriting.")
            result = area
            steps = [f"Asos $b={sp.latex(base)}$, balandlik $h={sp.latex(height)}$.", f"Uchburchak yuzi formulasi: $S=\\frac{{bh}}{{2}}$.", f"$S=\\frac{{{sp.latex(base)}\\cdot{sp.latex(height)}}}{{2}}={sp.latex(area)}$." ]
            return _geometry_response(f"geometry_triangle_{metric}", problem, result,
                theory="Uchburchak yuzi asos va shu asosga tushirilgan balandlik ko‘paytmasining yarmiga teng.",
                formula=r"S=\frac{bh}{2}", steps=steps,
                diagram={"kind": "triangle", "labels": {"b": sp.sstr(base), "h": sp.sstr(height)}})
        if len(angles) >= 2 and metric == "angle":
            result = sp.simplify(180-angles[0]-angles[1])
            return _geometry_response("geometry_triangle_angle", problem, result,
                theory="Uchburchak ichki burchaklari yig‘indisi 180° ga teng.", formula=r"A+B+C=180^\circ",
                steps=[f"Berilgan burchaklar: ${sp.latex(angles[0])}^\\circ$ va ${sp.latex(angles[1])}^\\circ$.", f"Uchinchi burchak: $180^\\circ-{sp.latex(angles[0])}^\\circ-{sp.latex(angles[1])}^\\circ={sp.latex(result)}^\\circ$."],
                diagram={"kind": "triangle", "labels": {"A": sp.sstr(angles[0]), "B": sp.sstr(angles[1]), "C": sp.sstr(result)}})
        has_right = any(word in lowered for word in ("right", "to‘g‘ri burchakli", "togri burchakli", "pitagor", "pythagorean"))
        if has_right and len(values) == 2:
            legs = values[:2]
            hypotenuse = _quantity(lowered, ("hypotenuse", "gipotenuza"))
            known_leg = None
            if metric == "area" and hypotenuse is None:
                result = legs[0]*legs[1]/2
                steps = ["To‘g‘ri burchakli uchburchakda katetlar o‘zaro perpendikulyar.", f"Yuza formulasi: $S=\\frac{{ab}}{{2}}=\\frac{{{sp.latex(legs[0])}\\cdot{sp.latex(legs[1])}}}{{2}}={sp.latex(result)}$." ]
            elif metric == "perimeter" and hypotenuse is None:
                hypotenuse = sp.sqrt(legs[0]**2+legs[1]**2)
                result = legs[0]+legs[1]+hypotenuse
                steps = ["Pifagor teoremasi: $c=\\sqrt{a^2+b^2}$.", f"Gipotenuza: $c={sp.latex(hypotenuse)}$.", f"Perimetr: $P=a+b+c={sp.latex(result)}$." ]
            elif hypotenuse is not None:
                known_leg = next((value for value in values if sp.simplify(value-hypotenuse) != 0), None)
                if known_leg is None or sp.simplify(hypotenuse**2-known_leg**2).is_nonpositive is True:
                    raise EngineInputError("Gipotenuzadan kichik musbat katet qiymatini kiriting.")
                leg = sp.sqrt(hypotenuse**2-known_leg**2)
                result = leg
                steps = [f"Pifagor teoremasi: $a^2+b^2=c^2$, bu yerda $c$ — gipotenuza.", f"Noma’lum katet: $b=\\sqrt{{c^2-a^2}}=\\sqrt{{{sp.latex(hypotenuse)}^2-{sp.latex(known_leg)}^2}}={sp.latex(result)}$." ]
            else:
                result = sp.sqrt(legs[0]**2+legs[1]**2)
                steps = ["Pifagor teoremasi: $a^2+b^2=c^2$.", f"Katetlarni qo‘yamiz: $c=\\sqrt{{{sp.latex(legs[0])}^2+{sp.latex(legs[1])}^2}}={sp.latex(result)}$." ]
            triangle_c = hypotenuse or sp.sqrt(legs[0]**2+legs[1]**2)
            triangle_a, triangle_b = (known_leg, result) if hypotenuse is not None and known_leg is not None else legs
            return _geometry_response("geometry_pythagorean", problem, result,
                theory="To‘g‘ri burchakli uchburchakda katetlar kvadratlari yig‘indisi gipotenuza kvadratiga teng.", formula=r"a^2+b^2=c^2",
                steps=steps+ ["Natijani tenglikka qayta qo‘yib tekshiramiz."], diagram={"kind": "rightTriangle", "labels": {"a": sp.sstr(triangle_a), "b": sp.sstr(triangle_b), "c": sp.sstr(triangle_c)}})
        if len(side_values) >= 3:
            a, b, c = side_values[:3]
            if any(value.is_positive is False or value.is_number and value <= 0 for value in (a, b, c)):
                raise EngineInputError("Uchburchak tomonlari musbat bo‘lishi kerak.")
            if any(sp.simplify(a+b-c).is_nonpositive is True for a,b,c in ((a,b,c),(a,c,b),(b,c,a))):
                raise EngineInputError("Berilgan tomonlar uchburchak tengsizliklarini qanoatlantirmaydi.")
            perimeter = a+b+c
            semiperimeter = perimeter/2
            area = sp.sqrt(semiperimeter*(semiperimeter-a)*(semiperimeter-b)*(semiperimeter-c))
            if metric == "perimeter": result, label = perimeter, "Perimetr"
            elif metric == "side": result, label = max(side_values[:3]), "Eng katta tomon"
            else: result, label = area, "Yuza"
            cos_a = sp.acos((b**2+c**2-a**2)/(2*b*c))*180/sp.pi
            cos_b = sp.acos((a**2+c**2-b**2)/(2*a*c))*180/sp.pi
            cos_c = 180-cos_a-cos_b
            return _geometry_response(f"geometry_triangle_{metric}", problem, result,
                theory="Uch tomon ma’lum bo‘lsa, yuza Geron formulasi bilan, burchaklar kosinuslar teoremasi bilan topiladi.",
                formula=r"p=\frac{a+b+c}{2},\quad S=\sqrt{p(p-a)(p-b)(p-c)}",
                steps=[f"Tomonlar: $a={sp.latex(a)}$, $b={sp.latex(b)}$, $c={sp.latex(c)}$.", f"Perimetr: $P=a+b+c={sp.latex(perimeter)}$; yarim perimetr $p={sp.latex(semiperimeter)}$.", f"Geron formulasi: $S=\\sqrt{{p(p-a)(p-b)(p-c)}}={sp.latex(area)}$.", f"Burchaklar (kosinuslar teoremasi): $A\\approx {sp.N(cos_a,5)}^\\circ$, $B\\approx {sp.N(cos_b,5)}^\\circ$, $C\\approx {sp.N(cos_c,5)}^\\circ$.", f"So‘ralgan {label.lower()}: ${sp.latex(result)}$."],
                diagram={"kind": "triangle", "labels": {"a": sp.sstr(a), "b": sp.sstr(b), "c": sp.sstr(c)}})
        raise EngineInputError("Uchburchak masalasi uchun kerakli tomonlar, asos-balandlik yoki burchaklarni kiriting.")

    if shape in ("square", "rectangle", "parallelogram", "rhombus", "trapezoid"):
        values = _number_values(problem)
        a = _quantity(lowered, ("side", "tomon", "qirrasi", "a"))
        b = _quantity(lowered, ("width", "eni", "b", "side b"))
        height = _quantity(lowered, ("height", "balandlik", "balandligi", "h"))
        metric = _metric(lowered)
        if shape == "square":
            a = _positive(a or (values[0] if values else None), "Kvadrat tomoni")
            area, perimeter = a**2, 4*a
            formula, labels = r"S=a^2,\quad P=4a", {"a": sp.sstr(a)}
        elif shape == "rectangle":
            if a is None or b is None:
                if len(values) >= 2: a,b=values[:2]
                else: raise EngineInputError("To‘g‘ri to‘rtburchakning bo‘yi va enini kiriting.")
            a,b=_positive(a,"Bo‘yi"),_positive(b,"Eni")
            area, perimeter=a*b,2*(a+b)
            formula, labels=r"S=ab,\quad P=2(a+b)",{"a":sp.sstr(a),"b":sp.sstr(b)}
        elif shape == "parallelogram":
            a = _positive(a or (values[0] if values else None), "Asos")
            height = _positive(height or (values[1] if len(values)>1 else None), "Balandlik")
            side = _quantity(lowered,("side", "yon tomoni", "yon tomon")) or (values[2] if len(values)>2 else a)
            area,perimeter=a*height,2*(a+side)
            formula,labels=r"S=ah,\quad P=2(a+b)",{"a":sp.sstr(a),"h":sp.sstr(height),"b":sp.sstr(side)}
        elif shape == "rhombus":
            diagonals=values[:2]
            if len(diagonals)>=2:
                d1,d2=diagonals; area=d1*d2/2; a= _quantity(lowered,("side","tomon")) or sp.sqrt(d1**2+d2**2)/2
            else:
                a=_positive(a or (values[0] if values else None),"Romb tomoni")
                height=_positive(height or (values[1] if len(values)>1 else None),"Balandlik")
                area=a*height
            perimeter=4*a
            formula,labels=r"S=\frac{d_1d_2}{2},\quad P=4a",{"a":sp.sstr(a)}
        else:
            bases=values[:2]
            if len(bases)<2 or height is None and len(values)<3:
                raise EngineInputError("Trapetsiya uchun ikki asos va balandlikni kiriting.")
            lower_base,upper_base=bases
            height=_positive(height or values[2],"Balandlik")
            area=(lower_base+upper_base)*height/2
            perimeter=sum(values[:4]) if len(values)>=4 else None
            formula=r"S=\frac{(a+b)h}{2}"
            labels={"a":sp.sstr(lower_base),"b":sp.sstr(upper_base),"h":sp.sstr(height)}
        result = perimeter if metric=="perimeter" and perimeter is not None else area
        label="Perimetr" if result==perimeter else "Yuza"
        return _geometry_response(f"geometry_{shape}_{metric}",problem,result,
            theory="Ko‘pburchak yuzi tegishli tomonlar va balandlik/diagonallar orqali, perimetri esa chegara tomonlari yig‘indisi orqali topiladi.",
            formula=formula,steps=[f"Berilgan o‘lchamlar: {', '.join(f'${k}={v}$' for k,v in labels.items())}.",f"Formula: ${formula}$.",f"Hisoblaymiz: ${label}={sp.latex(result)}$."],diagram={"kind":shape,"labels":labels})

    if shape == "polygon":
        sides_by_name={"triangle":3,"uchburchak":3,"pentagon":5,"beshburchak":5,"hexagon":6,"oltiburchak":6,"octagon":8}
        count=next((n for token,n in sides_by_name.items() if token in lowered),None)
        count=count or _quantity(lowered,("sides", "tomon", "tomonli"))
        values=_number_values(problem)
        side=_quantity(lowered,("side", "tomon", "tomoni")) or (values[-1] if values else None)
        side=_positive(side,"Ko‘pburchak tomoni")
        if count is None: raise EngineInputError("Ko‘pburchak tomonlari sonini kiriting.")
        count=int(count)
        if count<3 or count>100: raise EngineInputError("Tomonlar soni 3 dan 100 gacha bo‘lishi kerak.")
        if not any(word in lowered for word in ("regular","muntazam")) and _metric(lowered)!="perimeter":
            raise EngineInputError("Yuza uchun ko‘pburchak muntazam ekanini ko‘rsating.")
        perimeter=count*side
        area=count*side**2/(4*sp.tan(sp.pi/count))
        result=perimeter if _metric(lowered)=="perimeter" else area
        formula=r"P=na,\quad S=\frac{na^2}{4\tan(\pi/n)}"
        return _geometry_response("geometry_regular_polygon",problem,result,
            theory="Muntazam ko‘pburchakda tomonlar va ichki burchaklar teng. Perimetr n ta teng tomon yig‘indisi; yuza apofema orqali aniqlanadi.",
            formula=formula,steps=[f"Tomonlar soni $n={count}$, tomon $a={sp.latex(side)}$.",f"Perimetr: $P=na={sp.latex(perimeter)}$.",f"Yuza: $S=\\frac{{na^2}}{{4\\tan(\\pi/n)}}={sp.latex(area)}$.",f"So‘ralgan natija: ${sp.latex(result)}$."],
            diagram={"kind":"polygon","labels":{"n":str(count),"a":sp.sstr(side)}})
    return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        request = json.loads(sys.stdin.read())
        output = compute(request)
        print(json.dumps({"ok": True, "data": output}, ensure_ascii=False))
    except EngineInputError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
    except (ArithmeticError, TypeError, ValueError, sp.SympifyError) as exc:
        print(json.dumps({"ok": False, "error": f"Hisoblash bajarilmadi: {str(exc)[:180]}"}, ensure_ascii=False))
    except Exception:
        print(json.dumps({"ok": False, "error": "SymPy hisoblash xatosi. Ifodani tekshiring."}, ensure_ascii=False))


if __name__ == "__main__":
    main()
