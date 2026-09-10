from __future__ import annotations

import ast
import operator
import re
from decimal import Decimal, DivisionByZero, InvalidOperation, getcontext

import discord
from discord.ext import commands

from cogs.admin_command_utils import create_error_splash


getcontext().prec = 50


class SafeMathEvaluator:
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
    }
    UNARY_OPERATORS = {
        ast.UAdd: lambda value: value,
        ast.USub: lambda value: -value,
    }
    NUMBER_PATTERN = re.compile(r"(?<![\w.])\d[\d.,]*(?![\w.])")

    @classmethod
    def normalize_number(cls, token: str) -> str:
        if "," in token and "." in token:
            if token.rfind(",") > token.rfind("."):
                normalized = token.replace(".", "").replace(",", ".")
            else:
                normalized = token.replace(",", "")
            return normalized

        if "," in token:
            parts = token.split(",")
            if len(parts) > 2:
                return token.replace(",", "")
            if len(parts[-1]) == 3 and len(parts[0]) >= 1:
                return token.replace(",", "")
            return token.replace(",", ".")

        if "." in token:
            parts = token.split(".")
            if len(parts) > 2:
                return token.replace(".", "")
            if len(parts[-1]) == 3 and len(parts[0]) >= 1:
                return token.replace(".", "")
            return token

        return token

    @classmethod
    def normalize_expression(cls, expression: str) -> str:
        cleaned = expression.strip()
        cleaned = cleaned.replace("×", "*").replace("x", "*").replace("X", "*")
        cleaned = cleaned.replace("÷", "/").replace(":", "/")
        cleaned = cleaned.replace("^", "**")
        cleaned = cls.NUMBER_PATTERN.sub(lambda match: cls.normalize_number(match.group(0)), cleaned)
        if not re.fullmatch(r"[\d\s+\-*/().]*", cleaned):
            raise ValueError("Biểu thức chỉ được dùng số và các dấu `+ - * / ^ ( )`.")
        return cleaned

    @classmethod
    def evaluate(cls, expression: str) -> Decimal:
        normalized = cls.normalize_expression(expression)
        try:
            tree = ast.parse(normalized, mode="eval")
        except SyntaxError as exc:
            raise ValueError("Biểu thức không hợp lệ.") from exc
        return cls._eval_node(tree.body)

    @classmethod
    def _eval_node(cls, node: ast.AST) -> Decimal:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))

        if isinstance(node, ast.UnaryOp) and type(node.op) in cls.UNARY_OPERATORS:
            return cls.UNARY_OPERATORS[type(node.op)](cls._eval_node(node.operand))

        if isinstance(node, ast.BinOp) and type(node.op) in cls.OPERATORS:
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ValueError("Không thể chia cho 0.")
            if isinstance(node.op, ast.Pow):
                if right != right.to_integral_value():
                    raise ValueError("Số mũ phải là số nguyên.")
                if abs(int(right)) > 12:
                    raise ValueError("Số mũ quá lớn, giới hạn trong khoảng `-12` đến `12`.")
            try:
                return Decimal(str(cls.OPERATORS[type(node.op)](left, right)))
            except (InvalidOperation, DivisionByZero, OverflowError) as exc:
                raise ValueError("Kết quả vượt giới hạn tính toán.") from exc

        raise ValueError("Biểu thức có thành phần không được hỗ trợ.")


def format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{int(value):,}"

    text = format(value.normalize(), "f").rstrip("0").rstrip(".")
    sign = ""
    if text.startswith("-"):
        sign = "-"
        text = text[1:]
    integer_part, decimal_part = text.split(".", 1)
    return f"{sign}{int(integer_part):,}.{decimal_part}"


class MathCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="math", aliases=["calc", "tinh", "tính"])
    async def math(self, ctx, *, expression: str = None):
        if not expression:
            await ctx.reply(
                embed=create_error_splash("❌ Thiếu Biểu Thức", "Dùng: `math 120+520` hoặc `math 100.000 + 50,000`."),
                mention_author=False,
            )
            return

        try:
            result = SafeMathEvaluator.evaluate(expression)
        except ValueError as exc:
            await ctx.reply(embed=create_error_splash("❌ Math Lỗi", str(exc)), mention_author=False)
            return

        await ctx.reply(f"Kết quả của {expression}={format_decimal(result)}.", mention_author=False)


async def setup(bot):
    await bot.add_cog(MathCog(bot))
