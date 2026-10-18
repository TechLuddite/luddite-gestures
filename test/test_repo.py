"""Repository checks for an Omarchy plugin, run in CI where the omarchy CLI
is not available. They cover what `omarchy plugin validate` and the
marketplace scanner check, and the plugin rules Luddite Scout reports on.
Run: python3 -m unittest discover -s test"""
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIP_DIRS = {".git", "__pycache__"}
MAX_FILE_BYTES = 512 * 1024
AGENT_FILES = re.compile(r"^(AGENTS\.md|CLAUDE\.md|GEMINI\.md|SKILL\.md|\.claude|\.codex|\.agents|\.gemini|\.cursor|\.github/copilot-instructions\.md)$")
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def tree():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            yield os.path.relpath(path, ROOT), path


def text_files(*exts):
    for rel, path in tree():
        if rel.endswith(exts) and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                yield rel, f.read()


class Manifest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "manifest.json")) as f:
            self.m = json.load(f)

    def test_required_fields(self):
        for key in ("schemaVersion", "id", "name", "version", "author", "license", "description", "kinds", "entryPoints"):
            self.assertIn(key, self.m)
        self.assertEqual(self.m["schemaVersion"], 1)
        self.assertLessEqual(len(self.m["version"]), 64)

    def test_id(self):
        pid = self.m["id"]
        self.assertRegex(pid, r"^[a-z0-9][a-z0-9.-]*$")
        self.assertFalse(pid.startswith("omarchy."), "omarchy.* is reserved")
        self.assertNotIn("clonedFrom", json.dumps(self.m.get("omarchy", {})))

    def test_entry_points_exist(self):
        for kind, rel in self.m["entryPoints"].items():
            self.assertFalse(rel.startswith("/") or ".." in rel, rel)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_ids_agree(self):
        pid = self.m["id"]
        for rel, src in text_files(".qml"):
            for found in re.findall(r'moduleName:\s*"([^"]+)"', src):
                self.assertEqual(found, pid, rel)
        with open(os.path.join(ROOT, "README.md")) as f:
            self.assertIn(f"omarchy plugin remove {pid}", f.read())


class Tree(unittest.TestCase):
    def test_no_symlinks(self):
        for rel, path in tree():
            self.assertFalse(os.path.islink(path), rel)

    def test_required_files(self):
        for name in ("README.md", "LICENSE", "manifest.json"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, name)), name)

    def test_no_agent_instruction_files(self):
        for rel, _ in tree():
            self.assertIsNone(AGENT_FILES.match(rel), f"{rel} would be installed where coding agents read it")

    def test_scanner_limits(self):
        for rel, path in tree():
            if not os.path.isfile(path):
                continue
            self.assertLessEqual(os.path.getsize(path), MAX_FILE_BYTES, rel)
            self.assertFalse(re.search(r"install|setup", os.path.basename(rel), re.I) and rel.endswith((".png", ".jpg", ".gif", ".webp")), rel)
            if rel.endswith(".png"):
                continue
            with open(path, "rb") as f:
                self.assertNotIn(b"\x00", f.read(), rel)

    def test_no_hidden_bidi_characters(self):
        for rel, src in text_files(".qml", ".js", ".lua", ".py", ".md", ".json", ".yml", ".svg", ".desktop"):
            self.assertIsNone(BIDI.search(src), rel)


class Qml(unittest.TestCase):
    def test_every_text_is_plain(self):
        for rel, src in text_files(".qml"):
            for m in re.finditer(r"\b(Text|Label|TextEdit|TextInput)\s*\{", src):
                i, depth = m.end(), 1
                while i < len(src) and depth:
                    depth += (src[i] == "{") - (src[i] == "}")
                    i += 1
                line = src[:m.start()].count("\n") + 1
                self.assertIn("textFormat:", src[m.end():i], f"{rel}:{line}")

    def test_no_unbounded_collectors_or_shell_strings(self):
        for rel, src in text_files(".qml"):
            for pattern in (r"\bStdioCollector\b", r"\bbar\.run\(", r'execDetached\(\s*"', r'"(ba)?sh",\s*"-l?c"'):
                self.assertIsNone(re.search(pattern, src), f"{rel}: {pattern}")

    def test_processes_start_from_absolute_paths(self):
        for rel, src in text_files(".qml"):
            for cmd in re.findall(r"command\s*=\s*\[\s*\"([^\"]+)\"", src):
                self.assertTrue(cmd.startswith("/"), f"{rel}: {cmd}")


if __name__ == "__main__":
    unittest.main()
