"""
校验和计算工具模块
====================

本模块提供 AUV 通信协议所需的校验和计算函数。

C# 源码参考：Form1.cs lines 139-162

主要函数：
1. calculate_byte_sum_checksum() - 字节和校验（WiFi/无线电数据包）
2. calculate_xor_checksum() - XOR 校验（北斗数据包）
3. hex_to_ascii() - 十六进制转 ASCII（CCTXA 编码）
4. ascii_to_hex() - ASCII 转十六进制（CCTXA 解码）
"""


def calculate_byte_sum_checksum(data: bytes) -> int:
    """
    计算字节和校验

    用于 WiFi 和无线电通信的 72/145 字节数据包。
    计算所有字节的和，取低 8 位作为校验值。

    Args:
        data (bytes): 要计算校验和的字节数组

    Returns:
        int: 校验值（0-255）

    示例：
        >>> data = bytes([0x01, 0x02, 0x03])
        >>> checksum = calculate_byte_sum_checksum(data)
        >>> print(f"校验和: {checksum:#04x}")  # 0x06
    """
    return sum(data) & 0xFF


def calculate_xor_checksum(data: bytes, length: int) -> int:
    """
    计算 XOR 校验和

    用于北斗卫星通信的数据包。
    对所有字节进行 XOR 运算得到校验值。

    C# 源码参考：Form1.cs Data_XOR() 函数, lines 148-162

    Args:
        data (bytes): 要计算校验的字节数组
        length (int): 要处理的字节数

    Returns:
        int: XOR 校验值

    示例：
        >>> data = bytes([0x01, 0x02, 0x03])
        >>> checksum = calculate_xor_checksum(data, 3)
        >>> print(f"XOR校验: {checksum:#04x}")  # 0x00
    """
    if len(data) == 0 or length == 0:
        return 0

    xor_value = data[0]
    for i in range(1, min(length, len(data))):
        xor_value ^= data[i]

    return xor_value


def hex_to_ascii(hex_byte: int) -> int:
    """
    将半字节（0-15）转换为 ASCII 字符

    用于 CCTXA 编码，将十六进制值转换为 ASCII 字符。
    例如：0x0A → 'A'，0x0F → 'F'

    C# 源码参考：Form1.cs HEX_to_ASCII() 函数, lines 139-147

    Args:
        hex_byte (int): 十六进制值（0-15）

    Returns:
        int: ASCII 字符编码

    转换规则：
        - 0-9  → 0x30-0x39 ('0'-'9')
        - 10-15 → 0x41-0x46 ('A'-'F')

    示例：
        >>> hex_to_ascii(0x0A)  # 返回 0x41 ('A')
        >>> hex_to_ascii(0x0F)  # 返回 0x46 ('F')
        >>> hex_to_ascii(0x09)  # 返回 0x39 ('9')
    """
    hex_byte = hex_byte & 0x0F  # 只取低 4 位

    if hex_byte <= 0x09:
        return hex_byte + 0x30  # '0'-'9' (0x30-0x39)
    else:
        return hex_byte + 0x37  # 'A'-'F' (0x41-0x46)


def ascii_to_hex(ascii_char: int) -> int:
    """
    将 ASCII 字符转换为半字节（hex_to_ascii 的逆操作）

    用于 CCTXA 解码，将 ASCII 字符转换为十六进制值。
    例如：'A' → 0x0A，'F' → 0x0F

    Args:
        ascii_char (int): ASCII 字符编码

    Returns:
        int: 十六进制值（0-15）

    转换规则：
        - '0'-'9' (0x30-0x39) → 0-9
        - 'A'-'F' (0x41-0x46) → 10-15
        - 'a'-'f' (0x61-0x66) → 10-15
        - 其他 → 0

    示例：
        >>> ascii_to_hex(0x41)  # 'A' → 10
        >>> ascii_to_hex(0x46)  # 'F' → 15
        >>> ascii_to_hex(0x39)  # '9' → 9
    """
    if 0x30 <= ascii_char <= 0x39:  # '0'-'9'
        return ascii_char - 0x30
    elif 0x41 <= ascii_char <= 0x46:  # 'A'-'F'
        return ascii_char - 0x37
    elif 0x61 <= ascii_char <= 0x66:  # 'a'-'f'
        return ascii_char - 0x57
    else:
        return 0
