import struct
import liblzfse

from PIL import Image
from texture2ddecoder import decode_astc


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

    if glInternalFormat not in (0x93B0, 0x93B4, 0x93B7):
        raise TypeError('Unsupported texture format: {}'.format(hex(glInternalFormat)))

    if glInternalFormat == 0x93B0:
        block_width, block_height = 4, 4

    elif glInternalFormat == 0x93B4:
        block_width, block_height = 6, 6

    else:
        block_width, block_height = 8, 8

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

    decoded_data = decode_astc(image_data, pixelWidth, pixelHeight, block_width, block_height)
    return Image.frombytes('RGBA', (pixelWidth, pixelHeight), decoded_data, 'raw', ('BGRA'))
