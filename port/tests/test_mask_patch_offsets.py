from paths import ROOT
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(ROOT / 'scripts'))
import mod_patches


class MaskPatchOffsets(unittest.TestCase):
    def line(self, **attrs):
        return ET.Element('Line', {'Type': 'mask', 'Address': '55 48 ?? E5',
                                   'Value': 'C3', **attrs})

    def test_zero_based_elf_match_is_image_relative(self):
        offset, data = mod_patches._compile_mask(
            self.line(), [(0, b'\x90' * 32 + bytes.fromhex('55 48 89 E5'))])
        self.assertEqual((offset, data), (32, b'\xc3'))

    def test_match_keeps_virtual_address_and_relative_adjustment(self):
        offset, _ = mod_patches._compile_mask(
            self.line(Offset='2'), [(0x5073B0, bytes.fromhex('55 48 89 E5'))])
        self.assertEqual(offset, 0x5073B2)

    def test_mask_write_reaches_matched_instruction(self):
        meta = ET.fromstring('<Metadata><PatchList><Line Type="mask" '
                             'Address="55 48 ?? E5" Value="C3"/></PatchList></Metadata>')
        # Construct a small ELF with an executable PT_LOAD segment based at zero.
        import struct
        elf = bytearray(0x140)
        struct.pack_into('<Q', elf, 0x20, 0x40)
        struct.pack_into('<HH', elf, 0x36, 56, 1)
        struct.pack_into('<IIQQQQQQ', elf, 0x40, 1, 5, 0x100, 0, 0, 64, 64, 1)
        elf[0x120:0x124] = bytes.fromhex('55 48 89 E5')
        writes = mod_patches.compile_external([('intro', None, meta)], [(0, 64)], elf)
        self.assertEqual([(o, d) for o, d, _ in writes], [(32, b'\xc3')])

    def test_literal_external_address_still_subtracts_cheat_base(self):
        meta = ET.fromstring('<Metadata><PatchList><Line Type="bytes" '
                             'Address="0x400020" Value="C3"/></PatchList></Metadata>')
        writes = mod_patches.compile_external([('literal', None, meta)], [(0, 64)])
        self.assertEqual([(o, d) for o, d, _ in writes], [(32, b'\xc3')])


if __name__ == '__main__':
    unittest.main()
