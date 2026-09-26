import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

# HelmIt auto-format — PostToolUse body. Formatting is NEVER a gate: every
# failure below is deliberately a no-op. Runs config.json.commands.format after
# an edit, but refuses project-wide formatters unless `.helmit/` is protected
# (REQ-102); that tree belongs only to /helmit:* commands.

INPUT = os.environ.get("AF_INPUT", "")
PLAIN = (".prettierignore", ".eslintignore", ".stylelintignore", ".biomeignore", ".formatignore")
CONF = ("pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg", ".flake8", "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "biome.json", "biome.jsonc")
MAX_BYTES = 262144
WINDOW = 300
TTL = 43200


def payload():
    try:
        return json.loads(INPUT)
    except Exception:
        return {}


def config_format(config):
    try:
        with open(config, encoding="utf-8") as fh:
            return json.load(fh).get("commands", {}).get("format", "") or ""
    except Exception:
        return ""


def read(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def covers(line):
    """True when this ignore line takes the whole .helmit/ tree out."""
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("!"):
        return False
    s = s.strip("/")
    if s.startswith("**/"):
        s = s[3:]
    if s.endswith("/**"):
        s = s[:-3]
    return s.strip("/") in (".helmit", ".helmit/*")


def protected(proj, config):
    try:
        with open(config, encoding="utf-8") as fh:
            cmds = json.load(fh).get("commands", {})
        if str(cmds.get("format_guard", "")).strip().lower() == "declared":
            return True
    except Exception:
        pass
    for name in PLAIN:
        for line in read(os.path.join(proj, name)).splitlines():
            if covers(line):
                return True
    for name in CONF:
        text = read(os.path.join(proj, name))
        if ".helmit" not in text:
            continue
        for match in re.finditer(r"\.helmit", text):
            before = text[max(0, match.start() - WINDOW):match.start()]
            if re.search(r"exclude|ignore", before, re.I):
                return True
    return False


def first_time(proj, fmt):
    """Dedup warning outside the repository, once per project+command+12h."""
    try:
        key = hashlib.sha1((os.path.abspath(proj) + "\n" + fmt).encode("utf-8")).hexdigest()[:16]
        stamp = os.path.join(tempfile.gettempdir(), "helmit-fmtguard-" + key)
        if os.path.exists(stamp) and time.time() - os.path.getmtime(stamp) < TTL:
            return False
        with open(stamp, "w") as fh:
            fh.write(fmt)
        return True
    except Exception:
        return True


def edited_paths(data, proj):
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return []
    paths = []
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        paths.append(file_path)
    elif data.get("tool_name") == "apply_patch":
        command = tool_input.get("command", "")
        if not isinstance(command, str):
            return []
        pending = None
        for line in command.splitlines():
            if line.startswith(("*** Add File: ", "*** Update File: ", "*** Delete File: ")):
                if pending:
                    paths.append(pending)
                pending = None if line.startswith("*** Delete File: ") else line.split(": ", 1)[1]
            elif line.startswith("*** Move to: ") and pending:
                pending = line[len("*** Move to: "):]
            elif line == "*** End Patch":
                if pending:
                    paths.append(pending)
                pending = None
    result = []
    seen = set()
    for path in paths:
        absolute = os.path.abspath(os.path.join(proj, path))
        resolved = os.path.realpath(absolute)
        if ".helmit" in absolute.split(os.sep) or ".helmit" in resolved.split(os.sep):
            continue
        if data.get("tool_name") == "apply_patch" and not os.path.isfile(absolute):
            continue
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def substitution_end(text, start):
    depth, quote, index = 1, None, start
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if text.startswith("$(", index) and quote != "'":
            index = substitution_end(text, index + 2) + 1
            continue
        if char in ("'", '"'):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif quote is None:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    raise ValueError("unterminated shell substitution")


def template_words(text):
    words, start, quote, index = [], None, None, 0
    while index < len(text):
        char = text[index]
        if quote is None and (char.isspace() or char in ";&|<>()"):
            if start is not None:
                words.append((start, index, text[start:index]))
                start = None
            if not char.isspace():
                words.append((index, index + 1, char))
            index += 1
            continue
        if start is None:
            start = index
        if char == "\\" and quote != "'":
            index += 2
            continue
        if text.startswith("$(", index) and quote != "'":
            index = substitution_end(text, index + 2) + 1
            continue
        if char in ("'", '"'):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        index += 1
    if quote is not None:
        raise ValueError("unterminated shell quote")
    if start is not None:
        words.append((start, index, text[start:index]))
    return words


def literal_shell_word(raw):
    quote, index = None, 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if char in "$`" and quote != "'":
            return False
        if char in ("'", '"'):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        index += 1
    return True


def interpreter_source(command, value):
    interpreters = r"(?:python[0-9.]*|node|nodejs|perl[0-9.]*|ruby[0-9.]*|php[0-9.]*|[gm]?awk)"
    for index, word in enumerate(command):
        name = os.path.basename(word)
        if not re.fullmatch(interpreters, name):
            continue
        args = command[index + 1:]
        if args and args[-1] in ("-c", "-e", "-p", "-r", "--eval", "--execute", "--expression", "--source"):
            return True
        if re.match(r"^-(?:c|e|p|r).+|^--(?:eval|execute|expression|source)=", value):
            return True
        if name in ("awk", "gawk", "mawk"):
            supplied, skip = False, False
            for arg in args:
                if skip:
                    skip = False
                    continue
                if arg in ("-f", "--file") or arg.startswith("-f"):
                    supplied = True
                    skip = arg in ("-f", "--file")
                elif arg in ("-F", "-v", "--field-separator", "--assign"):
                    skip = True
                elif not arg.startswith("-"):
                    supplied = True
            return not supplied and not skip
    return False


def shell_program_word(words, position):
    def option_values(index, flags):
        for _ in range(sum(flag in "oO" for flag in flags[1:])):
            if index >= len(words) or words[index][2] in ";&|()<>" or "{file}" in words[index][2] or not literal_shell_word(words[index][2]):
                raise ValueError("nested shell option requires a literal value")
            index += 1
        return index

    index = option_values(position + 1, shlex.split(words[position][2])[0])
    while index < len(words):
        raw = words[index][2]
        if raw in ";&|()<>":
            raise ValueError("nested shell program is missing")
        if not literal_shell_word(raw):
            raise ValueError("nested shell source and options must be literal")
        parsed = shlex.split(raw)
        if len(parsed) != 1:
            raise ValueError("nested shell program must be one literal argument")
        value = parsed[0]
        if value == "--":
            index += 1
            break
        if re.fullmatch(r"[-+][A-Za-z]+", value):
            index = option_values(index + 1, value)
            continue
        if value.startswith(("-", "+")) and value not in ("-", "+"):
            raise ValueError("ambiguous nested shell option before its program")
        break
    if index >= len(words) or words[index][2] in ";&|()<>":
        raise ValueError("nested shell program is missing")
    return words[index]


def file_template(fmt, depth=0):
    if depth > 12:
        raise ValueError("shell template nesting is too deep")
    if "{file}" not in fmt:
        return fmt
    if "`" in fmt or "<<" in fmt or "$((" in fmt or "<(" in fmt or ">(" in fmt:
        raise ValueError("use a direct filename argument instead of heredoc, backtick, arithmetic or process substitution")
    words = template_words(fmt)
    replacements, command = [], []
    for position, (start, end, raw) in enumerate(words):
        parsed = shlex.split(raw)
        value = parsed[0] if len(parsed) == 1 else ""
        if raw in ";&|()":
            command = []
            continue
        if os.path.basename(value) in ("bash", "sh", "dash", "zsh", "ksh"):
            following = []
            for _, _, argument in words[position + 1:]:
                if argument in ";&|()<>":
                    break
                following.append(argument)
            if not any(not argument.startswith("-") for argument in following):
                raise ValueError("shell input must use an explicit literal -c program or a script file")
        if value == "eval":
            raise ValueError("eval cannot safely accept a filename template")
        if "{file}" in raw and interpreter_source(command, value):
            raise ValueError("interpreter source cannot contain a filename template")
        if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", value) and position + 1 < len(words):
            shell_command = any(os.path.basename(word) in ("bash", "sh", "dash", "zsh", "ksh") for word in command)
            code_start, code_end, code_raw = shell_program_word(words, position) if shell_command else words[position + 1]
            if "{file}" in code_raw:
                if not shell_command:
                    if any("$" in word or "`" in word for word in command):
                        raise ValueError("nested interpreter name must be literal")
                    command.append(value)
                    continue
                if not literal_shell_word(code_raw):
                    raise ValueError("nested shell source must be literal; pass dynamic values as arguments")
                code = shlex.split(code_raw)
                if len(code) != 1:
                    raise ValueError("nested shell source must be one literal argument")
                replacements.append((code_start, code_end, shlex.quote(file_template(code[0], depth + 1))))
        command.append(value)
    for start, end, replacement in reversed(replacements):
        fmt = fmt[:start] + replacement + fmt[end:]
    result = []
    quote = None
    index = 0
    while index < len(fmt):
        if fmt.startswith("$(", index) and quote != "'":
            end = substitution_end(fmt, index + 2)
            result.append("$(" + file_template(fmt[index + 2:end], depth + 1) + ")")
            index = end + 1
            continue
        if fmt.startswith("{file}", index):
            expansion = '${HELMIT_FORMAT_FILE}'
            if quote == "'":
                expansion = "'\"" + expansion + "\"'"
            elif quote != '"':
                expansion = '"' + expansion + '"'
            result.append(expansion)
            index += len("{file}")
            continue
        char = fmt[index]
        result.append(char)
        index += 1
        if char == "\\" and quote != "'" and index < len(fmt):
            result.append(fmt[index])
            index += 1
        elif char in ("'", '"'):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
    return "".join(result)


def main():
    data = payload()
    proj = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd", "") or os.getcwd()
    config = os.path.join(proj, ".helmit", "config.json")
    if not os.path.isfile(config):
        return
    fmt = config_format(config)
    if not fmt:
        return
    paths = edited_paths(data, proj)
    if not paths:
        return
    per_file = "{file}" in fmt
    if per_file:
        try:
            fmt = file_template(fmt)
        except ValueError as error:
            print("HelmIt: auto-format SKIPPED. Unsafe filename template: " + str(error), file=sys.stderr)
            return
    elif not protected(proj, config):
        if first_time(proj, fmt):
            msg = "HelmIt: auto-format SKIPPED. commands.format is project-wide and would rewrite .helmit/, which only the /helmit:* commands may write. Fix: use the {file} form (e.g. prettier --write {file}), or add the helmit:format-ignore block to your formatter ignore file (see /helmit:setup), or set commands.format_guard to declared once .helmit/ is excluded by other means."
            print(json.dumps({"systemMessage": msg}))
            print(msg, file=sys.stderr)
        return
    for path in paths if per_file else [None]:
        try:
            env = dict(os.environ)
            if path is not None:
                env["HELMIT_FORMAT_FILE"] = path
            subprocess.run(["bash", "-c", fmt], cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
