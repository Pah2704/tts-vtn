from typing import Optional, BinaryIO, Any, Union

_FileLike = Union[BinaryIO, bytes, str]

class AudioSegment:
    @staticmethod
    def from_file(file: _FileLike, format: Optional[str] = ...) -> "AudioSegment": ...
    def export(self, out_f: _FileLike, format: Optional[str] = ..., bitrate: Optional[str] = ..., **kwargs: Any) -> Any: ...
