# fatty

### Overview 
Simple tool for decoding and traversing FAT32 images in bash fashion.
Does not hold whole image in memory and supports Long File Names.

### Install
```
pip3 install -r requirements.txt
```

### Usage
- Print file tree
```
./read_fat.py [fat_image]
```
- Launch interactive shell
```
./read_fat.py [fat_image] -i
```

