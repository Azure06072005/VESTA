import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32
ntdll = ctypes.windll.ntdll

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

hCur = kernel32.GetCurrentProcess()
hProc = kernel32.OpenProcess(0x1FFFFF, False, 1756)

found = []
name_buf = ctypes.create_unicode_buffer(1024)

# Scan all handle values up to 65536 in steps of 4
for h in range(4, 65536, 4):
    hDup = wintypes.HANDLE()
    # DUPLICATE_SAME_ACCESS = 2
    if kernel32.DuplicateHandle(hProc, wintypes.HANDLE(h), hCur, ctypes.byref(hDup), 0, False, 2):
        ft = kernel32.GetFileType(hDup)
        if ft == 1: # FILE_TYPE_DISK
            ret = kernel32.GetFinalPathNameByHandleW(hDup, name_buf, 1024, 0)
            if ret > 0:
                p = name_buf.value
                if "vesta" in p.lower() or "duckdb" in p.lower():
                    print(f"MATCH: Handle 0x{h:X} -> {p}")
                    found.append((h, p))
        kernel32.CloseHandle(hDup)

kernel32.CloseHandle(hProc)
print(f"Total matching handles: {len(found)}")
