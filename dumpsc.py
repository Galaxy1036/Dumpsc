import os
import lzma
import lzham
import struct
import argparse
import zstandard

from PIL import Image
from ktx import load_ktx


def convert_pixel(pixel, type):
    if type == 0 or type == 1:
        # RGB8888
        return struct.unpack('4B', pixel)
    elif type == 2:
        # RGB4444
        pixel, = struct.unpack('<H', pixel)
        return (((pixel >> 12) & 0xF) << 4, ((pixel >> 8) & 0xF) << 4,
                ((pixel >> 4) & 0xF) << 4, ((pixel >> 0) & 0xF) << 4)
    elif type == 3:
        # RBGA5551
        pixel, = struct.unpack('<H', pixel)
        return (((pixel >> 11) & 0x1F) << 3, ((pixel >> 6) & 0x1F) << 3,
                ((pixel >> 1) & 0x1F) << 3, ((pixel) & 0xFF) << 7)
    elif type == 4:
        # RGB565
        pixel, = struct.unpack("<H", pixel)
        return (((pixel >> 11) & 0x1F) << 3, ((pixel >> 5) & 0x3F) << 2, (pixel & 0x1F) << 3)
    elif type == 6:
        # LA88 = Luminance Alpha 88
        pixel, = struct.unpack("<H", pixel)
        return (pixel >> 8), (pixel >> 8), (pixel >> 8), (pixel & 0xFF)
    elif type == 10:
        # L8 = Luminance8
        pixel, = struct.unpack("<B", pixel)
        return pixel, pixel, pixel
    elif type == 15:
        raise NotImplementedError("Pixel type 15 is not supported")
    else:
        raise Exception("Unknown pixel type {}.".format(type))


def process_sc(baseName, data, path, decompress):
    if decompress:
        version = None

        if data[:2] == b'SC':
            # Skip the header if there's any
            pre_version = int.from_bytes(data[2: 6], 'big')

            if pre_version == 4:
                version = int.from_bytes(data[6: 10], 'big')
                hash_length = int.from_bytes(data[10: 14], 'big')
                end_block_size = int.from_bytes(data[-4:], 'big')

                data = data[14 + hash_length:-end_block_size - 9]

            else:
                version = pre_version
                hash_length = int.from_bytes(data[6: 10], 'big')
                data = data[10 + hash_length:]

        if version in (None, 1, 3):
            try:
                if data[:4] == b'SCLZ':
                    print('[*] Detected LZHAM compression !')

                    dict_size = int.from_bytes(data[4:5], 'big')
                    uncompressed_size = int.from_bytes(data[5:9], 'little')
                    decompressed = lzham.decompress(data[9:], uncompressed_size, {'dict_size_log2': dict_size})

                elif data[:4] == bytes.fromhex('28 B5 2F FD'):
                    print('[*] Detected Zstandard compression !')
                    decompressed = zstandard.decompress(data)

                else:
                    print('[*] Detected LZMA compression !')
                    data = data[0:9] + (b'\x00' * 4) + data[9:]
                    decompressor = lzma.LZMADecompressor()

                    output = []

                    while decompressor.needs_input:
                        output.append(decompressor.decompress(data))

                    decompressed = b''.join(output)

            except Exception as _:
                print('Cannot decompress {} !'.format(baseName))
                return

        else:
            decompressed = data

    else:
        decompressed = data

    i = 0
    picCount = 0
    while len(decompressed[i:]) > 5:
        fileType, = struct.unpack('<b', bytes([decompressed[i]]))

        if fileType == 0x2D:
            i += 4  # Ignore this uint32, it's basically the fileSize + the size of subType + width + height (9 bytes)

        fileSize, = struct.unpack('<I', decompressed[i + 1:i + 5])
        subType, = struct.unpack('<b', bytes([decompressed[i + 5]]))
        width, = struct.unpack('<H', decompressed[i + 6:i + 8])
        height, = struct.unpack('<H', decompressed[i + 8:i + 10])
        i += 10

        print('fileType: {}, fileSize: {}, subType: {}, width: {}, '
              'height: {}'.format(fileType, fileSize, subType, width, height))

        if fileType != 0x2D:
            if subType in (0, 1):
                pixelSize = 4
            elif subType in (2, 3, 4, 6):
                pixelSize = 2
            elif subType == 10:
                pixelSize = 1
            elif subType != 15:
                raise Exception("Unknown pixel type {}.".format(subType))

            if subType == 15:
                ktx_size, = struct.unpack('<I', decompressed[i:i + 4])
                img = load_ktx(decompressed[i + 4: i + 4 + ktx_size])
                i += 4 + ktx_size

            else:
                img = Image.new("RGBA", (width, height))
                pixels = []

                for y in range(height):
                    for x in range(width):
                        pixels.append(convert_pixel(decompressed[i:i + pixelSize], subType))
                        i += pixelSize

                img.putdata(pixels)

            if fileType == 29 or fileType == 28 or fileType == 27:
                imgl = img.load()
                iSrcPix = 0

                for l in range(height // 32):  # block of 32 lines
                    # normal 32-pixels blocks
                    for k in range(width // 32):  # 32-pixels blocks in a line
                        for j in range(32):  # line in a multi line block
                            for h in range(32):  # pixels in a block
                                imgl[h + (k * 32), j + (l * 32)] = pixels[iSrcPix]
                                iSrcPix += 1
                    # line end blocks
                    for j in range(32):
                        for h in range(width % 32):
                            imgl[h + (width - (width % 32)), j + (l * 32)] = pixels[iSrcPix]
                            iSrcPix += 1
                # final lines
                for k in range(width // 32):  # 32-pixels blocks in a line
                    for j in range(height % 32):  # line in a multi line block
                        for h in range(32):  # pixels in a 32-pixels-block
                            imgl[h + (k * 32), j + (height - (height % 32))] = pixels[iSrcPix]
                            iSrcPix += 1
                # line end blocks
                for j in range(height % 32):
                    for h in range(width % 32):
                        imgl[h + (width - (width % 32)), j + (height - (height % 32))] = pixels[iSrcPix]
                        iSrcPix += 1

        else:
            img = load_ktx(decompressed[i:i + fileSize])
            i += fileSize

        img.save(path + baseName + ('_' * picCount) + '.png', 'PNG')
        picCount += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract png files from Supercell "*_tex.sc" files')
    parser.add_argument('files', help='sc file', nargs='+')
    parser.add_argument('-o', help='Extract pngs to directory', type=str)
    parser.add_argument('-d', '--decompress', help='Try to decompress _tex.sc before processing it', action='store_true')

    args = parser.parse_args()

    if args.o:
        path = os.path.normpath(args.o) + '/'

    else:
        path = os.path.dirname(os.path.realpath(__file__)) + '/'

    for file in args.files:
        if file.endswith('tex.sc'):
            basename, _ = os.path.splitext(os.path.basename(file))

            with open(file, 'rb') as f:
                print('[*] Processing {}'.format(f.name))
                process_sc(basename, f.read(), path, args.decompress)

        else:
            print('[*] Only tex.sc are supported !')
