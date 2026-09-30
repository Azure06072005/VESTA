import ctypes
from ctypes import wintypes
import sys

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

pid = 3184
hCur = kernel32.GetCurrentProcess()
hProc = kernel32.OpenProcess(0x1FFFFF, False, pid)

if not hProc:
    print(f"Không thể mở tiến trình PID {pid}")
    sys.exit(1)

closed_count = 0
name_buf = ctypes.create_unicode_buffer(1024)

print(f"Scanning open handles in PID {pid}...")
for h in range(4, 65536, 4):
    hDup = wintypes.HANDLE()
    # DUPLICATE_SAME_ACCESS = 2
    if kernel32.DuplicateHandle(hProc, wintypes.HANDLE(h), hCur, ctypes.byref(hDup), 0, False, 2):
        ft = kernel32.GetFileType(hDup)
        if ft == 1: # FILE_TYPE_DISK
            ret = kernel32.GetFinalPathNameByHandleW(hDup, name_buf, 1024, 0)
            if ret > 0:
                p = name_buf.value
                if "vesta_snapshot.duckdb" in p.lower() and not p.lower().endswith(".wal"):
                    print(f"MATCH: Handle 0x{h:X} -> {p}")
                    kernel32.CloseHandle(hDup)
                    # DUPLICATE_CLOSE_SOURCE = 1
                    hNull = wintypes.HANDLE()
                    res = kernel32.DuplicateHandle(hProc, wintypes.HANDLE(h), 0, ctypes.byref(hNull), 0, False, 1)
                    if res:
                        print(f"  -> Successfully closed source handle 0x{h:X}!")
                        closed_count += 1
                    else:
                        print(f"  -> Failed to close handle 0x{h:X}, err: {kernel32.GetLastError()}")
                    continue
        kernel32.CloseHandle(hDup)

kernel32.CloseHandle(hProc)
print(f"Hoàn thành: Đã đóng {closed_count} handles dangling trên vesta_snapshot.duckdb!")
