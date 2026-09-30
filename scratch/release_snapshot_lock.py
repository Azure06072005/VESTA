import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.DuplicateHandle.argtypes = [
    wintypes.HANDLE,
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HANDLE),
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD
]
kernel32.DuplicateHandle.restype = wintypes.BOOL

kernel32.GetFileType.argtypes = [wintypes.HANDLE]
kernel32.GetFileType.restype = wintypes.DWORD

kernel32.GetFinalPathNameByHandleW.argtypes = [
    wintypes.HANDLE,
    wintypes.LPWSTR,
    wintypes.DWORD,
    wintypes.DWORD
]
kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

DUPLICATE_CLOSE_SOURCE = 0x00000001
hCur = kernel32.GetCurrentProcess()
hProc = kernel32.OpenProcess(0x1FFFFF, False, 1756)

name_buf = ctypes.create_unicode_buffer(1024)

closed_handles = []
for h in range(4, 65536, 4):
    hDup = wintypes.HANDLE()
    if kernel32.DuplicateHandle(hProc, wintypes.HANDLE(h), hCur, ctypes.byref(hDup), 0, False, 2):
        if kernel32.GetFileType(hDup) == 1:
            ret = kernel32.GetFinalPathNameByHandleW(hDup, name_buf, 1024, 0)
            if ret > 0:
                p = name_buf.value
                if "vesta_snapshot.duckdb" in p.lower():
                    print(f"Closing handle 0x{h:X} -> {p}")
                    hDummy = wintypes.HANDLE()
                    kernel32.DuplicateHandle(hProc, wintypes.HANDLE(h), wintypes.HANDLE(0), ctypes.byref(hDummy), 0, False, DUPLICATE_CLOSE_SOURCE)
                    closed_handles.append(h)
        kernel32.CloseHandle(hDup)

kernel32.CloseHandle(hProc)
print(f"Closed {len(closed_handles)} handles on vesta_snapshot.duckdb")
