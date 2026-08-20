from __future__ import annotations

import copy
from abc import ABC

from . import dsl_nodes


class DSLParseError(ValueError):
    """Actionable syntax error for externally supplied DSL source."""

    def __init__(
        self,
        construct: str,
        offset: int,
        expected: str,
        actual: str | None,
        tokens: list[str],
    ) -> None:
        self.construct = construct
        self.offset = offset
        self.expected = expected
        self.actual = actual
        start = max(0, offset - 3)
        end = min(len(tokens), offset + 4)
        self.context = " ".join(tokens[start:end]) or "<empty>"
        self.token_window = self.context
        received = "end of input" if actual is None else f"`{actual}`"
        message = (
            f"DSL parse error in {construct} at token {offset}: expected {expected}; "
            f"actual {received}; context `{self.context}`"
        )
        if expected == "known DSL symbol" and actual is not None:
            message = f"Unrecognized token: {actual}. {message}"
        super().__init__(message)


def _parse_error(
    construct: str, offset: int, expected: str, tokens: list[str]
) -> DSLParseError:
    return DSLParseError(
        construct, offset, expected, tokens[offset] if offset < len(tokens) else None, tokens
    )


_OPEN_TO_CLOSE = {
    "m(": "m)", "c(": "c)", "w(": "w)", "i(": "i)",
    "e(": "e)", "r(": "r)", "h(": "h)",
}
_CLOSE_TOKENS = set(_OPEN_TO_CLOSE.values())


def _matching_close(tokens: list[str], start: int) -> int:
    opener = tokens[start]
    expected = _OPEN_TO_CLOSE[opener]
    depth = 0
    for offset in range(start, len(tokens)):
        if tokens[offset] == opener:
            depth += 1
        elif tokens[offset] == expected:
            depth -= 1
            if depth == 0:
                return offset
    raise AssertionError("tokens were balanced before matching delimiters")


def _validate_boolean_expression(tokens: list[str], start: int, end: int) -> None:
    """Validate that tokens[start:end] is exactly one complete boolean expression.

    Structural delimiter balancing alone accepts a trailing token stranded
    between a nested `not`/`and`/`or` expression's own close and the
    enclosing condition's close (e.g. `not c( x c) x c)`); this walks the
    boolean grammar explicitly so that span is required to line up.
    """
    if start >= end:
        raise DSLParseError(
            "boolean expression", start, "a boolean expression",
            tokens[start] if start < len(tokens) else None, tokens,
        )
    token = tokens[start]
    if token in {"not", "and", "or"}:
        if start + 1 >= end or tokens[start + 1] != "c(":
            raise _parse_error(token, start + 1, "`c(`", tokens)
        c1_close = _matching_close(tokens, start + 1)
        if c1_close >= end:
            raise _parse_error(token, end, "`c)`", tokens)
        _validate_boolean_expression(tokens, start + 2, c1_close)
        if token == "not":
            next_offset = c1_close + 1
        else:
            if c1_close + 1 >= end or tokens[c1_close + 1] != "c(":
                raise _parse_error(token, c1_close + 1, "`c(`", tokens)
            c2_close = _matching_close(tokens, c1_close + 1)
            if c2_close >= end:
                raise _parse_error(token, end, "`c)`", tokens)
            _validate_boolean_expression(tokens, c1_close + 2, c2_close)
            next_offset = c2_close + 1
        if next_offset != end:
            raise _parse_error(token, next_offset, "`c)`", tokens)
        return
    if end - start == 1:
        return
    if start + 1 < end and tokens[start + 1] == "h(":
        h_close = _matching_close(tokens, start + 1)
        if h_close + 1 == end:
            return
        raise _parse_error(token, h_close + 1, "`c)`", tokens)
    raise _parse_error("boolean expression", start + 1, "`c)`", tokens)


def token_is_repeat_count(token: str) -> bool:
    if not token.startswith("R="):
        return False
    try:
        return 0 <= int(token[2:]) <= 19
    except ValueError:
        return False

class BaseDSL(ABC):

    def __init__(self, nodes_list: list[dsl_nodes.BaseNode] = None):
        self.nodes_list = nodes_list
        self.tokens_list = self.convert_nodes_to_tokens_list(self.nodes_list)
        self.t2i = {token: i for i, token in enumerate(self.tokens_list)}
        self.i2t = {i: token for i, token in enumerate(self.tokens_list)}
        self.actions = [n.name for n in self.nodes_list if isinstance(n, dsl_nodes.Action)]
        self.bool_features = [n.name for n in self.nodes_list if isinstance(n, dsl_nodes.BoolFeature)]
        self.int_features = [n.name for n in self.nodes_list if isinstance(n, dsl_nodes.IntFeature)]
    
    @property
    def prod_rules(self) -> dict[type[dsl_nodes.BaseNode], list[list[type[dsl_nodes.BaseNode]]]]:
        statements = [dsl_nodes.While, dsl_nodes.Repeat, dsl_nodes.If, dsl_nodes.ITE,
                      dsl_nodes.Concatenate, dsl_nodes.Action]
        booleans = [dsl_nodes.BoolFeature, dsl_nodes.Not, dsl_nodes.And, dsl_nodes.Or,
                    dsl_nodes.ConstBool]
        statements_without_concat = [dsl_nodes.While, dsl_nodes.Repeat, dsl_nodes.If,
                                     dsl_nodes.ITE, dsl_nodes.Action]
        booleans_without_not = [dsl_nodes.BoolFeature, dsl_nodes.And, dsl_nodes.Or,
                                dsl_nodes.ConstBool]
        return {
            dsl_nodes.Program: [statements],
            dsl_nodes.While: [booleans, statements],
            dsl_nodes.Repeat: [[dsl_nodes.ConstInt], statements],
            dsl_nodes.If: [booleans, statements],
            dsl_nodes.ITE: [booleans_without_not, statements, statements],
            dsl_nodes.Concatenate: [statements_without_concat, statements],
            dsl_nodes.Not: [booleans_without_not],
            dsl_nodes.And: [booleans, booleans],
            dsl_nodes.Or: [booleans, booleans]
        }

    def get_dsl_nodes_probs(self, node_type: type[dsl_nodes.BaseNode]) -> dict[dsl_nodes.BaseNode, float]:
        return {}
    
    @property
    def action_probs(self) -> dict[str, float]:
        return {}
    
    @property
    def bool_feat_probs(self) -> dict[str, float]:
        return {}
    
    @property
    def int_feat_probs(self) -> dict[str, float]:
        return {}
    
    @property
    def const_bool_probs(self) -> dict[bool, float]:
        return {}
    
    @property
    def const_int_probs(self) -> dict[int, float]:
        return {}
    
    def structure_only(self):
        structure_nodes = [n for n in self.nodes_list if not isinstance(n, dsl_nodes.BoolFeature)
                        and not isinstance(n, dsl_nodes.IntFeature)
                        and not isinstance(n, dsl_nodes.Action)
                        and not isinstance(n, dsl_nodes.ConstInt)
                        and not isinstance(n, dsl_nodes.ConstBool)] + [None]
        return BaseDSL(structure_nodes)
        
    def extend_dsl(self):
        extended_dsl = copy.deepcopy(self)
        extended_dsl.nodes_list.append(None)
        extended_dsl.tokens_list.append('<HOLE>')
        return extended_dsl

    def get_actions(self) -> list[dsl_nodes.BaseNode]:
        return self.actions
    
    def get_bool_features(self) -> list[dsl_nodes.BaseNode]:
        return self.bool_features
    
    def get_int_features(self) -> list[dsl_nodes.BaseNode]:
        return self.int_features

    def get_tokens(self) -> list[str]:
        return self.tokens_list
    
    # Note: the parse and convert methods use the formatting that LEAPS uses for Karel environment.
    # If you want to use a different formatting, you should override these methods.
    def convert_nodes_to_tokens_list(self, nodes_list: list[dsl_nodes.BaseNode]) -> list[str]:
        tokens_list = ['DEF', 'run', 'm(', 'm)']
        for node in nodes_list:
            if node is None:
                tokens_list += ['<HOLE>']

            if isinstance(node, dsl_nodes.ConstInt):
                tokens_list += ['R=' + str(node.value)]
            if isinstance(node, dsl_nodes.ConstBool):
                tokens_list += [str(node.value)]
            if isinstance(node, dsl_nodes.Action) \
                or isinstance(node, dsl_nodes.BoolFeature) \
                or isinstance(node, dsl_nodes.IntFeature):
                tokens_list += [node.name]

            if isinstance(node, dsl_nodes.While):
                tokens_list += ['WHILE', 'c(', 'c)', 'w(', 'w)']
            if isinstance(node, dsl_nodes.Repeat):
                tokens_list += ['REPEAT', 'r(', 'r)']
            if isinstance(node, dsl_nodes.If):
                tokens_list += ['IF', 'c(', 'c)', 'i(', 'i)']
            if isinstance(node, dsl_nodes.ITE):
                tokens_list += ['IFELSE', 'c(', 'c)', 'i(', 'i)', 'ELSE', 'e(', 'e)']
            if isinstance(node, dsl_nodes.Concatenate):
                tokens_list += []

            if isinstance(node, dsl_nodes.Not):
                tokens_list += ['not', 'c(', 'c)']
            if isinstance(node, dsl_nodes.And):
                tokens_list += ['and', 'c(', 'c)']
            if isinstance(node, dsl_nodes.Or):
                tokens_list += ['or', 'c(', 'c)']

        tokens_list += ['<pad>']
        return list(dict.fromkeys(tokens_list)) # Remove duplicates

    def parse_node_to_str(self, node: dsl_nodes.BaseNode) -> str:
        if node is None:
            return '<HOLE>'
        
        if isinstance(node, dsl_nodes.ConstInt):
            return 'R=' + str(node.value)
        if isinstance(node, dsl_nodes.ConstBool):
            return str(node.value)
        if isinstance(node, dsl_nodes.Action) \
            or isinstance(node, dsl_nodes.BoolFeature) \
            or isinstance(node, dsl_nodes.IntFeature):
            return node.name

        if isinstance(node, dsl_nodes.Program):
            m = self.parse_node_to_str(node.children[0])
            return f'DEF run m( {m} m)'

        if isinstance(node, dsl_nodes.While):
            c = self.parse_node_to_str(node.children[0])
            w = self.parse_node_to_str(node.children[1])
            return f'WHILE c( {c} c) w( {w} w)'
        if isinstance(node, dsl_nodes.Repeat):
            n = self.parse_node_to_str(node.children[0])
            r = self.parse_node_to_str(node.children[1])
            return f'REPEAT {n} r( {r} r)'
        if isinstance(node, dsl_nodes.If):
            c = self.parse_node_to_str(node.children[0])
            i = self.parse_node_to_str(node.children[1])
            return f'IF c( {c} c) i( {i} i)'
        if isinstance(node, dsl_nodes.ITE):
            c = self.parse_node_to_str(node.children[0])
            i = self.parse_node_to_str(node.children[1])
            e = self.parse_node_to_str(node.children[2])
            return f'IFELSE c( {c} c) i( {i} i) ELSE e( {e} e)'
        if isinstance(node, dsl_nodes.Concatenate):
            s1 = self.parse_node_to_str(node.children[0])
            s2 = self.parse_node_to_str(node.children[1])
            return f'{s1} {s2}'

        if isinstance(node, dsl_nodes.Not):
            c = self.parse_node_to_str(node.children[0])
            return f'not c( {c} c)'
        if isinstance(node, dsl_nodes.And):
            c1 = self.parse_node_to_str(node.children[0])
            c2 = self.parse_node_to_str(node.children[1])
            return f'and c( {c1} c) c( {c2} c)'
        if isinstance(node, dsl_nodes.Or):
            c1 = self.parse_node_to_str(node.children[0])
            c2 = self.parse_node_to_str(node.children[1])
            return f'or c( {c1} c) c( {c2} c)'
        
        raise Exception(f'Unknown node type: {type(node)}')
    
    def _parse_bool_feature(self, prog_str_list: list[str]) -> tuple[dsl_nodes.BaseNode, int]:
        """Parse the bool-feature leaf at the start of prog_str_list.

        Returns the parsed node and how many leading tokens it consumed.
        Dialects with multi-token feature arguments (e.g. `h( ... h)`)
        override this instead of duplicating the whole parse dispatch.
        """
        return dsl_nodes.BoolFeature(prog_str_list[0]), 1

    def parse_str_list_to_node(self, prog_str_list: list[str]) -> dsl_nodes.BaseNode:
        # if len(prog_str_list) == 0:
        #     return EmptyStatement()
        
        if prog_str_list[0] in self.actions:
            if len(prog_str_list) > 1:
                s1 = dsl_nodes.Action(prog_str_list[0])
                s2 = self.parse_str_list_to_node(prog_str_list[1:])
                return dsl_nodes.Concatenate.new(s1, s2)
            return dsl_nodes.Action(prog_str_list[0])
        
        if prog_str_list[0] in self.bool_features:
            node, consumed = self._parse_bool_feature(prog_str_list)
            if consumed < len(prog_str_list):
                s2 = self.parse_str_list_to_node(prog_str_list[consumed:])
                return dsl_nodes.Concatenate.new(node, s2)
            return node
        
        if prog_str_list[0] in self.int_features:
            if len(prog_str_list) > 1:
                s1 = dsl_nodes.IntFeature(prog_str_list[0])
                s2 = self.parse_str_list_to_node(prog_str_list[1:])
                return dsl_nodes.Concatenate.new(s1, s2)
            return dsl_nodes.IntFeature(prog_str_list[0])
        
        if prog_str_list[0] == '<HOLE>':
            if len(prog_str_list) > 1:
                s1 = None
                s2 = self.parse_str_list_to_node(prog_str_list[1:])
                return dsl_nodes.Concatenate.new(s1, s2)
            return None
        
        if prog_str_list[0] == 'DEF':
            assert prog_str_list[1] == 'run', 'Invalid program'
            assert prog_str_list[2] == 'm(', 'Invalid program'
            assert prog_str_list[-1] == 'm)', 'Invalid program'
            m = self.parse_str_list_to_node(prog_str_list[3:-1])
            return dsl_nodes.Program.new(m)
        
        elif prog_str_list[0] == 'IF':
            c_end = _matching_close(prog_str_list, 1)
            i_end = _matching_close(prog_str_list, c_end+1)
            c = self.parse_str_list_to_node(prog_str_list[2:c_end])
            i = self.parse_str_list_to_node(prog_str_list[c_end+2:i_end])
            if i_end == len(prog_str_list) - 1: 
                return dsl_nodes.If.new(c, i)
            else:
                return dsl_nodes.Concatenate.new(
                    dsl_nodes.If.new(c, i), 
                    self.parse_str_list_to_node(prog_str_list[i_end+1:])
                )
        elif prog_str_list[0] == 'IFELSE':
            c_end = _matching_close(prog_str_list, 1)
            i_end = _matching_close(prog_str_list, c_end+1)
            assert prog_str_list[i_end+1] == 'ELSE', 'Invalid program'
            e_end = _matching_close(prog_str_list, i_end+2)
            c = self.parse_str_list_to_node(prog_str_list[2:c_end])
            i = self.parse_str_list_to_node(prog_str_list[c_end+2:i_end])
            e = self.parse_str_list_to_node(prog_str_list[i_end+3:e_end])
            if e_end == len(prog_str_list) - 1: 
                return dsl_nodes.ITE.new(c, i, e)
            else:
                return dsl_nodes.Concatenate.new(
                    dsl_nodes.ITE.new(c, i, e),
                    self.parse_str_list_to_node(prog_str_list[e_end+1:])
                )
        elif prog_str_list[0] == 'WHILE':
            c_end = _matching_close(prog_str_list, 1)
            w_end = _matching_close(prog_str_list, c_end+1)
            c = self.parse_str_list_to_node(prog_str_list[2:c_end])
            w = self.parse_str_list_to_node(prog_str_list[c_end+2:w_end])
            if w_end == len(prog_str_list) - 1: 
                return dsl_nodes.While.new(c, w)
            else:
                return dsl_nodes.Concatenate.new(
                    dsl_nodes.While.new(c, w),
                    self.parse_str_list_to_node(prog_str_list[w_end+1:])
                )
        elif prog_str_list[0] == 'REPEAT':
            n = self.parse_str_list_to_node([prog_str_list[1]])
            r_end = _matching_close(prog_str_list, 2)
            r = self.parse_str_list_to_node(prog_str_list[3:r_end])
            if r_end == len(prog_str_list) - 1: 
                return dsl_nodes.Repeat.new(n, r)
            else:
                return dsl_nodes.Concatenate.new(
                    dsl_nodes.Repeat.new(n, r),
                    self.parse_str_list_to_node(prog_str_list[r_end+1:])
                )
        
        elif prog_str_list[0] == 'not':
            assert prog_str_list[1] == 'c(', 'Invalid program'
            assert prog_str_list[-1] == 'c)', 'Invalid program'
            c = self.parse_str_list_to_node(prog_str_list[2:-1])
            return dsl_nodes.Not.new(c)
        elif prog_str_list[0] == 'and':
            c1_end = _matching_close(prog_str_list, 1)
            assert prog_str_list[c1_end+1] == 'c(', 'Invalid program'
            assert prog_str_list[-1] == 'c)', 'Invalid program'
            c1 = self.parse_str_list_to_node(prog_str_list[2:c1_end])
            c2 = self.parse_str_list_to_node(prog_str_list[c1_end+2:-1])
            return dsl_nodes.And.new(c1, c2)
        elif prog_str_list[0] == 'or':
            c1_end = _matching_close(prog_str_list, 1)
            assert prog_str_list[c1_end+1] == 'c(', 'Invalid program'
            assert prog_str_list[-1] == 'c)', 'Invalid program'
            c1 = self.parse_str_list_to_node(prog_str_list[2:c1_end])
            c2 = self.parse_str_list_to_node(prog_str_list[c1_end+2:-1])
            return dsl_nodes.Or.new(c1, c2)

        elif prog_str_list[0].startswith('R='):
            num = int(prog_str_list[0].replace('R=', ''))
            assert num is not None
            return dsl_nodes.ConstInt(num)
        elif prog_str_list[0] in ['True', 'False']:
            return dsl_nodes.ConstBool(prog_str_list[0] == 'True')
        else:
            raise ValueError(f'Unrecognized token: {prog_str_list[0]}.')
    
    # The following methods should not be overridden even if using a different formatting logic
    def parse_str_to_node(self, prog_str: str) -> dsl_nodes.BaseNode:
        tokens = prog_str.split()
        self._validate_external_tokens(tokens)
        try:
            return self.parse_str_list_to_node(tokens)
        except DSLParseError:
            raise
        except (AssertionError, IndexError, KeyError, TypeError, ValueError) as error:
            raise DSLParseError(
                "program", 0, "valid DSL structure", None, tokens
            ) from error

    def _validate_external_tokens(self, tokens: list[str]) -> None:
        if not tokens:
            raise _parse_error("program wrapper", 0, "`DEF`", tokens)
        if tokens[0] != "DEF":
            raise _parse_error("program wrapper", 0, "`DEF`", tokens)
        for offset, expected in ((1, "`run`"), (2, "`m(`")):
            if offset >= len(tokens) or tokens[offset] != expected.strip("`"):
                raise _parse_error("program wrapper", offset, expected, tokens)
        if len(tokens) == 3:
            raise _parse_error("program wrapper", 3, "a statement", tokens)

        self._validate_dialect_tokens(tokens)

        stack: list[tuple[str, int]] = []
        for offset, token in enumerate(tokens):
            if token in _OPEN_TO_CLOSE:
                stack.append((token, offset))
                continue
            if token in _CLOSE_TOKENS:
                if not stack:
                    raise _parse_error("delimiter", offset, "opening delimiter", tokens)
                opener, _ = stack.pop()
                expected = _OPEN_TO_CLOSE[opener]
                if token != expected:
                    raise _parse_error("delimiter", offset, f"`{expected}`", tokens)

        if stack:
            opener, offset = stack[-1]
            raise DSLParseError(
                "delimiter", len(tokens), f"`{_OPEN_TO_CLOSE[opener]}`", None, tokens
            )
        if tokens[-1] != "m)":
            raise _parse_error("program wrapper", len(tokens) - 1, "final `m)`", tokens)

        valid_else_offsets: set[int] = set()
        for offset, token in enumerate(tokens):
            if token in {"IF", "IFELSE", "WHILE"}:
                if offset + 1 >= len(tokens) or tokens[offset + 1] != "c(":
                    raise _parse_error(token, offset + 1, "`c(`", tokens)
                c_close = _matching_close(tokens, offset + 1)
                _validate_boolean_expression(tokens, offset + 2, c_close)
                if token in {"IF", "IFELSE"}:
                    if c_close + 1 >= len(tokens) or tokens[c_close + 1] != "i(":
                        raise _parse_error(token, c_close + 1, "`i(`", tokens)
                    i_close = _matching_close(tokens, c_close + 1)
                    if token == "IFELSE":
                        if i_close + 1 >= len(tokens) or tokens[i_close + 1] != "ELSE":
                            raise _parse_error("IFELSE", i_close + 1, "`ELSE`", tokens)
                        valid_else_offsets.add(i_close + 1)
                        if i_close + 2 >= len(tokens) or tokens[i_close + 2] != "e(":
                            raise _parse_error("ELSE", i_close + 2, "`e(`", tokens)
                elif token == "WHILE":
                    if c_close + 1 >= len(tokens) or tokens[c_close + 1] != "w(":
                        raise _parse_error("WHILE", c_close + 1, "`w(`", tokens)
            elif token == "REPEAT":
                if offset + 1 >= len(tokens) or not token_is_repeat_count(tokens[offset + 1]):
                    raise _parse_error("REPEAT", offset + 1, "`R=<0-19>`", tokens)
                if offset + 2 >= len(tokens) or tokens[offset + 2] != "r(":
                    raise _parse_error("REPEAT", offset + 2, "`r(`", tokens)
            elif token == "ELSE":
                if offset not in valid_else_offsets:
                    raise _parse_error("statement", offset, "a DSL statement", tokens)
                if offset + 1 >= len(tokens) or tokens[offset + 1] != "e(":
                    raise _parse_error("ELSE", offset + 1, "`e(`", tokens)
        known = self._known_external_tokens()
        for offset, token in enumerate(tokens):
            if token.startswith("R=") and not token_is_repeat_count(token):
                raise _parse_error("REPEAT", offset, "`R=<0-19>`", tokens)
            if token not in known:
                raise DSLParseError(
                    "program", offset, "known DSL symbol", token, tokens
                )

    def _validate_dialect_tokens(self, tokens: list[str]) -> None:
        _ = tokens

    def _known_external_tokens(self) -> set[str]:
        return set(self.tokens_list)
    def parse_node_to_int(self, node: dsl_nodes.BaseNode) -> list[int]:
        prog_str = self.parse_node_to_str(node)
        return self.parse_str_to_int(prog_str)
    
    def parse_int_to_node(self, prog_tokens: list[int]) -> dsl_nodes.BaseNode:
        prog_str = self.parse_int_to_str(prog_tokens)
        return self.parse_str_to_node(prog_str)
    
    def parse_int_to_str(self, prog_tokens: list[int]) -> str:
        token_list = [self.i2t[i] for i in prog_tokens]
        return ' '.join(token_list)
    
    def parse_str_to_int(self, prog_str: str) -> list[int]:
        prog_str_list = prog_str.split(' ')
        return [self.t2i[i] for i in prog_str_list]
