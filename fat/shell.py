from . import decoder


class FatShell:
    def __init__(self, decoder, file_tree):
        self.decoder = decoder
        self.tree = file_tree
        self.current_node = file_tree

    def run(self):
        while True:
            command: str = input(self.get_working_dir() + " $ ")
            clean_command = command.strip().split(sep=' ')
            if clean_command[0] == 'exit':
                break
            else:
                self.process_command(clean_command)

    def get_working_dir(self):
        wd = ''
        tmp_node = self.current_node
        while tmp_node.parent:
            wd += '/' + tmp_node.fat_file.name
            tmp_node = tmp_node.parent
        if not wd:
            wd = '/'
        return wd

    def process_command(self, command: list):
        if not command or not command[0]:
            return
        executable = command[0]
        if executable == 'cd':
            if self.validate_arg_count(executable, 1, len(command) - 1):
                self.change_dir(command[1])

        elif executable == 'cat':
            if self.validate_arg_count(executable, 1, len(command) - 1):
                self.print_file(command[1])

        elif executable == 'ls':
            if self.validate_arg_count(executable, 0, len(command) - 1):
                self.list_dir()

        else:
            print("command not found:", executable)

    @staticmethod
    def validate_arg_count(executable, required, actual) -> bool:
        if required != actual:
            if required > actual:
                print(executable + ': Not enough arguments')
            else:
                print(executable + ': Too many arguments')
            return False
        return True

    def change_dir(self, to):
        if to == '.':
            pass
        elif to == '..':
            if self.current_node.parent:
                self.current_node = self.current_node.parent
            else:
                print('cd: root')
        else:
            to_node = None
            for current_dir_entry in self.current_node.children:
                if to == current_dir_entry.fat_file.name or to == current_dir_entry.fat_file.full_name:
                    to_node = current_dir_entry
            if to_node:
                if to_node.is_directory():
                    self.current_node = to_node
                else:
                    print('cd: not a directory:', to)
            else:
                print('cd: no such file or directory:', to)

    def list_dir(self):
        for current_dir_entry in self.current_node.children:
            print(current_dir_entry.fat_file.name)

    def print_file(self, f):
        cat_node = None
        for current_dir_entry in self.current_node.children:
            if f == current_dir_entry.fat_file.name or f == current_dir_entry.fat_file.full_name:
                cat_node = current_dir_entry
        if cat_node:
            if not cat_node.is_directory():
                file_bytes = self.decoder.decode_file(cat_node.fat_file)
                print(file_bytes)
            else:
                print('cat: %s: is a directory:' % f)
        else:
            print('cat: No such file or directory')


def run(decoder, file_tree):
    FatShell(decoder, file_tree).run()


def decode_and_run(file):
    with open(file, 'rb') as reader:
        if not reader.seekable():
            print("File is not seekable!")
            exit(1)
        fat_decoder = decoder.FatDecoder()
        file_tree = fat_decoder.decode(reader)
        run(fat_decoder, file_tree)
