"""
Beidou satellite communication protocol
C# Reference: Form1.cs CCTXA() function, lines 168-223
"""

from .checksums import calculate_xor_checksum, hex_to_ascii
from .constants import BEIDOU_DEST_ADDRESS


class BeidouProtocol:
    """Handle Beidou CCTXA protocol encoding"""

    @staticmethod
    def build_cctxa_packet(bw_data: bytes) -> bytes:
        """
        Build CCTXA command packet for Beidou communication
        Format: $CCTXA,0989565,1,2,A4<data>*checksum\r\n

        Args:
            bw_data: Binary data to encode (max 34 bytes for Beidou)

        Returns:
            ASCII-encoded CCTXA packet ready for serial transmission
        """
        cctxa = bytearray(256)

        # Packet header: $CCTXA,
        cctxa[0:7] = b'$CCTXA,'

        # Destination IC number (7 digits decimal) - fixed to 0989564
        dest_num = 0x0989564
        for i in range(7):
            cctxa[7 + i] = ((dest_num // (10**(6 - i))) % 10) + ord('0')

        cctxa[14] = ord(',')
        cctxa[15] = ord('1')
        cctxa[16] = ord(',')
        cctxa[17] = ord('2')
        cctxa[18] = ord(',')
        cctxa[19] = ord('A')
        cctxa[20] = ord('4')

        # Data payload - encode each byte as 2 ASCII hex characters
        len_bw = len(bw_data)
        for i in range(len_bw):
            high_nibble = (bw_data[i] >> 4) & 0x0F
            low_nibble = bw_data[i] & 0x0F
            cctxa[21 + i * 2] = hex_to_ascii(high_nibble)
            cctxa[22 + i * 2] = hex_to_ascii(low_nibble)

        # Calculate XOR checksum (excluding leading $)
        crc_data_start = 1  # Skip '$'
        crc_data_end = 20 + len_bw * 2
        crc_data = bytes(cctxa[crc_data_start:crc_data_end])
        checksum = calculate_xor_checksum(crc_data, len(crc_data))

        # Append checksum
        cctxa[crc_data_end] = ord('*')
        cctxa[crc_data_end + 1] = hex_to_ascii((checksum >> 4) & 0x0F)
        cctxa[crc_data_end + 2] = hex_to_ascii(checksum & 0x0F)
        cctxa[crc_data_end + 3] = 0x0D  # CR
        cctxa[crc_data_end + 4] = 0x0A  # LF

        return bytes(cctxa[:crc_data_end + 5])

    @staticmethod
    def parse_bdtxr_packet(packet: bytes) -> bytes:
        """
        Parse BDTXR format packet from Beidou
        Format: $BDTXR,...*checksum\r\n with ASCII hex encoded data

        Args:
            packet: Raw BDTXR packet

        Returns:
            Decoded binary data
        """
        try:
            # Verify packet starts with $BDTXR
            if not packet.startswith(b'$BDTXR,'):
                return None

            # Find data section (after $BDTXR,ICNUM,1,2,A4)
            parts = packet.split(b',')
            if len(parts) < 5:
                return None

            # Data is in part 4 (after A4)
            hex_data = parts[4][2:]  # Skip 'A4' prefix

            # Verify checksum
            checksum_parts = parts[5].split(b'*')
            if len(checksum_parts) < 2:
                return None

            received_checksum_str = checksum_parts[1][:2]
            # TODO: Verify checksum

            # Convert ASCII hex back to binary
            binary_data = bytearray()
            for i in range(0, len(hex_data) - 1, 2):
                high_char = hex_data[i]
                low_char = hex_data[i + 1]

                # Convert ASCII to hex nibbles
                if 0x30 <= high_char <= 0x39:
                    high = high_char - 0x30
                elif 0x41 <= high_char <= 0x46:
                    high = high_char - 0x37
                elif 0x61 <= high_char <= 0x66:
                    high = high_char - 0x57
                else:
                    high = 0

                if 0x30 <= low_char <= 0x39:
                    low = low_char - 0x30
                elif 0x41 <= low_char <= 0x46:
                    low = low_char - 0x37
                elif 0x61 <= low_char <= 0x66:
                    low = low_char - 0x57
                else:
                    low = 0

                byte_val = (high << 4) | low
                binary_data.append(byte_val)

            return bytes(binary_data)

        except Exception as e:
            print(f"Error parsing BDTXR packet: {e}")
            return None
