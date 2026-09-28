"""Read WebAssembly import names; keep the original bytes for browser validation."""
class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def byte(self):
        value = self.data[self.offset]
        self.offset += 1
        return value

    def integer(self):
        value = shift = 0
        while True:
            byte = self.byte()
            value |= (byte & 127) << shift
            if byte < 128:
                return value
            shift += 7
            if shift > 63:
                raise ValueError("Invalid LEB128")

    def string(self):
        length = self.integer()
        value = self.data[self.offset:self.offset + length].decode()
        self.offset += length
        return value

    def limits(self):
        flags = self.integer()
        self.integer()
        if flags & 1:
            self.integer()


def imports(path):
    data = path.read_bytes()
    if data[:8] != b"\0asm\x01\0\0\0":
        raise ValueError("Not a WebAssembly module")
    reader = Reader(data)
    reader.offset = 8
    result = set()
    while reader.offset < len(data):
        kind, length = reader.byte(), reader.integer()
        end = reader.offset + length
        if end > len(data):
            raise ValueError("Truncated section")
        if kind == 2:
            for _ in range(reader.integer()):
                namespace, name, entry = reader.string(), reader.string(), reader.byte()
                result.add(name)
                if entry == 0:
                    reader.integer()
                elif entry == 1:
                    reader.byte()
                    reader.limits()
                elif entry == 2:
                    reader.limits()
                elif entry == 3:
                    reader.byte()
                    reader.byte()
                elif entry == 4:
                    reader.byte()
                    reader.integer()
                else:
                    raise ValueError(f"Unknown import kind: {entry}")
        reader.offset = end
    return result
