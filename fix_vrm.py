"""
从 AliciaSolid.vrm 提取嵌入的 PNG 纹理为独立文件，
并生成使用外部 URI 引用纹理的新 VRM 文件。
"""
import struct
import json
import os
import shutil

VRM_PATH = "frontend/static/vrm/AliciaSolid.vrm"
VRM_OUT_PATH = "frontend/static/vrm/AliciaSolid_fixed.vrm"
TEX_DIR = "frontend/static/vrm/textures"

os.makedirs(TEX_DIR, exist_ok=True)

with open(VRM_PATH, "rb") as f:
    raw = f.read()

# Parse GLB header
magic, version, total_length = struct.unpack_from("<III", raw, 0)
assert magic == 0x46546C67, "Not a GLB file"

# Chunk 0: JSON
chunk0_len, chunk0_type = struct.unpack_from("<II", raw, 12)
assert chunk0_type == 0x4E4F534A  # JSON
json_bytes = raw[20 : 20 + chunk0_len]
json_str = json_bytes.rstrip(b"\x20").decode("utf-8")
gltf = json.loads(json_str)

# Chunk 1: BIN
bin_offset = 20 + chunk0_len
chunk1_len, chunk1_type = struct.unpack_from("<II", raw, bin_offset)
assert chunk1_type == 0x004E4942  # BIN
bin_data = raw[bin_offset + 8 : bin_offset + 8 + chunk1_len]

print(f"BIN chunk: {chunk1_len} bytes")

# Extract images
images = gltf.get("images", [])
extracted = []
for i, img in enumerate(images):
    bv_idx = img.get("bufferView")
    if bv_idx is None:
        continue
    bv = gltf["bufferViews"][bv_idx]
    offset = bv.get("byteOffset", 0)
    length = bv["byteLength"]
    mime = img.get("mimeType", "image/png")
    ext = "png" if "png" in mime else "jpg"

    filename = f"tex_{i}.{ext}"
    filepath = os.path.join(TEX_DIR, filename)

    png_data = bin_data[offset : offset + length]
    with open(filepath, "wb") as out:
        out.write(png_data)

    print(f"  Extracted Image {i}: {filename} ({length} bytes)")
    extracted.append((i, filename, bv_idx))

# Modify GLTF JSON: replace bufferView references with external URIs
for img_idx, filename, bv_idx in extracted:
    gltf["images"][img_idx] = {
        "uri": f"textures/{filename}",
        "mimeType": "image/png",
    }

# Rebuild GLB: JSON chunk + BIN chunk (keep BIN for mesh/animation data)
new_json_str = json.dumps(gltf, separators=(",", ":"))
# Pad JSON to 4-byte boundary with spaces
while len(new_json_str) % 4 != 0:
    new_json_str += " "
new_json_bytes = new_json_str.encode("utf-8")

# Build new GLB
glb_header = struct.pack("<III", 0x46546C67, 2, 0)  # placeholder length
json_chunk_header = struct.pack("<II", len(new_json_bytes), 0x4E4F534A)
bin_chunk_header = struct.pack("<II", chunk1_len, 0x004E4942)

total = (
    12  # GLB header
    + 8 + len(new_json_bytes)  # JSON chunk
    + 8 + chunk1_len  # BIN chunk
)

with open(VRM_OUT_PATH, "wb") as out:
    out.write(struct.pack("<III", 0x46546C67, 2, total))
    out.write(json_chunk_header)
    out.write(new_json_bytes)
    out.write(bin_chunk_header)
    out.write(bin_data)

new_size = os.path.getsize(VRM_OUT_PATH)
old_size = os.path.getsize(VRM_PATH)
print(f"\nDone! Old: {old_size:,} bytes -> New: {new_size:,} bytes")
print(f"Output: {VRM_OUT_PATH}")
print(f"Textures extracted to: {TEX_DIR}/")
