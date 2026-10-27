"""PATs live only in Windows Credential Manager, never in SQLite or config files."""
import ctypes
from ctypes import wintypes
import sys


class WindowsCredentials:
    label='Confluence PAT'
    def _api(self):
        if sys.platform != "win32":
            raise RuntimeError("Хранение PAT поддерживается в Windows Credential Manager.")
        return ctypes.WinDLL("Advapi32.dll", use_last_error=True)

    @staticmethod
    def _key(key): return "ArchitectureRegistryStudio/Confluence/" + key

    def set(self, key, value):
        api = self._api()
        raw = value.encode("utf-16-le")
        if len(raw) > 2560: raise RuntimeError("PAT слишком длинный для Windows Credential Manager.")
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        cred = CREDENTIAL()
        cred.Type, cred.TargetName, cred.CredentialBlobSize, cred.CredentialBlob = 1, self._key(key), len(raw), buffer
        cred.Persist, cred.UserName = 2, self.label
        api.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        if not api.CredWriteW(ctypes.byref(cred), 0): raise RuntimeError("Не удалось сохранить PAT в Windows Credential Manager.")

    def get(self, key):
        api = self._api()
        pointer = ctypes.POINTER(CREDENTIAL)()
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        if not api.CredReadW(self._key(key), 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168: return None
            raise RuntimeError("Не удалось прочитать PAT из Windows Credential Manager.")
        try: return ctypes.string_at(pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize).decode("utf-16-le")
        finally: api.CredFree(pointer)

    def delete(self, key):
        api = self._api()
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        if not api.CredDeleteW(self._key(key), 1, 0) and ctypes.get_last_error() != 1168:
            raise RuntimeError("Не удалось удалить PAT из Windows Credential Manager.")


class CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
