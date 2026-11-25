import ast
import json
import operator
import re
import sys
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext

MAX_INPUT_BYTES = 2048
MAX_EXPRESSION_LENGTH = 160
MAX_DEPTH = 16
ALLOWED_EXPRESSION = re.compile(r"[0-9+*/(). \t-]+")
BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def evaluate(node: ast.expr, expression: str, depth: int = 0) -> Decimal:
    if depth > MAX_DEPTH:
        raise ValueError("表达式嵌套过深")
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Decimal(expression[node.col_offset : node.end_col_offset])
    if isinstance(node, ast.BinOp) and (
        binary_operation := BINARY_OPERATORS.get(type(node.op))
    ):
        left = evaluate(node.left, expression, depth + 1)
        right = evaluate(node.right, expression, depth + 1)
        if isinstance(node.op, ast.Div) and not right:
            raise ValueError("除数不能为零")
        return binary_operation(left, right)
    if isinstance(node, ast.UnaryOp) and (
        unary_operation := UNARY_OPERATORS.get(type(node.op))
    ):
        return unary_operation(evaluate(node.operand, expression, depth + 1))
    raise ValueError("仅支持十进制数字、括号和四则运算")


def calculate(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("expression"), str):
        raise ValueError("请填写 expression 字符串")
    if payload.keys() != {"expression"}:
        raise ValueError("仅接受 expression 字段")
    expression = payload["expression"].strip()
    if not 1 <= len(expression) <= MAX_EXPRESSION_LENGTH:
        raise ValueError("表达式长度须为 1–160 个字符")
    if not ALLOWED_EXPRESSION.fullmatch(expression):
        raise ValueError("仅支持十进制数字、括号和四则运算")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("表达式格式无效，请检查数字、括号和运算符") from exc
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        try:
            value = +evaluate(tree.body, expression)
        except DecimalException as exc:
            raise ValueError("无法完成该十进制运算") from exc
    result = format(value, "f") if value else "0"
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return {"expression": expression, "result": result}


def main() -> int:
    try:
        raw_input = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw_input) > MAX_INPUT_BYTES:
            raise ValueError("输入超出大小限制")
        try:
            payload = json.loads(raw_input.decode("utf-8"))
        except (ValueError, RecursionError) as exc:
            raise ValueError("请输入一个 UTF-8 JSON 对象") from exc
        result = calculate(payload)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
