import os
import lzma
import lzham
import struct
import argparse
import zstandard

from PIL import Image


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
    else:
        raise Exception("Unknown pixel type {}.".format(type))


def process_sc(baseName, data, path, decompress):
    if decompress:
        version = None

        if data[:2] == b'SC':
            # Skip the header if there's any
            version = int.from_bytes(data[2: 6], 'big')
            hash_length = int.from_bytes(data[6: 10], 'big')
            data = data[10 + hash_length:]

        if version in (None, 1, 3):  # Version 2 in HDP does not use any compression
            if data[:4] == b'SCLZ':
                print('[*] Detected LZHAM compression !')

                dict_size = int.from_bytes(data[4:5], 'big')
                uncompressed_size = int.from_bytes(data[5:9], 'little')

                try:
                    decompressed = lzham.decompress(data[9:], uncompressed_size, {'dict_size_log2': dict_size})

                except Exception as exception:
                    print('Cannot decompress {} !'.format(baseName))
                    return

            elif data[:4] == bytes.fromhex('28 B5 2F FD'):
                print('[*] Detected Zstandard compression !')

                try:
                    decompressed = zstandard.decompress(data)

                except Exception as exception:
                    print('Cannot decompress {} !'.format(baseName))
                    return

            else:
                print('[*] Detected LZMA compression !')
                data = data[0:9] + (b'\x00' * 4) + data[9:]

                try:
                    decompressed = lzma.LZMADecompressor().decompress(data)

                except Exception as exception:
                    print('Cannot decompress {} !'.format(baseName))
                    return

            print('[*] Successfully decompressed {} !'.format(baseName))

        else:
            decompressed = data

    else:
        decompressed = data

    i = 0
    picCount = 0
    while len(decompressed[i:]) > 5:
        fileType, = struct.unpack('<b', bytes([decompressed[i]]))
        fileSize, = struct.unpack('<I', decompressed[i + 1:i + 5])
        subType, = struct.unpack('<b', bytes([decompressed[i + 5]]))
        width, = struct.unpack('<H', decompressed[i + 6:i + 8])
        height, = struct.unpack('<H', decompressed[i + 8:i + 10])
        i += 10

        if subType in (0, 1):
            pixelSize = 4
        elif subType in (2, 3, 4, 6):
            pixelSize = 2
        elif subType == 10:
            pixelSize = 1
        else:
            raise Exception("Unknown pixel type {}.".format(subType))

        print('fileType: {}, fileSize: {}, subType: {}, width: {}, '
              'height: {}'.format(fileType, fileSize, subType, width, height))

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
