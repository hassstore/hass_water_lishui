"""渲染 512x512 透明背景 PNG 品牌图标：蓝色水滴 + 白色高光。

纯标准库实现（zlib + struct）：机器上没有 Pillow，pip 又被 PEP 668 锁死。
水滴形状 = 单位圆（圆形底部）与顶部等腰三角形（从尖端到圆的切点）的
圆滑并集（smin），颜色为自上而下的蓝色渐变，左上叠加白色椭圆高光。
"""

import math
import struct
import zlib

SIZE = 512
SS = 3  # 边缘抗锯齿的超采样倍数

# ---- 水滴几何（水滴坐标系，y 轴向上）----
R = 1.0                      # 圆形底部半径
TIP = 2.0                    # 尖端 y 坐标
ANG = math.asin(R / TIP)     # 切线与竖直轴夹角（tip 对圆的切线）
SMIN_K = 0.18                # 只在尖端附近生效的圆滑并集半径
BLEND_LO, BLEND_HI = 0.9, 1.3  # smin 生效的 y 区间（尖端区域）

# ---- 颜色 ----
TOP_COLOUR = (0x4F, 0xC3, 0xF7)   # 尖端附近的浅蓝
BOT_COLOUR = (0x15, 0x65, 0xC0)   # 底部的深蓝
WHITE = (0xFF, 0xFF, 0xFF)

# ---- 高光：旋转椭圆（水滴坐标）----
HL_CX, HL_CY = -0.42, 0.18
HL_A, HL_B = 0.14, 0.42          # 半短轴 / 半长轴
HL_ROT = math.radians(-22.0)     # 长轴向左上倾斜
HL_SOFT = 0.10                   # 边缘羽化宽度
HL_STRENGTH = 0.85               # 最大白度

# ---- 画布映射 ----
SCALE = 3.9        # 形状高 3.0 → 占画布约 77%
Y_CENTRE = 0.5     # 形状竖直中心 (TIP - R) / 2


def shape_sdf(x, y):
    """水滴的有符号距离场。

    主体 = 圆 ∪ 切线楔形（精确并集，切点处 C¹ 连续、无折痕）；
    仅在尖端附近用 smin 做圆滑并集，把尖角磨成圆头。
    """
    d_circle = math.hypot(x, y) - R
    sin_a, cos_a = math.sin(ANG), math.cos(ANG)
    # 楔形：两侧切线（利用对称性合并）+ 切点连线以下的底边
    f_side = abs(x) * cos_a + (y - TIP) * sin_a
    f_base = (R * R / TIP) - y
    d_tri = max(f_side, f_base)
    d_exact = min(d_circle, d_tri)
    # 只在 y > BLEND_LO 区域混入 smin，避免在切点接缝处产生凹陷
    t = max(0.0, min(1.0, (y - BLEND_LO) / (BLEND_HI - BLEND_LO)))
    w = t * t * (3.0 - 2.0 * t)
    if w <= 0.0:
        return d_exact
    a, b = d_circle, d_tri
    h = max(0.0, min(1.0, 0.5 + 0.5 * (b - a) / SMIN_K))
    d_smin = b + (a - b) * h - SMIN_K * h * (1.0 - h)
    return d_exact + (d_smin - d_exact) * w


def highlight(x, y):
    """高光强度 0..HL_STRENGTH：旋转椭圆内的羽化区域。"""
    dx, dy = x - HL_CX, y - HL_CY
    c, s = math.cos(HL_ROT), math.sin(HL_ROT)
    lx = dx * c + dy * s
    ly = -dx * s + dy * c
    d = (math.hypot(lx / HL_A, ly / HL_B) - 1.0) * min(HL_A, HL_B)
    return HL_STRENGTH * max(0.0, min(1.0, -d / HL_SOFT))


def sample(u, v):
    """图像坐标（u、v 都在 0..1，v 向下）→ RGB 或 None（透明）。"""
    x = (u - 0.5) * SCALE
    y = (0.5 - v) * SCALE + Y_CENTRE
    if shape_sdf(x, y) > 0:
        return None
    # 竖直渐变：底部深蓝 → 顶部浅蓝
    t = max(0.0, min(1.0, (y + R) / (TIP + R)))
    r = BOT_COLOUR[0] + (TOP_COLOUR[0] - BOT_COLOUR[0]) * t
    g = BOT_COLOUR[1] + (TOP_COLOUR[1] - BOT_COLOUR[1]) * t
    b = BOT_COLOUR[2] + (TOP_COLOUR[2] - BOT_COLOUR[2]) * t
    # 白色高光
    h = highlight(x, y)
    if h > 0:
        r += (WHITE[0] - r) * h
        g += (WHITE[1] - g) * h
        b += (WHITE[2] - b) * h
    return (r, g, b)


def render():
    rows = []
    for py in range(SIZE):
        row = bytearray()
        for px in range(SIZE):
            rr = gg = bb = hit = 0
            for sy in range(SS):
                for sx in range(SS):
                    u = (px + (sx + 0.5) / SS) / SIZE
                    v = (py + (sy + 0.5) / SS) / SIZE
                    colour = sample(u, v)
                    if colour is None:
                        continue
                    hit += 1
                    rr += colour[0]
                    gg += colour[1]
                    bb += colour[2]
            if not hit:
                row += b"\x00\x00\x00\x00"
                continue
            row += bytes((round(rr / hit), round(gg / hit), round(bb / hit),
                          round(255 * hit / (SS * SS))))
        rows.append(bytes(row))
    return rows


def png(path, rows):
    raw = b"".join(b"\x00" + row for row in rows)

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        fh.write(chunk(b"IEND", b""))


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.png"
    png(out, render())
    print("wrote", out)
