#!/usr/bin/env python3

import sys, os, re, json, csv, math, random
from PyQt5.QtWidgets import (
    QApplication, QWidget, QGridLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QFileDialog, QMessageBox, QSpinBox, QTextEdit,
    QTabWidget, QListWidget, QListWidgetItem, QProgressBar
)
from PyQt5.QtCore import QThread, pyqtSignal

SYMBOLS = "!@#$%^&*()-_+="
AMBIGUOUS = "0O1lI"

LEET = {
    "a": "@",
    "o": "0",
    "i": "1",
    "e": "3",
    "s": "$",
    "t": "7",
    "l": "1"
}


def entropy(password: str) -> float:
    """
    Calculate Shannon entropy estimate for a password.
    """
    if not password:
        return 0.0
    freq = {}
    for c in password:
        freq[c] = freq.get(c, 0) + 1
    ent = 0.0
    length = len(password)
    for f in freq.values():
        p = f / length
        ent -= p * math.log2(p)
    return ent * length


class GenerateWorker(QThread):
    finished = pyqtSignal(list, str)
    progress = pyqtSignal(int)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def load_words(self):
        words = []
        for path in self.config["wordlists"]:
            if not os.path.isfile(path):
                continue
            with open(path, "r", errors="ignore") as f:
                for line in f:
                    w = line.strip()
                    if w:
                        words.append(w)
        return words

    def apply_filters(self, word):
        cfg = self.config
        if cfg["min_word_len"] and len(word) < cfg["min_word_len"]:
            return False
        if cfg["max_word_len"] and len(word) > cfg["max_word_len"]:
            return False
        if cfg["remove_words_with_numbers"] and re.search(r"\d", word):
            return False
        if cfg["remove_words_with_symbols"] and re.search(r"[^\w]", word):
            return False
        if cfg["include_regex"] and not re.search(cfg["include_regex"], word):
            return False
        if cfg["exclude_regex"] and re.search(cfg["exclude_regex"], word):
            return False
        return True

    def apply_case(self, word):
        mode = self.config["case_mode"]
        if mode == "lower": return word.lower()
        if mode == "upper": return word.upper()
        if mode == "title": return word.title()
        if mode == "random":
            return "".join(
                c.upper() if random.choice([True, False]) else c.lower()
                for c in word
            )
        return word

    def leet(self, word):
        return "".join(LEET.get(c.lower(), c) for c in word)

    def rand_num(self):
        cfg = self.config
        if cfg["num_type"] == "fixed":
            return "".join(random.choice("0123456789") for _ in range(cfg["num_len"]))
        return str(random.randint(0, cfg["num_max"]))

    def rand_sym(self):
        return "".join(random.choice(SYMBOLS) for _ in range(self.config["sym_count"]))

    def sep_char(self):
        s = self.config["separator"]
        if s == "dash": return "-"
        if s == "underscore": return "_"
        if s == "dot": return "."
        return ""

    def build_from_pattern(self):
        cfg = self.config
        pattern = cfg["pattern"]
        # Pattern example: W-W-D-S
        parts = pattern.split("-")
        out = ""
        for p in parts:
            if p == "W":
                out += self.pick_word()
            elif p == "D":
                out += self.rand_num()
            elif p == "S":
                out += self.rand_sym()
            else:
                out += p
        return out

    def pick_word(self):
        cfg = self.config
        word = random.choice(self.config["words_pool"])
        while not self.apply_filters(word):
            word = random.choice(self.config["words_pool"])
        return word

    def remove_ambiguous(self, pwd):
        for c in AMBIGUOUS:
            pwd = pwd.replace(c, "")
        return pwd

    def run(self):
        cfg = self.config
        words = self.load_words()

        if cfg["remove_source_duplicates"]:
            words = list(dict.fromkeys(words))

        if not words:
            self.finished.emit([], cfg["output"])
            return

        cfg["words_pool"] = words

        results = []
        seen = set()

        for i in range(cfg["count"]):
            if cfg["pattern_mode"]:
                pwd = self.build_from_pattern()
            else:
                # standard word generation
                parts = []
                used = set()
                for _ in range(cfg["words_per_password"]):
                    w = self.pick_word()
                    if cfg["unique_words"] and w in used:
                        continue
                    used.add(w)
                    if cfg["case_mode"] != "none":
                        w = self.apply_case(w)
                    if cfg["leet_mode"]:
                        w = self.leet(w)
                    parts.append(w)

                if cfg["shuffle_words"]:
                    random.shuffle(parts)

                sep = self.sep_char()
                pwd = sep.join(parts)

                if cfg["insert_between"]:
                    # add symbol/number between words
                    newpwd = ""
                    for idx, w in enumerate(parts):
                        newpwd += w
                        if idx < len(parts)-1:
                            if cfg["insert_between"] == "symbol":
                                newpwd += random.choice(SYMBOLS)
                            elif cfg["insert_between"] == "number":
                                newpwd += self.rand_num()
                    pwd = newpwd

            if cfg["use_symbols"]:
                pwd += self.rand_sym()

            if cfg["use_numbers"] and not cfg["numbers_at_end"]:
                pwd += self.rand_num()
            if cfg["use_numbers"] and cfg["numbers_at_end"]:
                pwd += self.rand_num()

            pwd = cfg["prefix"] + pwd + cfg["suffix"]

            if cfg["exclude_ambiguous"]:
                pwd = self.remove_ambiguous(pwd)

            if cfg["smart_mode"]:
                if not re.search(r"\d", pwd):
                    pwd += self.rand_num()
                if not re.search(r"[!@#$%^&*()_+=-]", pwd):
                    pwd += self.rand_sym()

            if cfg["min_len"] and len(pwd) < cfg["min_len"]:
                continue

            if cfg["avoid_duplicates"] and pwd in seen:
                continue

            seen.add(pwd)
            results.append(pwd)

            self.progress.emit(int((i+1)/cfg["count"]*100))

        # Output save
        out = cfg["output"]
        fmt = cfg["output_format"]

        if fmt == "csv":
            with open(out, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["password"])
                for p in results:
                    writer.writerow([p])
        elif fmt == "json":
            with open(out, "w") as f:
                json.dump(results, f, indent=2)
        else:
            with open(out, "w") as f:
                f.write("\n".join(results))

        self.finished.emit(results, out)


class FixWorker(QThread):
    finished = pyqtSignal(list, str)
    progress = pyqtSignal(int)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def remove_ambiguous(self, pwd):
        for c in AMBIGUOUS:
            pwd = pwd.replace(c, "")
        return pwd

    def ensure_policy(self, pwd):
        cfg = self.config
        if cfg["policy_upper"] and not re.search(r"[A-Z]", pwd):
            pwd += random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        if cfg["policy_lower"] and not re.search(r"[a-z]", pwd):
            pwd += random.choice("abcdefghijklmnopqrstuvwxyz")
        if cfg["policy_number"] and not re.search(r"\d", pwd):
            pwd += str(random.randint(0, 9))
        if cfg["policy_symbol"] and not re.search(r"[!@#$%^&*()_+=-]", pwd):
            pwd += random.choice(SYMBOLS)
        return pwd

    def run(self):
        cfg = self.config
        if not os.path.isfile(cfg["input"]):
            self.finished.emit([], cfg["output"])
            return

        with open(cfg["input"], "r", errors="ignore") as f:
            passwords = [line.strip() for line in f if line.strip()]

        fixed = []
        seen = set()

        for idx, pwd in enumerate(passwords):
            if cfg["remove_ambiguous"]:
                pwd = self.remove_ambiguous(pwd)

            if cfg["blacklist"]:
                if any(b in pwd for b in cfg["blacklist"]):
                    continue

            if cfg["whitelist"]:
                if not any(w in pwd for w in cfg["whitelist"]):
                    continue

            if cfg["smart_mode"]:
                pwd = self.ensure_policy(pwd)

            if cfg["min_len"] and len(pwd) < cfg["min_len"]:
                continue

            if cfg["remove_duplicates"] and pwd in seen:
                continue

            if cfg["max_entropy"] and entropy(pwd) < cfg["max_entropy"]:
                continue

            seen.add(pwd)
            fixed.append(pwd)
            self.progress.emit(int((idx+1)/len(passwords)*100))

        out = cfg["output"]
        fmt = cfg["output_format"]

        if fmt == "csv":
            with open(out, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["password"])
                for p in fixed:
                    writer.writerow([p])
        elif fmt == "json":
            with open(out, "w") as f:
                json.dump(fixed, f, indent=2)
        else:
            with open(out, "w") as f:
                f.write("\n".join(fixed))

        self.finished.emit(fixed, out)


class WordToolGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ultimate Password Tool")
        self.setGeometry(150, 150, 1200, 800)

        layout = QGridLayout()
        self.setLayout(layout)

        tabs = QTabWidget()
        layout.addWidget(tabs, 0, 0)

        self.gen_tab = QWidget()
        self.fix_tab = QWidget()

        tabs.addTab(self.gen_tab, "Generator")
        tabs.addTab(self.fix_tab, "Fixer")

        self.init_generator()
        self.init_fixer()

    def init_generator(self):
        layout = QGridLayout()
        self.gen_tab.setLayout(layout)

        # Wordlists
        layout.addWidget(QLabel("Wordlist files (multi-select):"), 0, 0)
        self.wordlist_entry = QLineEdit()
        layout.addWidget(self.wordlist_entry, 0, 1, 1, 2)
        self.wordlist_btn = QPushButton("Browse")
        self.wordlist_btn.clicked.connect(self.choose_wordlists)
        layout.addWidget(self.wordlist_btn, 0, 3)

        # Word options
        layout.addWidget(QLabel("Words per password:"), 1, 0)
        self.words_spin = QSpinBox()
        self.words_spin.setRange(1, 5)
        self.words_spin.setValue(2)
        layout.addWidget(self.words_spin, 1, 1)

        layout.addWidget(QLabel("Case mode:"), 1, 2)
        self.case_combo = QComboBox()
        self.case_combo.addItems(["lower", "upper", "title", "random", "none"])
        layout.addWidget(self.case_combo, 1, 3)

        self.unique_check = QCheckBox("Unique words")
        layout.addWidget(self.unique_check, 2, 0)

        # Filters
        self.remove_numbers_check = QCheckBox("Remove words with numbers")
        layout.addWidget(self.remove_numbers_check, 2, 1)

        self.remove_symbols_check = QCheckBox("Remove words with symbols")
        layout.addWidget(self.remove_symbols_check, 2, 2)

        layout.addWidget(QLabel("Include regex:"), 3, 0)
        self.include_regex = QLineEdit()
        layout.addWidget(self.include_regex, 3, 1, 1, 3)

        layout.addWidget(QLabel("Exclude regex:"), 4, 0)
        self.exclude_regex = QLineEdit()
        layout.addWidget(self.exclude_regex, 4, 1, 1, 3)

        layout.addWidget(QLabel("Min word length:"), 5, 0)
        self.min_word_spin = QSpinBox()
        self.min_word_spin.setValue(0)
        layout.addWidget(self.min_word_spin, 5, 1)

        layout.addWidget(QLabel("Max word length:"), 5, 2)
        self.max_word_spin = QSpinBox()
        self.max_word_spin.setValue(0)
        layout.addWidget(self.max_word_spin, 5, 3)

        self.remove_source_dups_check = QCheckBox("Remove duplicates from source")
        layout.addWidget(self.remove_source_dups_check, 6, 0)

        # Pattern mode
        self.pattern_mode_check = QCheckBox("Pattern mode (W=word, D=number, S=symbol)")
        layout.addWidget(self.pattern_mode_check, 7, 0)
        layout.addWidget(QLabel("Pattern:"), 7, 1)
        self.pattern_entry = QLineEdit("W-W-D-S")
        layout.addWidget(self.pattern_entry, 7, 2, 1, 2)

        # Leet & shuffle
        self.leet_check = QCheckBox("Leetspeak")
        layout.addWidget(self.leet_check, 8, 0)

        self.shuffle_check = QCheckBox("Shuffle words")
        layout.addWidget(self.shuffle_check, 8, 1)

        # Insert between words
        layout.addWidget(QLabel("Insert between words:"), 9, 0)
        self.insert_between_combo = QComboBox()
        self.insert_between_combo.addItems(["none", "symbol", "number"])
        layout.addWidget(self.insert_between_combo, 9, 1)

        # Numbers / symbols
        self.use_numbers_check = QCheckBox("Include numbers")
        layout.addWidget(self.use_numbers_check, 10, 0)

        layout.addWidget(QLabel("Number type:"), 10, 1)
        self.num_type_combo = QComboBox()
        self.num_type_combo.addItems(["fixed", "random"])
        layout.addWidget(self.num_type_combo, 10, 2)

        layout.addWidget(QLabel("Number length:"), 11, 0)
        self.num_len_spin = QSpinBox()
        self.num_len_spin.setValue(2)
        layout.addWidget(self.num_len_spin, 11, 1)

        layout.addWidget(QLabel("Number max:"), 11, 2)
        self.num_max_spin = QSpinBox()
        self.num_max_spin.setValue(999)
        layout.addWidget(self.num_max_spin, 11, 3)

        self.numbers_end_check = QCheckBox("Numbers at end only")
        layout.addWidget(self.numbers_end_check, 12, 0)

        self.use_symbols_check = QCheckBox("Include symbols")
        layout.addWidget(self.use_symbols_check, 12, 1)

        layout.addWidget(QLabel("Symbol count:"), 12, 2)
        self.sym_count_spin = QSpinBox()
        self.sym_count_spin.setValue(1)
        layout.addWidget(self.sym_count_spin, 12, 3)

        # Separator, prefix, suffix
        layout.addWidget(QLabel("Separator:"), 13, 0)
        self.sep_combo = QComboBox()
        self.sep_combo.addItems(["none", "dash", "underscore", "dot"])
        layout.addWidget(self.sep_combo, 13, 1)

        layout.addWidget(QLabel("Prefix:"), 14, 0)
        self.prefix_entry = QLineEdit()
        layout.addWidget(self.prefix_entry, 14, 1)

        layout.addWidget(QLabel("Suffix:"), 14, 2)
        self.suffix_entry = QLineEdit()
        layout.addWidget(self.suffix_entry, 14, 3)

        # Options
        self.avoid_duplicates_check = QCheckBox("Avoid duplicates")
        self.avoid_duplicates_check.setChecked(True)
        layout.addWidget(self.avoid_duplicates_check, 15, 0)

        layout.addWidget(QLabel("Min length:"), 15, 1)
        self.min_len_spin = QSpinBox()
        self.min_len_spin.setValue(0)
        layout.addWidget(self.min_len_spin, 15, 2)

        self.exclude_ambig_check = QCheckBox("Exclude ambiguous chars")
        self.exclude_ambig_check.setChecked(True)
        layout.addWidget(self.exclude_ambig_check, 16, 0)

        self.smart_check = QCheckBox("Smart mode (ensure number+symbol)")
        layout.addWidget(self.smart_check, 16, 1)

        # Count + output
        layout.addWidget(QLabel("Count:"), 17, 0)
        self.count_spin = QSpinBox()
        self.count_spin.setValue(100)
        layout.addWidget(self.count_spin, 17, 1)

        layout.addWidget(QLabel("Output file:"), 17, 2)
        self.output_entry = QLineEdit("generated_wordlist.txt")
        layout.addWidget(self.output_entry, 17, 3)

        layout.addWidget(QLabel("Output format:"), 18, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["txt", "csv", "json"])
        layout.addWidget(self.format_combo, 18, 1)

        self.gen_btn = QPushButton("Generate")
        self.gen_btn.clicked.connect(self.generate)
        layout.addWidget(self.gen_btn, 19, 0, 1, 4)

        self.gen_progress = QProgressBar()
        layout.addWidget(self.gen_progress, 20, 0, 1, 4)

        self.preview_gen = QTextEdit()
        self.preview_gen.setReadOnly(True)
        layout.addWidget(self.preview_gen, 21, 0, 1, 4)

    def init_fixer(self):
        layout = QGridLayout()
        self.fix_tab.setLayout(layout)

        layout.addWidget(QLabel("Input file:"), 0, 0)
        self.in_entry = QLineEdit()
        layout.addWidget(self.in_entry, 0, 1, 1, 2)
        self.in_btn = QPushButton("Browse")
        self.in_btn.clicked.connect(self.choose_in)
        layout.addWidget(self.in_btn, 0, 3)

        layout.addWidget(QLabel("Output file:"), 1, 0)
        self.out_entry = QLineEdit("fixed_wordlist.txt")
        layout.addWidget(self.out_entry, 1, 1, 1, 2)
        self.out_btn = QPushButton("Browse")
        self.out_btn.clicked.connect(self.choose_out)
        layout.addWidget(self.out_btn, 1, 3)

        self.remove_ambig_check = QCheckBox("Remove ambiguous characters")
        self.remove_ambig_check.setChecked(True)
        layout.addWidget(self.remove_ambig_check, 2, 0)

        self.smart_fix_check = QCheckBox("Enforce policy (upper/lower/number/symbol)")
        layout.addWidget(self.smart_fix_check, 2, 1)

        layout.addWidget(QLabel("Min length:"), 3, 0)
        self.min_fix_len_spin = QSpinBox()
        self.min_fix_len_spin.setValue(0)
        layout.addWidget(self.min_fix_len_spin, 3, 1)

        self.remove_dup_fix_check = QCheckBox("Remove duplicates")
        self.remove_dup_fix_check.setChecked(True)
        layout.addWidget(self.remove_dup_fix_check, 3, 2)

        layout.addWidget(QLabel("Max entropy (0=off):"), 4, 0)
        self.max_entropy_spin = QSpinBox()
        self.max_entropy_spin.setValue(0)
        layout.addWidget(self.max_entropy_spin, 4, 1)

        # Policy enforcement
        self.policy_upper = QCheckBox("Require Uppercase")
        self.policy_upper.setChecked(True)
        layout.addWidget(self.policy_upper, 5, 0)

        self.policy_lower = QCheckBox("Require Lowercase")
        self.policy_lower.setChecked(True)
        layout.addWidget(self.policy_lower, 5, 1)

        self.policy_number = QCheckBox("Require Number")
        self.policy_number.setChecked(True)
        layout.addWidget(self.policy_number, 5, 2)

        self.policy_symbol = QCheckBox("Require Symbol")
        self.policy_symbol.setChecked(True)
        layout.addWidget(self.policy_symbol, 5, 3)

        # blacklist/whitelist
        layout.addWidget(QLabel("Blacklist (comma separated):"), 6, 0)
        self.blacklist_entry = QLineEdit()
        layout.addWidget(self.blacklist_entry, 6, 1, 1, 3)

        layout.addWidget(QLabel("Whitelist (comma separated):"), 7, 0)
        self.whitelist_entry = QLineEdit()
        layout.addWidget(self.whitelist_entry, 7, 1, 1, 3)

        layout.addWidget(QLabel("Output format:"), 8, 0)
        self.fix_format_combo = QComboBox()
        self.fix_format_combo.addItems(["txt", "csv", "json"])
        layout.addWidget(self.fix_format_combo, 8, 1)

        self.fix_btn = QPushButton("Fix Password File")
        self.fix_btn.clicked.connect(self.fix_passwords)
        layout.addWidget(self.fix_btn, 9, 0, 1, 4)

        self.fix_progress = QProgressBar()
        layout.addWidget(self.fix_progress, 10, 0, 1, 4)

        self.preview_fix = QTextEdit()
        self.preview_fix.setReadOnly(True)
        layout.addWidget(self.preview_fix, 11, 0, 1, 4)

    def choose_wordlists(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select wordlist files", "", "Text Files (*.txt)")
        if files:
            self.wordlist_entry.setText(",".join(files))

    def choose_in(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select password file", "", "Text Files (*.txt)")
        if file:
            self.in_entry.setText(file)

    def choose_out(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save fixed file", "", "Text Files (*.txt)")
        if file:
            self.out_entry.setText(file)

    def generate(self):
        wordlists = [p.strip() for p in self.wordlist_entry.text().split(",") if p.strip()]
        if not wordlists:
            QMessageBox.warning(self, "Error", "Select wordlist file(s)!")
            return

        out = self.output_entry.text()
        if not out:
            QMessageBox.warning(self, "Error", "Select output file!")
            return

        config = {
            "wordlists": wordlists,
            "words_per_password": self.words_spin.value(),
            "case_mode": self.case_combo.currentText(),
            "unique_words": self.unique_check.isChecked(),
            "remove_words_with_numbers": self.remove_numbers_check.isChecked(),
            "remove_words_with_symbols": self.remove_symbols_check.isChecked(),
            "include_regex": self.include_regex.text(),
            "exclude_regex": self.exclude_regex.text(),
            "min_word_len": self.min_word_spin.value(),
            "max_word_len": self.max_word_spin.value(),
            "remove_source_duplicates": self.remove_source_dups_check.isChecked(),
            "pattern_mode": self.pattern_mode_check.isChecked(),
            "pattern": self.pattern_entry.text(),
            "leet_mode": self.leet_check.isChecked(),
            "shuffle_words": self.shuffle_check.isChecked(),
            "insert_between": self.insert_between_combo.currentText(),
            "use_numbers": self.use_numbers_check.isChecked(),
            "num_type": self.num_type_combo.currentText(),
            "num_len": self.num_len_spin.value(),
            "num_max": self.num_max_spin.value(),
            "numbers_at_end": self.numbers_end_check.isChecked(),
            "use_symbols": self.use_symbols_check.isChecked(),
            "sym_count": self.sym_count_spin.value(),
            "separator": self.sep_combo.currentText(),
            "prefix": self.prefix_entry.text(),
            "suffix": self.suffix_entry.text(),
            "avoid_duplicates": self.avoid_duplicates_check.isChecked(),
            "min_len": self.min_len_spin.value(),
            "exclude_ambiguous": self.exclude_ambig_check.isChecked(),
            "smart_mode": self.smart_check.isChecked(),
            "count": self.count_spin.value(),
            "output": out,
            "output_format": self.format_combo.currentText()
        }

        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("Generating...")
        self.gen_progress.setValue(0)

        self.worker = GenerateWorker(config)
        self.worker.progress.connect(self.gen_progress.setValue)
        self.worker.finished.connect(self.on_generate_finished)
        self.worker.start()

    def on_generate_finished(self, results, out_file):
        self.preview_gen.setPlainText("\n".join(results))
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("Generate")
        self.gen_progress.setValue(100)

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Generation Complete")
        msg.setText(f"Generated {len(results)} passwords!")
        msg.setInformativeText(f"Saved to: {out_file}")
        msg.exec_()

    def fix_passwords(self):
        inp = self.in_entry.text()
        out = self.out_entry.text()
        if not inp or not os.path.isfile(inp):
            QMessageBox.warning(self, "Error", "Input file missing!")
            return
        if not out:
            QMessageBox.warning(self, "Error", "Output file missing!")
            return

        config = {
            "input": inp,
            "output": out,
            "remove_ambiguous": self.remove_ambig_check.isChecked(),
            "smart_mode": self.smart_fix_check.isChecked(),
            "min_len": self.min_fix_len_spin.value(),
            "remove_duplicates": self.remove_dup_fix_check.isChecked(),
            "max_entropy": self.max_entropy_spin.value(),
            "policy_upper": self.policy_upper.isChecked(),
            "policy_lower": self.policy_lower.isChecked(),
            "policy_number": self.policy_number.isChecked(),
            "policy_symbol": self.policy_symbol.isChecked(),
            "blacklist": [x.strip() for x in self.blacklist_entry.text().split(",") if x.strip()],
            "whitelist": [x.strip() for x in self.whitelist_entry.text().split(",") if x.strip()],
            "output_format": self.fix_format_combo.currentText()
        }

        self.fix_btn.setEnabled(False)
        self.fix_btn.setText("Fixing...")
        self.fix_progress.setValue(0)

        self.worker = FixWorker(config)
        self.worker.progress.connect(self.fix_progress.setValue)
        self.worker.finished.connect(self.on_fix_finished)
        self.worker.start()

    def on_fix_finished(self, results, out_file):
        self.preview_fix.setPlainText("\n".join(results))
        self.fix_btn.setEnabled(True)
        self.fix_btn.setText("Fix Password File")
        self.fix_progress.setValue(100)

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Fix Complete")
        msg.setText(f"Fixed {len(results)} passwords!")
        msg.setInformativeText(f"Saved to: {out_file}")
        msg.exec_()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = WordToolGUI()
    win.show()
    sys.exit(app.exec_())
