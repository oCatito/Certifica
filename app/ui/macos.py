"""Ajustes específicos do macOS."""

from __future__ import annotations

import ctypes
import ctypes.util
import sys


def set_app_name(name: str) -> None:
    """Mostra `name` no Dock e no menu do app em vez de "Python" quando roda com `python main.py`.

    O nome vem do CFBundleName do bundle principal, que é o do Python fora do .app. Trocar o valor
    em memória antes de o Tk iniciar a NSApplication basta. No .app gerado pelo PyInstaller o nome
    já é "Certifica", então lá nada é feito. Usa o runtime do Objective-C via ctypes (sem pyobjc).
    """
    if sys.platform != "darwin" or getattr(sys, "frozen", False):
        return
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        vp = ctypes.c_void_p
        msg0 = ctypes.CFUNCTYPE(vp, vp, vp)(send)
        msg_str = ctypes.CFUNCTYPE(vp, vp, vp, ctypes.c_char_p)(send)
        msg2 = ctypes.CFUNCTYPE(None, vp, vp, vp, vp)(send)

        def sel(s: str) -> int:
            return objc.sel_registerName(s.encode())

        def nsstring(s: str) -> int:
            return msg_str(objc.objc_getClass(b"NSString"), sel("stringWithUTF8String:"), s.encode("utf-8"))

        bundle = msg0(objc.objc_getClass(b"NSBundle"), sel("mainBundle"))
        for getter in ("infoDictionary", "localizedInfoDictionary"):
            info = msg0(bundle, sel(getter))
            if info:
                msg2(info, sel("setObject:forKey:"), nsstring(name), nsstring("CFBundleName"))
    except Exception:  # noqa: BLE001 - só cosmético: se falhar, o Dock continua mostrando "Python"
        pass
