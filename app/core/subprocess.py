import subprocess
import asyncio

class FakeProc:
    def __init__(self, res):
        self.returncode = res.returncode
        self._res = res

    async def communicate(self):
        return self._res.stdout, self._res.stderr

async def run_async_subprocess(*cmd, stdout=None, stderr=None):
    """
    A Windows-compatible wrapper for running subprocesses asynchronously.
    It uses asyncio.to_thread to avoid NotImplementedError on Windows' SelectorEventLoop.
    """
    def _run():
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE if stdout else None,
            stderr=subprocess.PIPE if stderr else None
        )
    
    res = await asyncio.to_thread(_run)
    return FakeProc(res)
