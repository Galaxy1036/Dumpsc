import struct
import astc_decomp
import liblzfse

from PIL import Image


def load_ktx(data):
    header = data[:64]
    ktx_data = data[64:]

    if header[12:16] == bytes.fromhex('01020304'):
        endianness = '<'

    else:
        endianness = '>'

    if header[0:7] != b'\xabKTX 11':
        raise TypeError('Unsupported or unknown KTX version: {}'.format(header[0:7]))

    glInternalFormat, = struct.unpack(endianness + 'I', header[28:32])
    pixelWidth, pixelHeight = struct.unpack(endianness + '2I', header[36:44])
    bytesOfKeyValueData, = struct.unpack(endianness + 'I', header[60:64])

    if glInternalFormat != 0x93B0:
        raise TypeError('Unsupported texture format: 0x{}'.format(hex(glInternalFormat)))

    key_value_data = ktx_data[:bytesOfKeyValueData]
    ktx_data = ktx_data[bytesOfKeyValueData:]

    if b'Compression_APPLE' in key_value_data:
        if ktx_data[12:15] == b'bvx':
            image_data = liblzfse.decompress(ktx_data[12:])

        else:
            raise ValueError('Unsupported compression type: {}'.format(
                ktx_data[12:15])
            )

    else:
        image_data = ktx_data[4:]

    return Image.frombytes('RGBA', (pixelWidth, pixelHeight), image_data, 'astc', (4, 4, False))