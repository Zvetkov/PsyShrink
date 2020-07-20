import logging
import sys
import os
from utils.game_path import WORKING_DIRECTORY


DESKTOP_PATH = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')
ARCHIVE_PATH_REPACKAGE = os.path.join(DESKTOP_PATH, "Psychonautsdata2.pkg_re")

ARCHIVE_PATH_PKG = "Psychonautsdata2.pkg_orig"
ARCHIVE_PATH_PPF = "WorkResource/PCLevelPackFiles/ASCO.ppf"

NULL = b"\x00"


def main():
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(asctime)s][%(levelname)s]: %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p')
    # replace_texture(os.path.join(WORKING_DIRECTORY, ARCHIVE_PATH_PKG))
    replace_texture(os.path.join(WORKING_DIRECTORY, ARCHIVE_PATH_PPF))


class PKGArchive(object):
    def __init__(self, archive_raw):
        self.raw = archive_raw
        self.header = archive_raw[0:4]
        self.version = byte_to_int(archive_raw[4:8])
        self.end_of_listings_offset = byte_to_int(archive_raw[8:12])
        self.num_of_files = byte_to_int(archive_raw[12:16])
        self.file_descriptions_offset = 512
        self.file_data_offset = 524288
        self.dir_records_offset = byte_to_int(archive_raw[16:20])
        self.num_of_dir_records = byte_to_int(archive_raw[20:24])
        self.filename_list_offset = byte_to_int(archive_raw[24:28])
        self.extension_list_offset = byte_to_int(archive_raw[28:32])

        self.file_descriptions_list = []
        self.dir_record_list = []

        file_desc_chunk_size = 16
        dir_record_chunk_size = 12

        current_offset = self.file_descriptions_offset

        file_index = 0

        while current_offset < self.dir_records_offset:
            new_file = ArchiveFile(archive_raw[current_offset:current_offset + file_desc_chunk_size])
            self.file_descriptions_list.append(new_file)
            new_file.file_index = file_index
            file_index += 1
            current_offset += file_desc_chunk_size

        if file_index != self.num_of_files:
            logging.warn("Files read from archive count is not the same as specified in archive header!\n"
                         f"Files specified in header: '{self.num_of_files}'\n Files read from archive: '{file_index}'")

        if current_offset != self.dir_records_offset:
            logging.warn("Not at the start of the dir records, after parsing all of the file description chunks!")

        while current_offset < self.filename_list_offset:
            new_file = ArchiveDirRecord(archive_raw[current_offset:current_offset
                                                    + dir_record_chunk_size], current_offset)
            self.dir_record_list.append(new_file)
            current_offset += dir_record_chunk_size

        if current_offset != self.filename_list_offset:
            logging.warn("Not at the start of FilenameDir after parsing all of the Dir2 chunks!")

        file_names_raw = archive_raw[self.filename_list_offset + 1:self.extension_list_offset - 1]
        extensions_raw = archive_raw[self.extension_list_offset + 1:self.end_of_listings_offset - 1]

        self.filename_list = file_names_raw.split(NULL)
        self.extension_list = extensions_raw.split(NULL)
        file_name_dict = {}
        extension_dict = {}

        offset = 1
        for file_name in self.filename_list:
            file_name_dict[offset] = file_name.decode("utf-8")
            offset += len(file_name) + 1  # plus delimeter size

        offset = 1
        for extension in self.extension_list:
            extension_dict[offset] = extension.decode("utf-8")
            offset += len(extension) + 1  # plus delimeter size

        for archive_file in self.file_descriptions_list:
            archive_file.name = file_name_dict[archive_file.file_name_offset_relative]
            archive_file.extension = extension_dict[archive_file.file_extension_offset_relative]
            archive_file.data = \
                archive_raw[archive_file.file_offset:archive_file.file_offset + archive_file.file_length]

        self.dir_name_dict = {}
        current_dir_name = b"//"
        dir_records = []
        all_link_1 = {}
        all_link_2 = {}
        all_records = {}
        for i in range(len(self.dir_record_list)):
            record = self.dir_record_list[i]
            all_records[record.record_id] = record

            if record.link_1 != 0:
                all_link_1[record.record_id] = record
                if current_dir_name:
                    self.dir_record_list[record.link_1].char_dir_name = \
                        current_dir_name + self.dir_record_list[record.link_1].char_dir_name
                else:
                    self.dir_record_list[record.link_1].char_dir_name = \
                        record.char_dir_name[0:-1] + self.dir_record_list[record.link_1].char_dir_name

            if record.link_2 != 0:
                all_link_2[record.record_id] = record
                if current_dir_name:
                    self.dir_record_list[record.link_2].char_dir_name = \
                        current_dir_name + self.dir_record_list[record.link_2].char_dir_name
                else:
                    self.dir_record_list[record.link_2].char_dir_name = \
                        record.char_dir_name[0:-1] + self.dir_record_list[record.link_2].char_dir_name

            current_dir_name += record.char_dir_name

            dir_records.append(record)
            if record.start_index != 0 or record.end_index != 0:
                self.dir_name_dict[current_dir_name.strip(b"//").decode("utf-8")] = \
                    {"start_index": record.start_index,
                     "end_index": record.end_index,
                     "records": dir_records}
                for record in dir_records:
                    record.of_directory = current_dir_name
                if i < self.num_of_dir_records - 1 and b"//" in self.dir_record_list[i + 1].char_dir_name:
                    current_dir_name = b""
                dir_records = []

    def recalculate_file_offsets(self):
        self.file_descriptions_list.sort(key=lambda x: x.file_offset, reverse=False)
        current_offset = self.file_data_offset
        for i in range(len(self.file_descriptions_list)):
            file_entry = self.file_descriptions_list[i]
            file_entry.file_length = len(file_entry.data)
            file_entry.orig_file_offset = file_entry.file_offset
            file_entry.file_offset = current_offset
            current_offset += file_entry.file_length
            if file_entry.extension == "jan" and file_entry.file_length % 512 != 0:
                file_entry.padding_size = 512 - (file_entry.file_length % 512)
            if file_entry.padding_size != 0:
                current_offset += file_entry.padding_size

    def unpack(self, target_path):
        create_dir_structure(os.path.join(target_path, "unpack"), self.dir_name_dict.keys())
        self.save_all_files(os.path.join(target_path, "unpack"))

    def save_all_files(self, root_path):
        files_dict = {}
        for file_entry in self.file_descriptions_list:
            files_dict[file_entry.file_index] = file_entry
        for relative_path in self.dir_name_dict.keys():
            full_path = os.path.join(root_path, relative_path)
            for file_index in range(self.dir_name_dict[relative_path]["start_index"],
                                    self.dir_name_dict[relative_path]["end_index"]):
                save_file_to_path(full_path, files_dict[file_index])

    def repackage(self, save_path):
        with open(r"C:\Users\Seel\Desktop\ca_load.dds", 'rb') as f:
            dds_new = f.read()
            self.file_descriptions_list[13125].data = dds_new
        self.recalculate_file_offsets()
        archive_header = (self.header
                          + int_to_byte(self.version)
                          + int_to_byte(self.end_of_listings_offset)
                          + int_to_byte(self.num_of_files)
                          + int_to_byte(self.dir_records_offset)
                          + int_to_byte(self.num_of_dir_records)
                          + int_to_byte(self.filename_list_offset)
                          + int_to_byte(self.extension_list_offset))
        padding = (512 - len(archive_header)) * NULL
        archive_header += padding

        file_descriptions = b""

        self.file_descriptions_list.sort(key=lambda x: x.file_index, reverse=False)
        for file_entry in self.file_descriptions_list:
            file_desc_bytes = (NULL
                               + int_to_byte(file_entry.file_extension_offset_relative, 2)
                               + NULL
                               + int_to_byte(file_entry.file_name_offset_relative)
                               + int_to_byte(file_entry.file_offset)
                               + int_to_byte(file_entry.file_length))
            file_descriptions += file_desc_bytes

        dir_records = b""
        for record in self.dir_record_list:
            record_bytes = (record.char_dir_name[-1:]
                            + NULL
                            + int_to_byte(record.link_1, 2)
                            + int_to_byte(record.link_2, 2)
                            + int_to_byte(record.record_id, 2)
                            + int_to_byte(record.start_index, 2)
                            + int_to_byte(record.end_index, 2))
            dir_records += record_bytes

        filenames = NULL
        for filename in self.filename_list:
            filenames += filename + NULL

        extensions = NULL
        for extension in self.extension_list:
            extensions += extension + NULL

        struct_info = (archive_header
                       + file_descriptions
                       + dir_records
                       + filenames
                       + extensions)

        file_padding = (self.file_data_offset - self.end_of_listings_offset) * NULL

        # self.file_descriptions_list.sort(key=lambda x: x.file_offset, reverse=False)
        self.block_sizes = {}
        self.block_sizes_no_pad = {}
        with open(save_path, "wb") as f:
            f.write(struct_info + file_padding)

        self.file_descriptions_list.sort(key=lambda x: x.file_offset, reverse=False)
        with open(save_path, "ab") as f:
            for file_entry in self.file_descriptions_list:
                f.write(file_entry.data)
                if file_entry.padding_size != 0:
                    f.write(b"\x00" * file_entry.padding_size)


class PPFArchive(object):
    def __init__(self, archive_raw):
        self.raw = archive_raw
        self.header = archive_raw[0:4]

    def unpack(self, target_path):
        pass

    def repackage(self, save_path):
        pass


class ArchiveFile(object):
    def __init__(self, bytes_raw):
        self.file_extension_offset_relative = byte_to_int(bytes_raw[1:3])
        self.file_name_offset_relative = byte_to_int(bytes_raw[4:8])
        self.file_offset = byte_to_int(bytes_raw[8:12])
        self.file_length = byte_to_int(bytes_raw[12:16])
        self.name: str
        self.extension: str
        self.data: bytes
        self.file_index: int
        self.padding_size = 0


class ArchiveDirRecord(object):
    def __init__(self, bytes_raw, offset):
        self.offset = offset
        self.char_dir_name = bytes_raw[0:1]

        self.link_1 = byte_to_int(bytes_raw[2:4])

        self.link_2 = byte_to_int(bytes_raw[4:6])
        self.link_2_1 = byte_to_int(bytes_raw[4:5])
        self.link_2_2 = byte_to_int(bytes_raw[5:6])

        self.record_id = byte_to_int(bytes_raw[6:8])
        self.start_index = byte_to_int(bytes_raw[8:10])
        self.end_index = byte_to_int(bytes_raw[10:12])
        self.of_directory = None


def replace_texture(path_to_archive: str):
    pkg = read_archive(path_to_archive)
    # pkg.unpack(DESKTOP_PATH)
    pkg.repackage(ARCHIVE_PATH_REPACKAGE)
    # pkg_2 = read_archive(ARCHIVE_PATH_REPACKAGE)
    a = 1


def read_archive(path_to_archive: str):
    logging.debug(f"Opening archive: '{path_to_archive}'")
    with open(path_to_archive, 'rb') as f:
        archive_file = f.read()
        if archive_file[:4] == b"ZPKG":
            pkg = PKGArchive(archive_file)
        elif archive_file[:4] == b"PPAK":
            pkg = PPFArchive(archive_file)
    return pkg


def byte_to_int(hex_byte_str: bytearray):
    return int.from_bytes(hex_byte_str, byteorder="little")


def int_to_byte(num: int, length: int = 4):
    return num.to_bytes(length, byteorder="little")


def save_file_to_path(save_path, archive_file: ArchiveFile):
    path_to_file = os.path.join(save_path, f"{archive_file.name}.{archive_file.extension}")
    with open(path_to_file, 'wb') as f:
        f.write(archive_file.data)


def create_dir_structure(root_path, path_list):
    for relative_path in path_list:
        full_path = os.path.join(root_path, relative_path)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        else:
            logging.debug(f"Trying to create path '{full_path}' when it's already exists")


def compare_bytearrays(byte_array_1, byte_array_2, size):
    return byte_array_1[0:size] == byte_array_2[0:size]


if __name__ == "__main__":
    sys.exit(main())
