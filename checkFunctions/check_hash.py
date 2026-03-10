import os
import hashlib
import sys


def calculate_md5(filepath, chunk_size=4096):
    md5_hash = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                md5_hash.update(chunk)
    except IOError as e:
        print(f"Ошибка при чтении файла {filepath}: {e}", file=sys.stderr)
        return None
    return md5_hash.hexdigest()


def get_file_map(directory):
    file_map = {}
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            relative_path = os.path.relpath(os.path.join(dirpath, filename), directory)
            file_map[relative_path] = os.path.join(dirpath, filename)
    return file_map


def compare_directories_by_hash(dir1, dir2):
    print(f"Сравнение директорий: '{dir1}' и '{dir2}'...")

    dir1_files = get_file_map(dir1)
    dir2_files = get_file_map(dir2)

    common_files = set(dir1_files.keys()) & set(dir2_files.keys())

    if not common_files:
        print("В директориях нет файлов с одинаковыми именами для сравнения.")
        return True

    for filename in sorted(list(common_files)):
        path1 = dir1_files[filename]
        path2 = dir2_files[filename]

        print(f"Сравнение файла: {filename}")

        hash1 = calculate_md5(path1)
        if hash1 is None:
            sys.exit(1)

        hash2 = calculate_md5(path2)
        if hash2 is None:
            sys.exit(1)

        if hash1 != hash2:
            print(f"ОШИБКА: Хэши файла '{filename}' не совпадают!")
            print(f"  {dir1}: {hash1}")
            print(f"  {dir2}: {hash2}")
            return False
    print("Все файлы с одинаковыми именами имеют совпадающие хэши.")
    return True


if __name__ == "__main__":
    dir_a = "/LogConf/config#1"
    dir_b = "/home/user/PycharmProjects/PythonProject5/LogConf/config#4"

    if not os.path.isdir(dir_a) or not os.path.isdir(dir_b):
        print("Обе указанные директории должны существовать.")
        sys.exit(1)

    if not compare_directories_by_hash(dir_a, dir_b):
        sys.exit(1)
