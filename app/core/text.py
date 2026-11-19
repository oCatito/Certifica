"""Funções de texto compartilhadas."""

from __future__ import annotations

import re
import unicodedata

# Caracteres invisíveis que costumam vir junto ao copiar e colar (web, Word, PDF).
_INVISIBLE_RE = re.compile("[­᠎​-‏ -  -⁯﻿]")

# Palavras que ficam em minúsculas no meio de um nome ("Maria da Silva").
_NAME_PARTICLES = {"a", "o", "e", "y", "da", "das", "de", "di", "do", "dos", "du", "del", "della",
                   "la", "le", "van", "von", "der", "den"}
_ROMAN_NUMERALS = {"ii", "iii", "iv", "vi", "vii", "viii", "ix", "xi", "xii"}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def nfc(value: str) -> str:
    """Forma composta do Unicode: 'a' + '~' vira 'ã' (o Mac às vezes guarda separado)."""
    return unicodedata.normalize("NFC", value or "")


def normalize(value: str) -> str:
    """Minúsculas, sem acentos e sem espaços nas pontas."""
    return strip_accents(value or "").strip().lower()


def variable_key(value: str) -> str:
    """Chave de variável: 'Data do Curso' -> 'data_do_curso'."""
    return re.sub(r"[\s\-]+", "_", normalize(value))


def file_key(value: str) -> str:
    """Chave para achar arquivos: ignora maiúsculas, acentos e trata espaço, _ e - como iguais.

    'Maria  José.pdf', 'maria_jose.pdf' e 'MARIA-JOSÉ.PDF' viram 'maria jose.pdf'.
    """
    return re.sub(r"[\s_\-]+", " ", normalize(value)).strip()


def remove_invisible(value: str) -> str:
    """Tira caracteres invisíveis (espaço de largura zero, hífen suave, BOM etc.)."""
    return _INVISIBLE_RE.sub("", value or "")


def clean_email(value: str) -> str:
    return remove_invisible(nfc(value)).strip()


def format_person_name(value: str) -> str:
    """Ajusta nomes digitados TODO EM MAIÚSCULAS ou todo em minúsculas.

    'JOÃO DA CONCEIÇÃO' -> 'João da Conceição'. Nomes já com maiúsculas e minúsculas
    misturadas ficam como estão, para respeitar grafias como 'McDonald' ou 'DiCaprio'.
    """
    name = " ".join(remove_invisible(nfc(value)).split())
    if not any(c.isalpha() for c in name) or not (name.isupper() or name.islower()):
        return name

    def cap(part: str) -> str:
        return part[:1].upper() + part[1:].lower()

    words = []
    for i, word in enumerate(name.split(" ")):
        low = word.lower()
        if i > 0 and low in _NAME_PARTICLES:
            words.append(low)
        elif low in _ROMAN_NUMERALS:
            words.append(word.upper())
        else:
            # Maiúscula também depois de hífen e apóstrofo: 'Maria-José', "D'Ávila".
            words.append(re.sub(r"[^\-'’]+", lambda m: cap(m.group(0)), word))
    return " ".join(words)
