import os
import subprocess
from typing import List


def listdir(path: str) -> List[str]:
    """
    List directory. Supports either hdfs or local path. Returns full path.
    Examples:
        - listdir("hdfs://dir") -> ["hdfs://dir/file1", "hdfs://dir/file2"]
        - listdir("/dir") -> ["/dir/file1", "/dir/file2"]
    """
    files = []
    if path.startswith("hdfs://"):
        pipe = subprocess.Popen(args=["hdfs", "dfs", "-ls", path], shell=False, stdout=subprocess.PIPE)
        for line in pipe.stdout:
            parts = line.strip().split()
            # drwxr-xr-x   - user group  4 file
            if len(parts) < 5:
                continue
            files.append(parts[-1].decode("utf8"))
        pipe.stdout.close()
        pipe.wait()
    else:
        files = [os.path.join(path, file) for file in os.listdir(path)]
    return files
