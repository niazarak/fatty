import unittest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             os.path.pardir))
from fat import FatDecoder


class TestDecoder(unittest.TestCase):

    def setUp(self):
        self.decoder = FatDecoder()

    def test_decoder(self):
        with open('tests/files/file.fs', 'rb') as test_file:
            tree = self.decoder.decode(test_file)


if __name__ == '__main__':
    unittest.main()
