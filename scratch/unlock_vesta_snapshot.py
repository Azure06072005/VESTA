import ctypes
from ctypes import wintypes
import os
import psutil

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

target_pids = []
for p in psutil.process_iter(['pid', 'name']):
    if 'antigravity' in p.info['name'].lower() or 'python' in p.info['name'].lower():
        if p.info['pid'] != os.getpid():
            target_pids.append((p.info['pid'], p.info['name']))

print(f"Checking {len(target_pids)} processes for open handles on vesta_snapshot.duckdb...")

name_buf = ctypes.create_unicode_buffer(1024)
total_closed = 0

for pid, name in target_pids:
    hProc = kernel32.OpenProcess(0x1FFFFF, False, pid)
    if not hProc:
        continue
    
    for h in range(4, 65536, 4):
        hDup = wintypes.HANDLE()
        if kernel32.DuplicateHandle(hProc, wintypes.HANDLE(h), hCur, ctypes.byref(hDup), 0, False, 2):
            if kernel32.GetFileType(hDup) == 1:
                ret = kernel32.GetFinalPathNameByHandleW(hDup, name_buf, 1024, 0)
                if ret > 0:
                    p_path = name_buf.value
                    if "vesta_snapshot.duckdb" in p_path.lower():
                        print(f"Closing handle 0x{h:X} in PID {pid} ({name}) -> {p_path}")
                        hDummy = wintypes.HANDLE()
                        kernel32.DuplicateHandle(hProc, wintypes.HANDLE(h), wintypes.HANDLE(0), ctypes.byref(hDummy), 0, False, DUPLICATE_CLOSE_SOURCE)
                        total_closed += 1
            kernel32.CloseHandle(hDup)
    kernel32.CloseHandle(hProc)

print(f"Total closed handles: {total_closed}")
