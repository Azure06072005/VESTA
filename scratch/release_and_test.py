import ctypes
from ctypes import wintypes
import duckdb

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

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

DUPLICATE_CLOSE_SOURCE = 0x00000001
hProc = kernel32.OpenProcess(0x1FFFFF, False, 1756)

if not hProc:
    print(f"Could not open process 1756: {kernel32.GetLastError()}")
    exit(1)

# Close handle 0x6C4 in PID 1756
target_handle = 0x6C4
hDup = wintypes.HANDLE()
success = kernel32.DuplicateHandle(
    hProc,
    wintypes.HANDLE(target_handle),
    wintypes.HANDLE(0),
    ctypes.byref(hDup),
    0,
    False,
    DUPLICATE_CLOSE_SOURCE
)
err = kernel32.GetLastError()
print(f"DuplicateHandle DUPLICATE_CLOSE_SOURCE: success={success}, LastError={err}")
kernel32.CloseHandle(hProc)

# Now test opening db/vesta.duckdb
print("Testing DuckDB connection to db/vesta.duckdb...")
try:
    con = duckdb.connect("db/vesta.duckdb", read_only=True)
    cnt = con.execute("SELECT count(*) FROM duckdb_tables()").fetchone()[0]
    print(f"SUCCESS! Connected to db/vesta.duckdb! Table count: {cnt}")
    con.close()
except Exception as e:
    print(f"Failed to connect: {e}")
