import os
import math
from PIL import Image, ImageDraw, ImageFilter

def create_lawflow_icon(output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. 绘制带有柔和外发光的科技圆角矩形底座 (Squircle with ambient glow)
    # 尺寸与边距
    pad = 80
    rect = [pad, pad, size - pad, size - pad]
    radius = 210

    # 外层霓虹微光
    glow_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_img)
    glow_draw.rounded_rectangle([pad-15, pad-15, size-pad+15, size-pad+15], radius=radius+15, fill=(0, 180, 255, 45))
    glow_img = glow_img.filter(ImageFilter.GaussianBlur(30))
    img.alpha_composite(glow_img)

    # 底座主体深邃渐变 (Midnight Navy to Deep Sapphire)
    base_mask = Image.new("L", (size, size), 0)
    base_mask_draw = ImageDraw.Draw(base_mask)
    base_mask_draw.rounded_rectangle(rect, radius=radius, fill=255)

    base_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # 垂直对角线渐变
    for y in range(size):
        ratio = y / size
        # 渐变从极深湛蓝 (10, 18, 36) 到 科技夜空蓝 (18, 32, 64)
        r = int(10 * (1 - ratio) + 20 * ratio)
        g = int(18 * (1 - ratio) + 38 * ratio)
        b = int(36 * (1 - ratio) + 72 * ratio)
        line_draw = ImageDraw.Draw(base_layer)
        line_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))
    
    # 裁切圆角
    img.paste(base_layer, (0, 0), base_mask)

    # 2. 底座精细微边框 (1px - 2px subtle cyan-gold border)
    border_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_img)
    border_draw.rounded_rectangle(rect, radius=radius, outline=(0, 210, 255, 120), width=6)
    border_draw.rounded_rectangle([pad+4, pad+4, size-pad-4, size-pad-4], radius=radius-4, outline=(255, 215, 0, 60), width=3)
    img.alpha_composite(border_img)

    # 3. 科技流线背景底纹 (Digital Legal Waves / Circuits)
    circuit_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cd = ImageDraw.Draw(circuit_layer)
    center_x = size // 2
    center_y = size // 2

    # 动态弧形光环与同心律法之环 (Concentric Rings of Justice)
    for r_val, alpha in [(280, 35), (380, 25), (460, 15)]:
        cd.ellipse(
            [center_x - r_val, center_y - r_val + 30, center_x + r_val, center_y + r_val + 30],
            outline=(0, 230, 255, alpha),
            width=3
        )

    # 4. 核心图腾：现代几何天平与智律光芒 (Geometric Balance Scale + AI Flux)
    # 中心柱与基座
    scale_y_top = 290
    scale_y_bottom = 730
    scale_y_beam = 370
    beam_half_w = 260

    # 绘制基座台阶 (Pedestal)
    cd.line([(center_x - 140, scale_y_bottom), (center_x + 140, scale_y_bottom)], fill=(255, 215, 0, 200), width=16)
    cd.line([(center_x - 90, scale_y_bottom - 18), (center_x + 90, scale_y_bottom - 18)], fill=(255, 215, 0, 240), width=12)

    # 绘制立柱 (Central Column)
    cd.line([(center_x, scale_y_beam - 20), (center_x, scale_y_bottom - 20)], fill=(255, 225, 120, 255), width=18)
    cd.line([(center_x - 4, scale_y_beam - 20), (center_x - 4, scale_y_bottom - 20)], fill=(255, 255, 230, 200), width=4)

    # 柱顶几何菱形 (Apex Diamond)
    apex_pts = [
        (center_x, scale_y_top - 30),
        (center_x + 24, scale_y_top),
        (center_x, scale_y_top + 30),
        (center_x - 24, scale_y_top)
    ]
    cd.polygon(apex_pts, fill=(0, 245, 255, 255), outline=(255, 255, 255, 240))

    # 天平主横梁 (The Balance Beam - 带有微量科技感动态斜角)
    cd.line([(center_x - beam_half_w, scale_y_beam), (center_x + beam_half_w, scale_y_beam)], fill=(255, 215, 70, 255), width=16)
    cd.line([(center_x - beam_half_w, scale_y_beam - 3), (center_x + beam_half_w, scale_y_beam - 3)], fill=(255, 255, 220, 200), width=4)

    # 左右吊索与托盘 (Left & Right Suspended Weighing Pans)
    for side in [-1, 1]:
        hx = center_x + side * beam_half_w
        hy = scale_y_beam
        # 吊索支点球
        cd.ellipse([hx - 12, hy - 12, hx + 12, hy + 12], fill=(0, 240, 255, 255))

        # 两根悬索
        pan_center_y = hy + 160
        pan_w = 90
        cd.line([(hx, hy), (hx - pan_w, pan_center_y)], fill=(0, 210, 255, 210), width=5)
        cd.line([(hx, hy), (hx + pan_w, pan_center_y)], fill=(0, 210, 255, 210), width=5)

        # 托盘 (Curved Arc Pan)
        pan_pts = [
            (hx - pan_w - 10, pan_center_y),
            (hx - pan_w // 2, pan_center_y + 35),
            (hx + pan_w // 2, pan_center_y + 35),
            (hx + pan_w + 10, pan_center_y)
        ]
        cd.line([(hx - pan_w - 12, pan_center_y), (hx + pan_w + 12, pan_center_y)], fill=(255, 215, 70, 255), width=8)
        # 托盘半球形底
        cd.arc([hx - pan_w - 10, pan_center_y - 20, hx + pan_w + 10, pan_center_y + 50], start=0, end=180, fill=(255, 215, 70, 255), width=8)

        # 托盘盛放的数字智慧光点 (Floating AI nodes)
        glow_dot_y = pan_center_y - 15
        cd.ellipse([hx - 15, glow_dot_y - 15, hx + 15, glow_dot_y + 15], fill=(0, 255, 230, 240))
        cd.ellipse([hx - 8, glow_dot_y - 8, hx + 8, glow_dot_y + 8], fill=(255, 255, 255, 255))

    # 5. 底部铭牌光纹：LAWFLOW 字体科技印记 (Embossed Brand Element)
    # 底部点缀流动的光效
    cd.line([(center_x - 180, scale_y_bottom + 55), (center_x + 180, scale_y_bottom + 55)], fill=(0, 220, 255, 160), width=4)
    # 两侧科技点缀
    cd.ellipse([center_x - 195, scale_y_bottom + 51, center_x - 187, scale_y_bottom + 59], fill=(0, 240, 255, 255))
    cd.ellipse([center_x + 187, scale_y_bottom + 51, center_x + 195, scale_y_bottom + 59], fill=(0, 240, 255, 255))

    img.alpha_composite(circuit_layer)

    # 6. 顶部微光高光层 (Subtle Glass Reflection)
    shine_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shine_draw = ImageDraw.Draw(shine_layer)
    shine_draw.ellipse([pad + 50, pad - 20, size - pad - 50, pad + 320], fill=(255, 255, 255, 22))
    shine_layer = shine_layer.filter(ImageFilter.GaussianBlur(15))
    # 仅保留在 base_mask 内部
    img.paste(Image.alpha_composite(img, shine_layer), (0, 0), base_mask)

    # 7. 保存高分辨率 PNG 与 多尺寸 Windows ICO
    png_path = os.path.join(output_dir, "lawflow_icon.png")
    ico_path = os.path.join(output_dir, "lawflow.ico")

    # 保存 PNG (512x512)
    png_img = img.resize((512, 512), Image.Resampling.LANCZOS)
    png_img.save(png_path, "PNG")

    # 生成包含 256, 128, 64, 48, 32, 16 的专业 ICO 文件
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ico_path, format="ICO", sizes=sizes)

    print(f"[OK] 创意桌面图标生成成功:")
    print(f"  * 高清 PNG: {png_path}")
    print(f"  * Windows 图标 ICO: {ico_path}")
    return ico_path, png_path

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")
    create_lawflow_icon(out_dir)
