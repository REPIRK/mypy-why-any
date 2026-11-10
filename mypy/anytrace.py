"""Provenance of Any types: where an Any was born and how it travelled.

Every AnyType carries a 'trace': a tuple of AnyStep. The first step says where and
why the Any appeared (an explicit annotation, a missing annotation, an unfollowed
import, ...). The following steps record how it propagated: a call returned it, an
attribute of it was accessed, it was assigned to a variable, and so on.

The trace is shown by reveal_any_source(expr), and as notes under Any-related errors
when --explain-any is enabled.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Final

from mypy.nodes import (
    CallExpr,
    ComparisonExpr,
    Expression,
    FuncItem,
    IndexExpr,
    MemberExpr,
    NameExpr,
    OpExpr,
    RefExpr,
    TypeAlias,
    UnaryExpr,
)
from mypy.types import (
    AnyStep,
    AnyType,
    CallableType,
    Instance,
    Type,
    TypeAliasType,
    TypeOfAny,
    get_proper_type,
)
from mypy.typetraverser import TypeTraverserVisitor

KIND_DESCRIPTIONS: Final = {
    TypeOfAny.unannotated: "missing annotation",
    TypeOfAny.explicit: "explicit 'Any'",
    TypeOfAny.from_unimported_type: "type from an unfollowed import",
    TypeOfAny.from_omitted_generics: "omitted type parameters",
    TypeOfAny.from_error: "type error",
    TypeOfAny.special_form: "special form not expressible in the type system",
    TypeOfAny.from_another_any: "another Any",
    TypeOfAny.implementation_artifact: "mypy implementation limitation",
    TypeOfAny.suggestion_engine: "suggestion engine",
}


def root_any(t: AnyType) -> AnyType:
    return t.source_any if t.source_any is not None else t


def describe_birth(t: AnyType, what: str | None = None) -> str:
    """Describe why an Any appeared; 'what' names the place, e.g. 'parameter "x" of "f"'."""
    root = root_any(t)
    kind = root.type_of_any
    where = f" in {what}" if what else ""
    if kind == TypeOfAny.explicit:
        return f"explicit 'Any'{where}"
    if kind == TypeOfAny.unannotated:
        return f"missing annotation for {what}" if what else "unannotated code"
    if kind == TypeOfAny.from_unimported_type:
        name = root.missing_import_name
        source = f'"{name}"' if name else "a name"
        return f"{source} comes from a module that is not followed or not installed{where}"
    if kind == TypeOfAny.from_omitted_generics:
        return f"omitted type parameters{where}"
    if kind == TypeOfAny.from_error:
        return f"a type error{where}"
    return KIND_DESCRIPTIONS.get(kind, "unknown reason") + where


def birth_step(t: AnyType, module: str | None, line: int, what: str | None = None) -> AnyStep:
    if t.line >= 0:
        line = t.line
    return AnyStep(describe_birth(t, what), module, line)


def with_origin(t: AnyType, module: str | None, line: int) -> AnyType:
    """Keep the reason for an untraced Any before adding propagation steps."""
    if t.trace:
        return t
    result = t.copy_modified()
    result.trace = (birth_step(t, module, line),)
    return result


class _OriginRecorder(TypeTraverserVisitor):
    """Give every Any inside a freshly analyzed type a birth step, if it has none.

    This mutates AnyType objects in place: they were just created by type analysis,
    so the first place that sees them is where they were born.
    """

    def __init__(self, module: str | None, line: int, what: str | None) -> None:
        super().__init__()
        self.module = module
        self.line = line
        self.what = what

    def visit_any(self, t: AnyType, /) -> None:
        if not t.trace:
            t.trace = (birth_step(t, self.module, self.line, self.what),)

    def visit_instance(self, t: Instance, /) -> None:
        for arg in t.args:
            p = get_proper_type(arg)
            if (
                isinstance(p, AnyType)
                and not p.trace
                and p.type_of_any == TypeOfAny.from_omitted_generics
            ):
                what = f'"{t.type.name}"' + (f" in {self.what}" if self.what else "")
                line = t.line if t.line >= 0 else self.line
                p.trace = (AnyStep(f"missing type parameters for {what}", self.module, line),)
        super().visit_instance(t)


class _AnyCollector(TypeTraverserVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[AnyType] = []
        self.active_aliases: set[TypeAlias] = set()

    def visit_any(self, t: AnyType, /) -> None:
        if not any(t is f for f in self.found):
            self.found.append(t)

    def visit_type_alias_type(self, t: TypeAliasType, /) -> None:
        # Expand aliases with their actual arguments, stopping at recursive references.
        if t.alias is None or t.alias in self.active_aliases:
            return
        self.active_aliases.add(t.alias)
        get_proper_type(t).accept(self)
        self.active_aliases.remove(t.alias)


def collect_any_types(typ: Type) -> list[AnyType]:
    """All Any types inside a type, in order of appearance."""
    collector = _AnyCollector()
    typ.accept(collector)
    return collector.found


def record_origins(typ: Type, module: str | None, line: int, what: str | None = None) -> None:
    typ.accept(_OriginRecorder(module, line, what))


def record_signature_origins(sig: CallableType, defn: FuncItem, module: str | None) -> None:
    """Record birth steps for the Anys in a function signature, naming the parameter."""
    fname = f'"{defn.name}"'
    for name, arg_type in zip(sig.arg_names, sig.arg_types):
        what = f'parameter "{name}" of {fname}' if name else f"a parameter of {fname}"
        record_origins(arg_type, module, defn.line, what)
    record_origins(sig.ret_type, module, defn.line, f"return type of {fname}")


def record_unannotated_function(sig: CallableType, defn: FuncItem) -> CallableType:
    """Birth steps for a function that has no annotations at all (see callable_type())."""
    module = defn.fullname or None
    fname = f'"{defn.name}"'
    args: list[Type] = []
    for name, arg_type in zip(sig.arg_names, sig.arg_types):
        p = get_proper_type(arg_type)
        if isinstance(p, AnyType) and not p.trace:
            what = f'parameter "{name}" of {fname}' if name else f"a parameter of {fname}"
            arg_type = p.with_step(AnyStep(f"missing annotation for {what}", module, defn.line))
        args.append(arg_type)
    ret = sig.ret_type
    p = get_proper_type(ret)
    if isinstance(p, AnyType) and not p.trace:
        ret = p.with_step(AnyStep(f"missing return annotation of {fname}", module, defn.line))
    return sig.copy_modified(arg_types=args, ret_type=ret)


def short_expr(e: Expression, limit: int = 40) -> str:
    """A compact source-like rendering of an expression for trace messages."""
    text = _render(e, depth=0)
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def _render(e: Expression, depth: int) -> str:
    if depth > 4:
        return "..."
    if isinstance(e, NameExpr):
        return e.name
    if isinstance(e, MemberExpr):
        return f"{_render(e.expr, depth + 1)}.{e.name}"
    if isinstance(e, CallExpr):
        return (
            f"{_render(e.callee, depth + 1)}(...)"
            if e.args
            else f"{_render(e.callee, depth + 1)}()"
        )
    if isinstance(e, IndexExpr):
        return f"{_render(e.base, depth + 1)}[...]"
    if isinstance(e, OpExpr):
        return f"{_render(e.left, depth + 1)} {e.op} {_render(e.right, depth + 1)}"
    if isinstance(e, UnaryExpr):
        return f"{e.op}{_render(e.expr, depth + 1)}"
    return "<expr>"


def callee_name(e: CallExpr) -> str:
    callee = e.callee
    if isinstance(callee, RefExpr) and callee.fullname and isinstance(callee, NameExpr):
        return callee.fullname
    return short_expr(callee)


def describe_expression_step(e: Expression, base_is_any: bool) -> str | None:
    """Message for an expression whose value is Any, or None if it adds nothing."""
    if isinstance(e, CallExpr):
        if base_is_any:
            return f'call of an Any value "{short_expr(e)}"'
        return f'returned by "{short_expr(e)}"'
    if isinstance(e, MemberExpr):
        if base_is_any:
            return f'attribute "{e.name}" of an Any value ("{short_expr(e)}")'
        return f'attribute "{short_expr(e)}"'
    if isinstance(e, IndexExpr):
        if base_is_any:
            return f'indexing an Any value ("{short_expr(e)}")'
        return f'item "{short_expr(e)}"'
    if isinstance(e, (OpExpr, ComparisonExpr, UnaryExpr)):
        return f'operation "{short_expr(e)}"'
    return None


def short_display_path(path: str) -> str:
    """Path relative to the current directory, or from 'typeshed' for bundled stubs."""
    norm = path.replace("\\", "/")
    marker = norm.rfind("/typeshed/")
    if marker >= 0:
        return norm[marker + 1 :]
    try:
        rel = os.path.relpath(path)
    except ValueError:  # Different drive on Windows
        return path
    return path if rel.startswith("..") else rel


def format_trace(
    t: AnyType, resolve: Callable[[str | None], str | None], current_path: str
) -> list[str]:
    """Render the trace of an Any as note lines, most recent step last."""
    steps: Iterable[AnyStep] = t.trace
    lines: list[str] = []
    if not t.trace:
        lines.append(f"Any comes from {describe_birth(t)} (origin not recorded)")
        return lines
    for i, step in enumerate(steps):
        path = resolve(step.module) or "?"
        loc = f"{path}:{step.line}" if step.line >= 0 else path
        if path == current_path and step.line >= 0:
            loc = f"line {step.line}"
        prefix = "Any comes from " if i == 0 else "  -> "
        lines.append(f"{prefix}{step.message} ({loc})")
    return lines
