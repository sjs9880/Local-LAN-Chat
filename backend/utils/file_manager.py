import hashlib
import os
import time
import zipfile


class BandwidthThrottler:
    """Limit outbound transfer speed in bytes/sec."""

    def __init__(self, limit_bytes_per_sec: int):
        self.limit = limit_bytes_per_sec
        self.tokens = float(limit_bytes_per_sec)
        self.last_update = time.time()

    def wait_for_tokens(self, amount: int):
        if self.limit <= 0:
            return

        while True:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now

            self.tokens += elapsed * self.limit
            if self.tokens > self.limit:
                self.tokens = self.limit

            if self.tokens >= amount:
                self.tokens -= amount
                return

            needed = amount - self.tokens
            sleep_time = needed / self.limit
            time.sleep(sleep_time)


class FileManager:
    @staticmethod
    def prepare_transfer(paths: list[str], output_zip_path: str = "temp_transfer.zip") -> dict:
        """
        Build file-transfer metadata.
        - Single file: transfer as-is.
        - Multiple files or directories: pack as one zip archive.
        """
        if not paths:
            raise ValueError("No files selected for transfer.")

        if len(paths) == 1 and os.path.isfile(paths[0]):
            file_path = paths[0]
            size = os.path.getsize(file_path)
            name = os.path.basename(file_path)
            return {"is_zip": False, "target_path": file_path, "name": name, "size": size}

        with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for path in paths:
                if os.path.isfile(path):
                    zipf.write(path, os.path.basename(path))
                elif os.path.isdir(path):
                    base_dir = os.path.basename(os.path.normpath(path))
                    for root, _dirs, files in os.walk(path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.join(base_dir, os.path.relpath(file_path, path))
                            zipf.write(file_path, arcname)

        size = os.path.getsize(output_zip_path)
        return {"is_zip": True, "target_path": output_zip_path, "name": "Archive.zip", "size": size}

    @staticmethod
    def extract_zip(zip_path: str, extract_dir: str):
        abs_extract_dir = os.path.realpath(extract_dir)
        with zipfile.ZipFile(zip_path, "r") as zipf:
            for member in zipf.namelist():
                member_path = os.path.realpath(os.path.join(abs_extract_dir, member))
                if not member_path.startswith(abs_extract_dir + os.sep) and member_path != abs_extract_dir:
                    raise ValueError(f"Zip Slip detected: '{member}' would extract outside target directory")
            zipf.extractall(extract_dir)
        os.remove(zip_path)

    @staticmethod
    def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
