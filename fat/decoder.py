import bitstring
import enum
import os


def decode(file):
    with open(file, 'rb') as reader:
        if not reader.seekable():
            print("File is not seekable!")
            exit(1)
        decoder = FatDecoder()
        print_file_tree(decoder.decode(reader))


class FatEntryStatus(enum.Enum):
    Free = 0
    Allocated = 1
    StrictReserved = 2
    Bad = 3
    Reserved = 4
    EOF = 5


FAT_CHAIN_TERMINAL = frozenset({FatEntryStatus.Reserved, FatEntryStatus.EOF})
FAT_FILE_DOT_DIR = frozenset({'.', '..'})


class FatDecoder:

    def __init__(self):
        self.bpb: BiosParameterBlock = None
        self.fat_clusters = {}
        self.file = None

    def decode(self, file):
        self.file = file
        stream = bitstring.BitStream(file)
        self.decode_boot_sector(stream)
        self.decode_fat(stream)
        return self.decode_data_region(file)

    def skip_sectors(self, stream, n=1):
        for i in range(n):
            stream.read('bytes:' + str(self.bpb.bytes_per_sector))

    def decode_boot_sector(self, stream: bitstring.BitStream):
        self.bpb = BiosParameterBlock()

        jmp, oem = stream.readlist(['bytes:3', 'bytes:8'])
        self.bpb.bytes_per_sector = stream.read('uintle:16')
        self.bpb.sectors_per_cluster = stream.read('uintle:8')
        self.bpb.reserved_sectors = stream.read('uintle:16')

        self.bpb.fats_count = stream.read('uintle:8')
        roots = stream.read('uintle:16')
        sectors = stream.read('uintle:16')
        self.bpb.media_descriptor = stream.read('bytes:1')
        sec_per_fat = stream.read('uintle:16')
        self.bpb.sec_per_track = stream.read('uintle:16')
        self.bpb.heads = stream.read('uintle:16')
        self.bpb.hidden_sectors = stream.read('uintle:32')

        self.bpb.sectors = stream.read('uintle:32')
        self.bpb.sec_per_fat = stream.read('uintle:32')

        active_fat, _, fat_is_mirrored, _ = stream.readlist([4, 2, 1, 9])
        fs_version = stream.read('uintle:16')
        self.bpb.root_cluster = stream.read('uintle:32')
        fs_info = stream.read('uintle:16')
        backup_boot_sector = stream.read('uintle:16')
        _, drive_num, _, boot_sig, volume_id, volume_label, fs_type = stream.readlist([
            'bytes:12', 'uintle:8', 'bytes:1', 'uintle:8', 'uintle:32', 'bytes:11', 'bytes:8'
        ])
        remaining_stuff = stream.read('bytes:' + str(self.bpb.bytes_per_sector - stream.bytepos))

        self.skip_sectors(stream, n=self.bpb.reserved_sectors - 1)

    def print_next(self, stream):
        stream.read('bytes:' + str(self.bpb.bytes_per_sector))

    def get_fat_entry_status(self, entry):
        if entry == 0:
            return FatEntryStatus.Free
        elif 2 <= entry <= self.bpb.maximum_valid_cluster_number():
            return FatEntryStatus.Allocated
        elif self.bpb.maximum_valid_cluster_number() + 1 <= entry <= 0xFFFFFF6:
            return FatEntryStatus.StrictReserved
        elif entry == 0xFFFFFF7:
            return FatEntryStatus.Bad
        elif 0xFFFFFF8 <= entry <= 0xFFFFFFE:
            return FatEntryStatus.Reserved
        elif entry == 0xFFFFFFF:
            return FatEntryStatus.EOF

    def get_cluster_chain_for_cluster(self, cluster):
        chain: list = []
        while self.get_fat_entry_status(cluster) not in FAT_CHAIN_TERMINAL:
            chain.append(cluster)
            cluster = self.fat_clusters[cluster]
        return chain

    def decode_fat(self, stream: bitstring.BitStream):
        entries_count = self.bpb.sec_per_fat * self.bpb.bytes_per_sector // 4

        for i in range(entries_count):
            entry = stream.read('uintle:32')
            if entry != 0:
                self.fat_clusters[i] = entry

        self.skip_sectors(stream, self.bpb.sec_per_fat)

    @staticmethod
    def decode_lfn_entry_name(stream):
        _, name, _, _, _, name_1, _, name_2 = stream.readlist(
            ['bytes:1', 'bytes:10', 'bytes:1', 'bytes:1', 'bytes:1', 'bytes:12', 'bytes:2', 'bytes:4'])
        # todo: maybe add checksum checking
        return name + name_1 + name_2

    @staticmethod
    def decode_normal_entry(entry_bytes):
        stream = bitstring.BitStream(bytes=entry_bytes)
        fat_file = FatFile()
        fat_file.name = stream.read('bytes:11').decode().strip()
        raw_attrs = stream.readlist(['2', '1', '1', '1', '1', '1', '1'])
        raw_attrs.reverse()
        fat_file.attrs = raw_attrs
        reserved = stream.read('bytes:1')
        fat_file.create_time = stream.read('uintle:24')
        fat_file.create_date = stream.read('uintle:16')
        fat_file.last_access_date = stream.read('uintle:16')
        zeros = stream.read('bytes:2')
        fat_file.last_modified_time = stream.read('uintle:16')
        fat_file.last_modified_date = stream.read('uintle:16')
        fat_file.first_cluster = stream.read('uintle:16')
        fat_file.file_size = stream.read('uintle:32')
        return fat_file

    def read_cluster_chain(self, file, chain: list):
        chain_bytes = b''
        for entry in chain:
            sector_start_byte = self.bpb.first_sector_of_cluster(entry) * self.bpb.bytes_per_sector
            file.seek(sector_start_byte, os.SEEK_SET)
            cluster_bytes = file.read(self.bpb.bytes_per_sector * self.bpb.sectors_per_cluster)
            chain_bytes += cluster_bytes
        return chain_bytes

    def decode_data_region(self, file):
        root_file_node = FileNode()
        for root_dir_entry in self.decode_dir(file, self.bpb.root_cluster):
            root_file_node.add_child(root_dir_entry)
        return root_file_node

    def decode_dir(self, file, cluster) -> list:
        dir_entries = []
        dir_cluster_chain = self.get_cluster_chain_for_cluster(cluster)
        dir_entries_count = len(dir_cluster_chain) * self.bpb.sectors_per_cluster * self.bpb.bytes_per_sector // 32
        dir_bytes = self.read_cluster_chain(file, dir_cluster_chain)

        stream = bitstring.BitStream(bytes=dir_bytes)

        i = 0
        while i < dir_entries_count:
            name = stream.read('bytes:11')
            attributes = stream.read('bytes:1')
            reserved = stream.read('bytes:1')

            first_byte = name[0]
            if first_byte == 0xe5:
                # deleted entry
                stream.read('bytes:' + str(32 - 13))
                i += 1
                continue
            elif first_byte == 0x00:
                # empty entry, end of entries here
                stream.read('bytes:' + str(32 - 13))
                break

            if attributes == b'\x0f':
                # lfn
                seq_num = first_byte
                name = name[1:]
                checksum = stream.read('uintle:8')
                name_ext = stream.read('bytes:12')
                cluster = stream.read('uintle:16')
                name_ext_2 = stream.read('bytes:4')
                seq_size = seq_num & 0b00111111

                full_name = bytearray(name + name_ext + name_ext_2).strip(b'\xff')[:-2]
                full_name.reverse()
                for seq_entry_idx in range(seq_size - 1):
                    full_name_chunk = bytearray(self.decode_lfn_entry_name(stream))
                    full_name_chunk.reverse()
                    full_name += full_name_chunk
                    i += 1
                full_name.reverse()

                fat_file = self.decode_normal_entry(stream.read('bytes:32'))
                fat_file.full_name = full_name.decode(encoding='utf-16')
                i += 1
            else:
                if first_byte == 0x05:
                    # initial character is e5
                    pass
                elif first_byte == 0x2e:
                    # dot
                    pass
                fat_file = self.decode_normal_entry(name + attributes + reserved + stream.read('bytes:' + str(32 - 13)))

            dir_entry_node = FileNode(fat_file)
            dir_entries.append(dir_entry_node)
            if dir_entry_node.is_directory() and not dir_entry_node.is_dot():
                subdir_entries = self.decode_dir(file, dir_entry_node.get_cluster())
                for subdir_entry in subdir_entries:
                    dir_entry_node.add_child(subdir_entry)
            i += 1

        return dir_entries

    def decode_file(self, fat_file):
        file_chain = self.get_cluster_chain_for_cluster(fat_file.first_cluster)
        file_cluster_bytes = self.read_cluster_chain(self.file, file_chain)
        return file_cluster_bytes[:fat_file.file_size]


class FileNode:
    def __init__(self, fat_file=None):
        self.fat_file: FatFile = fat_file
        self.children = []
        self.parent = None

    def is_directory(self):
        return self.fat_file.is_directory()

    def is_dot(self):
        return self.fat_file.name in FAT_FILE_DOT_DIR

    def get_cluster(self):
        return self.fat_file.first_cluster

    def add_child(self, node):
        node.parent = self
        self.children.append(node)


def print_file_tree(node: FileNode, indent=0):
    if node.fat_file:
        print('  ' * indent, '\u02ea', node.fat_file.name)
    else:
        print('\\')
    for child_node in node.children:
        print_file_tree(child_node, indent + 1)


class FatFile:
    def __init__(self):
        self.name = ''
        self.full_name = ''
        self.attrs = None
        self.create_time = None
        self.create_date = None
        self.last_access_date = None
        self.last_modified_time = None
        self.last_modified_date = None
        self.first_cluster = 0
        self.file_size = 0

    def is_directory(self):
        return self.attrs[4] != 0

    def __repr__(self):
        return "name: %s (full name: %s, attrs: %s, is_dir: %s, cluster:%s, size:%s)" % (
            self.name, self.full_name, self.attrs, self.is_directory(), self.first_cluster,
            self.file_size)


class BiosParameterBlock:
    def __init__(self):
        self.bytes_per_sector = 512
        self.sectors_per_cluster = 0
        self.reserved_sectors = 0
        self.fats_count = 0
        self.sectors = 0
        self.media_descriptor = 0
        self.sec_per_fat = 0
        self.sec_per_track = 0
        self.heads = 0
        self.hidden_sectors = 0
        self.root_cluster = 0

    def data_region_begin(self):
        return self.reserved_sectors + (self.fats_count * self.sec_per_fat)

    def first_sector_of_cluster(self, n):
        return ((n - 2) * self.sectors_per_cluster) + self.data_region_begin()

    def calc_cluster_fat_entry(self, n):
        return self.reserved_sectors + (n * 4 // self.bytes_per_sector), (n * 4) % self.bytes_per_sector

    def cluster_count(self):
        return (self.sectors - self.data_region_begin()) / self.sectors_per_cluster

    def maximum_valid_cluster_number(self):
        return self.cluster_count() + 1
