import ctypes
from ctypes import wintypes
import sys

# Windows API constants
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
SystemExtendedHandleInformation = 64
ObjectTypeInformation = 2
ObjectNameInformation = 1

ntdll = ctypes.WinDLL("ntdll.dll")
kernel32 = ctypes.WinDLL("kernel32.dll")

class SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX(ctypes.Structure):
    _fields_ = [
        ("Object", ctypes.c_void_p),
        ("UniqueProcessId", ctypes.c_size_t),
        ("HandleValue", ctypes.c_size_t),
        ("GrantedAccess", wintypes.ULONG),
        ("CreatorBackTraceIndex", wintypes.USHORT),
        ("ObjectTypeIndex", wintypes.USHORT),
        ("HandleAttributes", wintypes.ULONG),
        ("Reserved", wintypes.ULONG),
    ]

# Let's inspect handles belonging to PID 20852
target_pid = 20852
hProcess = kernel32.OpenProcess(0x0040 | 0x0400, False, target_pid) # PROCESS_DUP_HANDLE | PROCESS_QUERY_INFORMATION
print("OpenProcess PID 20852:", hProcess)

# Query handle information
size = wintypes.ULONG(1024 * 1024 * 4)
buf = ctypes.create_string_buffer(size.value)
while True:
    status = ntdll.NtQuerySystemInformation(SystemExtendedHandleInformation, buf, size, ctypes.byref(size))
    status = status & 0xFFFFFFFF
    if status == 0:
        break
    elif status == STATUS_INFO_LENGTH_MISMATCH:
        size = wintypes.ULONG(size.value * 2)
        buf = ctypes.create_string_buffer(size.value)
    else:
        print(f"NtQuerySystemInformation failed with 0x{status:08X}")
        sys.exit(1)

# First size_t is NumberOfHandles
num_handles = ctypes.cast(buf, ctypes.POINTER(ctypes.c_size_t)).contents.value
print(f"Total system handles: {num_handles}")

entry_size = ctypes.sizeof(SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX)
offset = ctypes.sizeof(ctypes.c_size_t) * 2

matching_handles = []
for i in range(num_handles):
    entry = SYSTEM_HANDLE_TABLE_ENTRY_INFO_EX.from_buffer(buf, offset + i * entry_size)
    if entry.UniqueProcessId == target_pid:
        # Duplicate handle to query its name
        hTarget = wintypes.HANDLE()
        res = kernel32.DuplicateHandle(
            hProcess,
            wintypes.HANDLE(entry.HandleValue),
            kernel32.GetCurrentProcess(),
            ctypes.byref(hTarget),
            0,
            False,
            2 # DUPLICATE_SAME_ACCESS
        )
        if res:
            name_buf = ctypes.create_string_buffer(2048)
            ret_len = wintypes.ULONG()
            status = ntdll.NtQueryObject(hTarget, ObjectNameInformation, name_buf, 2048, ctypes.byref(ret_len))
            if status == 0:
                # Name is a UNICODE_STRING
                # Struct: USHORT Length, USHORT MaximumLength, PWSTR Buffer
                length = int.from_bytes(name_buf[0:2], "little")
                name_bytes = name_buf[8:8+length]
                try:
                    name_str = name_bytes.decode("utf-16le")
                    if "vesta" in name_str.lower():
                        print(f"Found handle in PID {target_pid}: 0x{entry.HandleValue:X} -> {name_str}")
                        matching_handles.append(entry.HandleValue)
                except Exception:
                    pass
            kernel32.CloseHandle(hTarget)

print(f"Total matching handles for vesta in PID {target_pid}: {len(matching_handles)}")
