from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from novel_world.modules.stscript.lexer import tokenize


@dataclass
class STScope:
    global_vars: dict[str, str] = field(default_factory=dict)
    local_vars: dict[str, str] = field(default_factory=dict)
    chat_vars: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        key = name.strip().lower()
        if key in self.local_vars:
            return self.local_vars[key]
        if key in self.chat_vars:
            return self.chat_vars[key]
        return self.global_vars.get(key, "")

    def set(self, name: str, value: str, *, scope: str = "local") -> None:
        key = name.strip().lower()
        if scope == "global":
            self.global_vars[key] = value
        elif scope == "chat":
            self.chat_vars[key] = value
        else:
            self.local_vars[key] = value


class STScriptRuntime:
    def __init__(self) -> None:
        self.scope = STScope()
        self._commands: dict[str, Callable[[list[str], STScope], str]] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        self._commands["setvar"] = self._cmd_setvar
        self._commands["getvar"] = self._cmd_getvar
        self._commands["addvar"] = self._cmd_addvar
        self._commands["trim"] = self._cmd_trim
        self._commands["len"] = self._cmd_len
        self._commands["rand"] = self._cmd_rand
        self._commands["echo"] = self._cmd_echo
        self._commands["pass"] = lambda _a, _s: ""

    def _cmd_setvar(self, args: list[str], scope: STScope) -> str:
        if len(args) < 2:
            return ""
        var_scope = "local"
        if args[0].lower() in ("global", "local", "chat"):
            var_scope = args[0].lower()
            args = args[1:]
        scope.set(args[0], " ".join(args[1:]), scope=var_scope)
        return ""

    def _cmd_getvar(self, args: list[str], scope: STScope) -> str:
        return scope.get(args[0]) if args else ""

    def _cmd_addvar(self, args: list[str], scope: STScope) -> str:
        if len(args) < 2:
            return ""
        cur = scope.get(args[0])
        try:
            val = str(int(cur or "0") + int(args[1]))
        except ValueError:
            val = (cur or "") + args[1]
        scope.set(args[0], val)
        return val

    def _cmd_trim(self, args: list[str], _scope: STScope) -> str:
        return (args[0] if args else "").strip()

    def _cmd_len(self, args: list[str], _scope: STScope) -> str:
        return str(len(args[0]) if args else 0)

    def _cmd_rand(self, args: list[str], _scope: STScope) -> str:
        low, high = 0, 100
        if len(args) >= 2:
            low, high = int(args[0]), int(args[1])
        elif args:
            high = int(args[0])
        return str(random.randint(low, high))

    def _cmd_echo(self, args: list[str], _scope: STScope) -> str:
        return " ".join(args)

    def run_pipe(self, script: str, *, input_text: str = "") -> str:
        parts = [p.strip() for p in re.split(r"\|", script) if p.strip()]
        if not parts:
            return input_text
        value = input_text
        for part in parts:
            value = self.run_command_line(part, input_text=value)
        return value

    def run_command_line(self, line: str, *, input_text: str = "") -> str:
        tokens = tokenize(line)
        if not tokens:
            return input_text
        i = 0
        value = input_text
        while i < len(tokens):
            tok = tokens[i]
            if tok.startswith("/"):
                cmd = tok[1:].lower()
                args: list[str] = []
                i += 1
                while i < len(tokens) and not tokens[i].startswith("/") and tokens[i] != "|":
                    if tokens[i] == "{{input}}":
                        args.append(value)
                    else:
                        args.append(tokens[i])
                    i += 1
                handler = self._commands.get(cmd)
                if handler:
                    out = handler(args, self.scope)
                    if out or cmd in ("echo", "getvar", "trim", "len", "rand", "addvar"):
                        value = out
                continue
            if tok == "{{input}}":
                value = input_text
            elif tok.startswith("{{") and tok.endswith("}}"):
                key = tok[2:-2].strip().lower()
                value = self.scope.get(key) if key else value
            else:
                value = tok
            i += 1
        return self._expand_vars(value)

    def _expand_vars(self, text: str) -> str:
        def repl(m: re.Match[str]) -> str:
            return self.scope.get(m.group(1))

        return re.sub(r"\{\{(\w+)\}\}", repl, text or "")
