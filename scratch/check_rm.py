import ctypes
from ctypes import wintypes
import os

ntdll = ctypes.WinDLL("ntdll.dll")
kernel32 = ctypes.WinDLL("kernel32.dll")

PROCESS_DUP_HANDLE = 0x0040
PROCESS_QUERY_INFORMATION = 0x0400
DUPLICATE_CLOSE_SOURCE = 0x00000001
DUPLICATE_SAME_ACCESS = 0x00000002

class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]

# Try checking if handle can be unlocked
def find_and_close_lock(target_pid, filename_sub):
    # We can use Windows Restart Manager API (RmStartSession, RmRegisterResources, RmGetList)
    # This is the OFFICIAL Microsoft Windows API to release files locked by processes!
    rstrtmgr = ctypes.WinDLL("rstrtmgr.dll")
    
    session_handle = wintypes.DWORD()
    session_key = (wintypes.WCHAR * 256)()
    
    res = rstrtmgr.RmStartSession(ctypes.byref(session_handle), 0, session_key)
    print("RmStartSession result:", res)
    if res != 0:
        return
        
    try:
        file_paths = (wintypes.LPCWSTR * 1)(r"D:\VESTA\db\vesta_snapshot.duckdb")
        res = rstrtmgr.RmRegisterResources(session_handle, 1, file_paths, 0, None, 0, None)
        print("RmRegisterResources result:", res)
        
        proc_info_needed = wintypes.DWORD()
        proc_info = (wintypes.BYTE * 1024)()
        reboot_reasons = wintypes.DWORD()
        
        res = rstrtmgr.RmGetList(
            session_handle,
            ctypes.byref(proc_info_needed),
            ctypes.byref(proc_info_needed),
            proc_info,
            ctypes.byref(reboot_reasons)
        )
        print(f"RmGetList result: {res}, procs needed: {proc_info_needed.value}")
    finally:
        rstrtmgr.RmEndSession(session_handle)

find_and_close_lock(20852, "vesta_snapshot")
