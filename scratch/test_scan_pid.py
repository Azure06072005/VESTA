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

pid = 11040
hCur = kernel32.GetCurrentProcess()
# PROCESS_DUP_HANDLE (0x0040) | PROCESS_QUERY_INFORMATION (0x0400) or 0x1FFFFF
hProc = kernel32.OpenProcess(0x1FFFFF, False, pid)
print(f"OpenProcess for PID {pid}: hProc={hProc}, LastError={kernel32.GetLastError()}")

name_buf = ctypes.create_unicode_buffer(1024)
found = []
for h in range(4, 131072, 4):
    hDup = wintypes.HANDLE()
    if kernel32.DuplicateHandle(hProc, wintypes.HANDLE(h), hCur, ctypes.byref(hDup), 0, False, 2):
        if kernel32.GetFileType(hDup) == 1:
            ret = kernel32.GetFinalPathNameByHandleW(hDup, name_buf, 1024, 0)
            if ret > 0:
                p = name_buf.value
                if "vesta" in p.lower() or "duckdb" in p.lower():
                    print(f"Found handle 0x{h:X} -> {p}")
                    found.append((h, p))
        kernel32.CloseHandle(hDup)

kernel32.CloseHandle(hProc)
print(f"Total matching handles in PID {pid}: {len(found)}")
