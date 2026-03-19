import numpy as np
from PIL import Image


def panorama2project(img_file, zoom=0.5):
    img_array = np.array(img_file)
    if img_array.shape[2] != 3:
        return None
    else:
        H, W = img_array.shape[0], img_array.shape[1]

        # --- 方案 B: 若你想要“像素中心”坐标 (i+0.5 风格)，并且仍然希望左上像素中心靠近 (0,0)：
        # 像素中心通常使用范围 0.5 .. W-0.5 (长度 W)
        xs_centers = (np.arange(W, dtype=np.float32) + 0.5).astype(np.float32)
        ys_centers = (np.arange(H, dtype=np.float32) + 0.5).astype(np.float32)

        box_dict = {
            "x_p": {
                "center": np.array([1, 0, 0]),
                "right": np.array([0, 0, -1]),
                "up": np.array([0, 1, 0])
            },
            "x_m": {
                "center": np.array([-1, 0, 0]),
                "right": np.array([0, 0, 1]),
                "up": np.array([0, 1, 0])
            },

            "y_p": {
                "center": np.array([0, 1, 0]),
                "right": np.array([1, 0, 0]),
                "up": np.array([0, 0, -1])
            },
            "y_m": {
                "center": np.array([0, -1, 0]),
                "right": np.array([1, 0, 0]),
                "up": np.array([0, 0, 1])
            },

            "z_p": {
                "center": np.array([0, 0, 1]),
                "right": np.array([1, 0, 0]),
                "up": np.array([0, 1, 0])
            },
            "z_m": {
                "center": np.array([0, 0, -1]),
                "right": np.array([-1, 0, 0]),
                "up": np.array([0, 1, 0])
            }
        }
        s_length = int(H * zoom)

        box_surface_i = np.linspace(0, s_length, s_length, dtype=np.float32)
        box_surface_j = np.linspace(0, s_length, s_length, dtype=np.float32)

        box_i, box_j = np.meshgrid(box_surface_i, box_surface_j, indexing='xy')

        box_a = (2 * (box_i + 0.5) / s_length) - 1
        box_b = (2 * (box_j + 0.5) / s_length) - 1

        def normalize_vectors(v):
            # v: (..., 3)
            norm = np.linalg.norm(v, axis=-1, keepdims=True)
            # 防止除零
            norm = np.maximum(norm, 1e-12)
            return v / norm

        def directions_to_lonlat_uv(surface_unit, W, H):
            """
            将单位向量矩阵 (S,S,3) -> 经度/纬度 -> ERP 像素坐标 u,v（浮点）
            返回 u,v 的浮点数组 shape (S,S)
            """
            x = surface_unit[..., 0]
            y = surface_unit[..., 1]
            z = surface_unit[..., 2]

            # 纬度 lat = asin(y), 经度 lon = atan2(z, x)
            lat = np.arcsin(np.clip(y, -1.0, 1.0))  # shape (S,S)
            lon = np.arctan2(z, x)  # shape (S,S)

            # 映射到像素坐标
            u = (lon + np.pi) / (2.0 * np.pi) * float(W)  # range ~ [0,W)
            v = ((np.pi / 2.0) - lat) / np.pi * float(H)  # range [0,H]

            return lon, lat, u, v

        def bilinear_sample(img, uf, vf):
            H, W = img.shape[0], img.shape[1]

            # floor 与四个邻点
            u0 = np.floor(uf).astype(np.int64)  # left
            v0 = np.floor(vf).astype(np.int64)  # top

            u1 = (u0 + 1) % W  # right (wrap)
            v1 = np.clip(v0 + 1, 0, H - 1)  # bottom (clamp)

            # 对 u 做 modulo，以防 uf<0 或 uf>=W（但 lon->u 通常在 [0,W)）
            u0 = np.mod(u0, W)
            u1 = np.mod(u1, W)

            # 辅助权重（基于小数部分）
            du = uf - np.floor(uf)  # fractional part in [0,1)
            dv = vf - np.floor(vf)
            du = du.astype(np.float32)
            dv = dv.astype(np.float32)

            # 从 img 中用向量化索引取值
            # 取四个角的像素值（S,S,3）
            Ia = img[v0, u0]  # top-left
            Ib = img[v0, u1]  # top-right
            Ic = img[v1, u0]  # bottom-left
            Id = img[v1, u1]  # bottom-right

            # 线性插值： first horizontally then vertically
            top = Ia * (1.0 - du[..., None]) + Ib * (du[..., None])
            bottom = Ic * (1.0 - du[..., None]) + Id * (du[..., None])
            out = top * (1.0 - dv[..., None]) + bottom * (dv[..., None])

            # 保证类型与范围
            out = np.clip(out, 0, 255)
            return out.astype(img.dtype)

        return_dict = {}

        for box_surface_key in box_dict.keys():

            center_vector = box_dict[box_surface_key]['center']
            up_vector = box_dict[box_surface_key]['up']
            right_vector = box_dict[box_surface_key]['right']
            box_a_exp = box_a[..., np.newaxis]  # shape (S, S, 1)
            box_b_exp = box_b[..., np.newaxis]  # shape (S, S, 1)

            surface_unit = normalize_vectors(center_vector + (-box_b_exp * up_vector) + (box_a_exp * right_vector))

            lon, lat, u, v = directions_to_lonlat_uv(surface_unit=surface_unit, W=W, H=H)
            face_rgb = bilinear_sample(img=img_array, uf=u, vf=v)
            face_img = Image.fromarray(face_rgb)
            return_dict[box_surface_key] = face_img
        return return_dict

if __name__ =="__main__":
    img_file = Image.open('../test_img/output_image.jpg')
    img_dict = panorama2project(img_file=img_file, zoom=2)
    img_dict['x_p'].save('x_p.jpg')