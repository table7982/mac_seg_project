# mac_seg_project

## 1. 项目概述

### 1.1 项目背景

本项目是一套完整的百度街景数据采集与处理系统，主要解决以下业务场景：

| 场景         | 说明                                                   |
| :----------- | :----------------------------------------------------- |
| 街景数据采集 | 基于百度地图 API 获取指定坐标点的街景全景图            |
| 坐标系统转换 | 支持 WGS84、GCJ02、BD09LL、BD09MC 等多种坐标系互转     |
| 全景图投影   | 将球面全景图(Equirectangular)转换为六面体投影(Cubemap) |

### 1.2 核心功能

```plain
┌─────────────────────────────────────────────────────────────────┐
│                        系统功能架构                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │  坐标转换层  │───▶│  数据采集层  │───▶│  图像处理层   │       │
│  │ Coordinate  │    │ BaiduAPI    │    │ Panorama    │       │
│  │Transformation│   │ Control     │    │ Projection  │       │
│  └─────────────┘    └─────────────┘    └─────────────┘       │
│         │                   │                   │            │
│         ▼                   ▼                   ▼            │
│  • WGS84 ↔ GCJ02      • 街景元数据获取      • ERP转Cubemap      │
│  • GCJ02 ↔ BD09LL     • 全景图分片下载      • 双线性插值         │
│  • BD09LL ↔ BD09MC    • 历史影像回溯        • 六面体生成         │
│  • API批量转换         • 多线程并发下载       • 高保真输出         │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 技术栈

| 层级     | 技术组件            | 版本要求 |
| :------- | :------------------ | :------- |
| 语言     | Python              | 3.8+     |
| 图像处理 | Pillow (PIL), NumPy | Latest   |
| 网络请求 | requests            | Latest   |
| 并发处理 | concurrent.futures  | 标准库   |
| 坐标转换 | bd09convertor       | Latest   |

## 2. 系统架构

```plain
输入坐标(WGS84/GCJ02/BD09)
    │
    ▼
┌─────────────────┐
│ 坐标转换模块    │ ──▶ 统一转换为 BD09MC (百度墨卡托)
│ (Coordinate)    │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ API 控制模块    │ ──▶ 获取街景元数据(SID/RoadID等)
│ (BaiduAPI)      │ ──▶ 下载全景图分片(多线程)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ 图像处理模块    │ ──▶ 分片拼接为完整全景图
│ (combine_picture)│
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ 投影转换模块    │ ──▶ ERP 转 Cubemap (6面体)
│ (panorama2project)│
└─────────────────┘
    │
    ▼
输出: x_p/x_m/y_p/y_m/z_p/z_m 六个投影面
```

## 3. 模块详解

### 3.1 坐标转换模块 (`CoordinateTransformation.py`)

#### 3.1.1 模块职责

负责不同地理坐标系统之间的相互转换，支持中国特有的坐标加密体系。

#### 3.1.2 坐标系统说明

| 坐标系 | 全称                       | 使用场景          | 说明                       |
| :----- | :------------------------- | :---------------- | :------------------------- |
| WGS84  | World Geodetic System 1984 | GPS设备、国际标准 | 地球坐标系，国际通用       |
| GCJ02  | 国测局坐标系               | 高德、腾讯地图    | 加密坐标，WGS84 + 随机偏移 |
| BD09LL | 百度经纬度坐标             | 百度地图(旧)      | GCJ02 + 二次加密           |
| BD09MC | 百度墨卡托坐标             | 百度地图(新)      | 百度经纬度转墨卡托投影     |

#### 3.1.3 核心函数列表

| 函数名                              | 输入       | 输出       | 功能描述              |
| :---------------------------------- | :--------- | :--------- | :-------------------- |
| `wgs84_to_gcj02(lng, lat)`          | WGS84坐标  | GCJ02坐标  | GPS转火星坐标         |
| `gcj02_to_wgs84(lng, lat)`          | GCJ02坐标  | WGS84坐标  | 火星坐标转GPS         |
| `gcj02_to_bd09ll(lng, lat)`         | GCJ02坐标  | BD09LL坐标 | 火星转百度经纬度      |
| `bd09ll_to_gcj02(bd_lon, bd_lat)`   | BD09LL坐标 | GCJ02坐标  | 百度经纬度转火星      |
| `bd09ll_to_bd09mc(lon, lat)`        | BD09LL坐标 | BD09MC坐标 | 百度经纬度转墨卡托    |
| `bd09mc_to_bd09ll(lon, lat)`        | BD09MC坐标 | BD09LL坐标 | 百度墨卡托转经纬度    |
| `wgs84_to_bd09ll(lon, lat)`         | WGS84坐标  | BD09LL坐标 | GPS转百度经纬度(组合) |
| `wgs84_to_bd09mc(lon, lat)`         | WGS84坐标  | BD09MC坐标 | GPS转百度墨卡托(组合) |
| `api_wgs84_to_bd09mc(lon, lat, ak)` | WGS84坐标  | BD09MC坐标 | 通过百度API转换       |

#### 3.1.4 关键算法实现

**GCJ02 加密算法核心参数：**

```python
x_pi = 3.14159265358979324 * 3000.0 / 180.0  # π * 3000 / 180
pi = 3.1415926535897932384626                 # 圆周率
a = 6378245.0                                 # 长半轴(米)
ee = 0.00669342162296594323                   # 偏心率平方
```

**转换公式（GCJ02 → BD09LL）：**

```plain
z = √(lng² + lat²) + 0.00002 × sin(lat × x_pi)
θ = atan2(lat, lng) + 0.000003 × cos(lng × x_pi)

bd_lng = z × cos(θ) + 0.0065
bd_lat = z × sin(θ) + 0.006
```

#### 3.1.5 边界判定

```python
def out_of_china(lng, lat):
    """判断是否在国内，不在国内不做偏移"""
    return not (lng > 73.66 and lng < 135.05 and 
                lat > 3.86 and lat < 53.55)
```

> ⚠️ **注意**: 国外坐标直接返回原值，不进行加密偏移。

### 3.2 API 控制模块 (`Baidu_API_Control.py`)

#### 3.2.1 模块职责

封装百度地图街景 API 的调用逻辑，实现 AK 密钥池管理、多线程下载、图像拼接等功能。

#### 3.2.2 类架构

```plain
AKClass (AK密钥管理单元)
    ├── ak: str                    # 密钥字符串
    ├── error_times: int           # 连续错误次数
    ├── useful: bool               # 是否可用
    ├── response_error()           # 错误处理
    ├── response_correct()         # 正确响应处理
    └── self_check()               # 自检可用性

AKPool (AK密钥池)
    ├── AK_list: List[AKClass]     # AK实例列表
    ├── self_check()               # 批量自检
    └── choose_available_ak()      # 选择可用AK

BaiduAPI (核心API类)
    ├── ak_pool: AKPool            # AK池实例
    ├── max_connect_number: int    # 最大重试次数
    ├── web_url: str               # 街景服务地址
    ├── v1_api_url: str            # 坐标转换API
    │
    ├── get_bd09mc()               # 坐标转换(WGS84→BD09MC)
    ├── get_brief_road_message()   # 获取简要道路信息
    ├── get_road_message()         # 获取详细道路信息(含历史)
    ├── get_small_panorama()       # 获取缩略图
    ├── get_all_panorama_segment() # 多线程下载全景分片
    ├── get_big_panorama()         # 获取完整全景图
    ├── get_history_message()      # 获取历史影像元数据
    └── get_history_big_panorama() # 获取历史全景图集
```

#### 3.2.3 AK 密钥池机制

**设计目的**: 解决单 AK 并发限制、失效容错问题。

**状态流转：**

```plain
┌─────────┐    自检通过      ┌─────────┐
│  初始化  │ ─────────────▶ │  可用   │
│(useful=1)│                │(useful=1)│
└────┬────┘                └────┬────┘
     │                          │
     │    连续错误≥5次           │
     │ ◄─────────────────────────┘
     │
     ▼
┌─────────┐
│  失效   │
│(useful=0)│
└─────────┘
```

#### 3.2.4 街景数据接口详解

**1. 坐标转换接口**

| 属性 | 值                                      |
| :--- | :-------------------------------------- |
| URL  | `https://api.map.baidu.com/geoconv/v1/` |
| 方法 | GET                                     |
| 参数 | `coords`, `from`, `to`, `ak`            |
| 说明 | from=1(WGS84), to=6(BD09MC)             |

**2. 街景元数据接口 (qsdata)**

| 属性 | 值                                   |
| :--- | :----------------------------------- |
| URL  | `https://mapsv0.bdimg.com/`          |
| 参数 | `qt=qsdata`, `x`, `y`, `mode`        |
| 返回 | RoadId, RoadName, 全景ID(x), 坐标(y) |

**3. 街景历史数据接口 (sdata)**

| 属性 | 值                                    |
| :--- | :------------------------------------ |
| URL  | `https://mapsv0.bdimg.com/`           |
| 参数 | `qt=sdata`, `pc=1`, `sid`             |
| 返回 | Date, DeviceHeight, Heading, TimeLine |

**4. 全景图分片接口 (pdata)**

| 属性 | 值                                       |
| :--- | :--------------------------------------- |
| URL  | `https://mapsv0.bdimg.com/`              |
| 参数 | `qt=pdata`, `sid`, `pos`, `z`, `quality` |
| 返回 | JPEG 图像二进制数据                      |

#### 3.2.5 全景图分片规则

**Zoom 等级与分片数量关系：**

| Zoom | 水平分片数 | 垂直分片数 | 总分片数 | 输出尺寸    |
| :--- | :--------- | :--------- | :------- | :---------- |
| 1    | 2¹ = 2     | 2⁰ = 1     | 2        | 1024 × 512  |
| 2    | 2² = 4     | 2¹ = 2     | 8        | 2048 × 1024 |
| 3    | 2³ = 8     | 2² = 4     | 32       | 4096 × 2048 |
| 4    | 2⁴ = 16    | 2³ = 8     | 128      | 8192 × 4096 |

**分片命名规则**: `{row}_{col}`

- row: 0 到 2^(zoom-2)-1 (垂直方向)
- col: 0 到 2^(zoom-1)-1 (水平方向)

**示例 (zoom=3):**

```plain
pos_list = [
    "0_0", "0_1", "0_2", "0_3", "0_4", "0_5", "0_6", "0_7",
    "1_0", "1_1", "1_2", "1_3", "1_4", "1_5", "1_6", "1_7",
    "2_0", "2_1", "2_2", "2_3", "2_4", "2_5", "2_6", "2_7",
    "3_0", "3_1", "3_2", "3_3", "3_4", "3_5", "3_6", "3_7"
]
```

#### 3.2.6 多线程下载实现

```python
def get_all_panorama_segment(self, sid, zoom=3):
    pos_list = [...]  # 生成分片坐标
    panorama_picture_list = []
    
    def download_piece(pos):
        # 单个分片下载逻辑
        params = {...}
        response = requests.get(..., timeout=5)
        return {"pos": pos, "z": zoom, "picture_file": response.content}
    
    # 使用 ThreadPoolExecutor 并发下载
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_piece, pos): pos 
                  for pos in pos_list}
        for future in as_completed(futures):
            result = future.result()
            if result:
                panorama_picture_list.append(result)
```

**并发参数建议：**

| 场景         | max_workers | 说明             |
| :----------- | :---------- | :--------------- |
| 低带宽环境   | 4-5         | 避免网络拥塞     |
| 标准环境     | 8           | 平衡速度与稳定性 |
| 高带宽服务器 | 10-16       | 充分利用带宽     |

#### 3.2.7 图像拼接算法 (`combine_picture`)

**拼接流程：**

```plain
Step 1: 构建位置矩阵
    pos_matrix = [
        ["0_0", "0_1", "0_2", "0_3"],  # 第0行
        ["1_0", "1_1", "1_2", "1_3"],  # 第1行
        ...
    ]

Step 2: 横向拼接每一行
    new_image = Image.new('RGB', (512 * n_cols, 512))
    for img in row_images:
        new_image.paste(img, (x_offset, 0))
        x_offset += img.width

Step 3: 纵向拼接所有行
    final_image = Image.new('RGB', (width, 512 * n_rows))
    for img in row_combined_images:
        final_image.paste(img, (0, y_offset))
        y_offset += img.height
```

------

### 3.3 投影转换模块 (`panorama_project.py`)

#### 3.3.1 模块职责

实现等距圆柱投影(Equirectangular Projection, ERP)到立方体贴图(Cube Map)的转换。

#### 3.3.2 投影原理

**ERP 格式特点：**

- 图像宽高比 2:1
- 水平方向：360°经度 → [0, W]
- 垂直方向：180°纬度 → [0, H]
- 中心线：赤道 (纬度0°)

**Cube Map 格式：**

- 6个正方形面，分别对应空间6个方向
- 每个面覆盖 90°×90° 视野

#### 3.3.3 六面体定义

```python
box_dict = {
    "x_p": {  # 右面 (+X)
        "center": [1, 0, 0],
        "right":  [0, 0, -1],
        "up":     [0, 1, 0]
    },
    "x_m": {  # 左面 (-X)
        "center": [-1, 0, 0],
        "right":  [0, 0, 1],
        "up":     [0, 1, 0]
    },
    "y_p": {  # 上面 (+Y)
        "center": [0, 1, 0],
        "right":  [1, 0, 0],
        "up":     [0, 0, -1]
    },
    "y_m": {  # 下面 (-Y)
        "center": [0, -1, 0],
        "right":  [1, 0, 0],
        "up":     [0, 0, 1]
    },
    "z_p": {  # 前面 (+Z)
        "center": [0, 0, 1],
        "right":  [1, 0, 0],
        "up":     [0, 1, 0]
    },
    "z_m": {  # 后面 (-Z)
        "center": [0, 0, -1],
        "right":  [-1, 0, 0],
        "up":     [0, 1, 0]
    }
}
```

#### 3.3.4 转换算法流程

```plain
┌─────────────────────────────────────────────────────────────┐
│                    ERP → Cube Map 转换流程                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 生成网格坐标                                            │
│     ├── box_surface_i: [0, 1, 2, ..., S-1]                │
│     └── box_surface_j: [0, 1, 2, ..., S-1]                │
│                                                             │
│  2. 归一化到 [-1, 1]                                        │
│     ├── a = 2*(i+0.5)/S - 1  (水平方向)                    │
│     └── b = 2*(j+0.5)/S - 1  (垂直方向)                    │
│                                                             │
│  3. 计算3D方向向量                                          │
│     surface = normalize(center + a*right - b*up)            │
│                                                             │
│  4. 3D向量转球面坐标                                        │
│     ├── lat = arcsin(y)        (纬度)                      │
│     └── lon = atan2(z, x)      (经度)                      │
│                                                             │
│  5. 球面坐标转ERP像素坐标                                   │
│     ├── u = (lon + π) / (2π) * W                          │
│     └── v = (π/2 - lat) / π * H                           │
│                                                             │
│  6. 双线性插值采样                                          │
│     └── output[i,j] = bilinear_sample(img, u, v)            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 3.3.5 双线性插值实现

```python
def bilinear_sample(img, uf, vf):
    """
    双线性插值采样
    
    参数:
        img: 源图像数组 (H, W, 3)
        uf:  浮点型u坐标 (采样位置x)
        vf:  浮点型v坐标 (采样位置y)
    
    返回:
        插值后的像素值
    """
    # 计算四个邻点
    u0, v0 = floor(uf), floor(vf)      # 左上
    u1 = (u0 + 1) % W                   # 右 (循环 wrapping)
    v1 = clip(v0 + 1, 0, H-1)          # 下 (截断 clamping)
    u0 = u0 % W
    
    # 计算权重
    du = uf - floor(uf)  # 水平小数部分
    dv = vf - floor(vf)  # 垂直小数部分
    
    # 四次采样
    Ia = img[v0, u0]  # 左上
    Ib = img[v0, u1]  # 右上
    Ic = img[v1, u0]  # 左下
    Id = img[v1, u1]  # 右下
    
    # 双线性插值
    top    = Ia*(1-du) + Ib*du
    bottom = Ic*(1-du) + Id*du
    out    = top*(1-dv) + bottom*dv
    
    return clip(out, 0, 255)
```

#### 3.3.6 输出规格

| 参数     | 说明                                     |
| :------- | :--------------------------------------- |
| 输出格式 | Dict[str, Image.Image]                   |
| 键名     | "x_p", "x_m", "y_p", "y_m", "z_p", "z_m" |
| 单面尺寸 | (H × zoom) × (H × zoom) 像素             |
| 色彩空间 | RGB (3通道)                              |
| 数据类型 | uint8                                    |

## 4. API 接口规范

### 4.1 坐标转换模块接口

#### 4.1.1 本地转换接口

| 函数               | 签名                                            | 返回值       |
| :----------------- | :---------------------------------------------- | :----------- |
| `wgs84_to_gcj02`   | `(lng: float, lat: float) -> List[float]`       | `[lng, lat]` |
| `gcj02_to_wgs84`   | `(lng: float, lat: float) -> List[float]`       | `[lng, lat]` |
| `gcj02_to_bd09ll`  | `(lng: float, lat: float) -> List[float]`       | `[lng, lat]` |
| `bd09ll_to_gcj02`  | `(bd_lon: float, bd_lat: float) -> List[float]` | `[lng, lat]` |
| `bd09ll_to_bd09mc` | `(lon: float, lat: float) -> List[float]`       | `[x, y]`     |
| `bd09mc_to_bd09ll` | `(lon: float, lat: float) -> List[float]`       | `[lng, lat]` |
| `wgs84_to_bd09ll`  | `(lon: float, lat: float) -> List[float]`       | `[lng, lat]` |
| `wgs84_to_bd09mc`  | `(lon: float, lat: float) -> List[float]`       | `[x, y]`     |

#### 4.1.2 API 转换接口

```python
def api_wgs84_to_bd09mc(lon: float, lat: float, 
                        ak: str = "YOUR_AK") -> Optional[List[float]]:
    """
    通过百度官方API进行坐标转换
    
    Args:
        lon: WGS84经度
        lat: WGS84纬度  
        ak: 百度地图开发者密钥
    
    Returns:
        [bd09mc_lon, bd09mc_lat] 或 None(失败)
    """
```

### 4.2 API 控制模块接口

#### 4.2.1 初始化

```python
# 创建AK池
ak_pool = AKPool(ak_list=["ak1", "ak2", "ak3"], max_error_times=5)

# 初始化API客户端
bd_api = BaiduAPI(ak_pool=ak_pool, max_connect_number=5)
```

#### 4.2.2 核心方法

**获取坐标转换 (WGS84 → BD09MC)**

```python
def get_bd09mc(self, lon: float, lat: float) -> Dict:
    """
    将WGS84坐标转换为百度墨卡托坐标
    
    Returns:
        {
            "code": 200,
            "status": 0,
            "bd09mc_lon": float,
            "bd09mc_lat": float
        }
        或
        {
            "code": 400,
            "message": "获取坐标错误"
        }
    """
```

**获取道路信息**

```python
def get_road_message(self, bd09mc_lon: float, bd09mc_lat: float,
                    date: Optional[str] = None) -> Dict:
    """
    获取指定坐标的街景道路信息
    
    Args:
        date: 指定历史日期，格式 "YYYYMM"，如 "202002"
              None表示获取最新影像
    
    Returns:
        {
            "code": 200,
            "RoadID": str,
            "RoadName": str,
            "panorama_sid": str,
            "panorama_x": float,
            "panorama_y": float,
            "Date": str,
            "DeviceHeight": float,
            "Heading": float,
            "TimeLine": List[Dict]
        }
    """
```

**获取全景图**

```python
def get_big_panorama(self, bd09mc_lon: float, bd09mc_lat: float,
                    zoom: int = 3, brief: bool = True) -> Dict:
    """
    获取完整全景图(已拼接)
    
    Args:
        zoom: 清晰度等级 1-4
        brief: True=简要信息, False=详细信息
    
    Returns:
        {
            "code": 200,
            "road_message": Dict,
            "panorama_picture_list": List[Dict]
        }
    """
    # 注意: 返回的是分片列表，需调用 combine_picture() 拼接
```

**获取历史全景图集**

```python
def get_history_big_panorama(self, bd09mc_lon: float, 
                            bd09mc_lat: float,
                            zoom: int = 3) -> Dict:
    """
    获取该位置所有历史时期的街景图
    
    Returns:
        {
            "code": 200,
            "message_and_picture": List[Dict]
        }
        # 每个元素包含某时间点的道路信息和全景图
    """
```

### 4.3 投影转换模块接口

```python
def panorama2project(img_file: Image.Image, 
                    zoom: float = 0.5) -> Optional[Dict[str, Image.Image]]:
    """
    将ERP格式全景图转换为6面体Cube Map投影
    
    Args:
        img_file: PIL Image对象 (RGB模式)
        zoom: 输出面相对于输入高度的比例
              0.5表示输出面高度为原图高度的0.5倍
    
    Returns:
        {
            "x_p": Image,  # 右面
            "x_m": Image,  # 左面
            "y_p": Image,  # 上面
            "y_m": Image,  # 下面
            "z_p": Image,  # 前面
            "z_m": Image   # 后面
        }
        或 None (输入非RGB)
    """
```

------

## 5. 使用指南

### 5.1 快速开始

**场景1: 获取单点最新街景**

```python
from Baidu_API_Control import AKPool, BaiduAPI, combine_picture
from CoordinateTransformation import wgs84_to_bd09mc

# 1. 初始化
ak_pool = AKPool(["your_baidu_ak"])
api = BaiduAPI(ak_pool)

# 2. 坐标转换 (以上海某点为例)
lon, lat = 121.4543133, 31.24018751
bd09mc = wgs84_to_bd09mc(lon, lat)
x, y = bd09mc[0], bd09mc[1]

# 3. 获取全景图数据
result = api.get_big_panorama(x, y, zoom=3, brief=True)

# 4. 拼接图像
if result['code'] == 200:
    final_img = combine_picture(result['panorama_picture_list'])
    final_img.save('panorama.jpg')
```

**场景2: 获取历史街景序列**

```python
# 获取该位置所有历史影像
history_result = api.get_history_big_panorama(x, y, zoom=2)

if history_result['code'] == 200:
    for item in history_result['message_and_picture']:
        # 道路信息
        road_info = item['road_message']
        print(f"时间: {road_info['Date']}, 道路: {road_info['RoadName']}")
        
        # 拼接并保存
        img = combine_picture(item['panorama_picture_list'])
        img.save(f"history_{road_info['Date']}.jpg")
```

**场景3: ERP转Cube Map**

```python
from PIL import Image
from panorama_project import panorama2project

# 加载ERP全景图
erp_img = Image.open('panorama.jpg')

# 转换为Cube Map (zoom=2表示输出2048x2048每面)
cubemap = panorama2project(erp_img, zoom=2)

# 保存六个面
for face_name, face_img in cubemap.items():
    face_img.save(f'cubemap_{face_name}.jpg')
```

### 5.2 完整工作流示例

```python
import time
from Baidu_API_Control import AKPool, BaiduAPI, combine_picture
from CoordinateTransformation import wgs84_to_bd09mc
from panorama_project import panorama2project
from PIL import Image

def full_pipeline(lon, lat, ak, output_prefix="output"):
    """
    完整处理流程: WGS84坐标 → 街景采集 → Cube Map投影
    """
    print(f"🚀 开始处理坐标: ({lon}, {lat})")
    
    # Step 1: 初始化API
    ak_pool = AKPool([ak])
    api = BaiduAPI(ak_pool)
    
    # Step 2: 坐标转换
    t0 = time.time()
    x, y = wgs84_to_bd09mc(lon, lat)
    print(f"✅ 坐标转换完成: ({x}, {y}) [{(time.time()-t0)*1000:.2f}ms]")
    
    # Step 3: 获取全景图
    t0 = time.time()
    result = api.get_big_panorama(x, y, zoom=3)
    if result['code'] != 200:
        raise Exception(f"获取全景图失败: {result}")
    print(f"✅ 全景图下载完成 [{(time.time()-t0):.2f}s]")
    
    # Step 4: 拼接图像
    panorama_img = combine_picture(result['panorama_picture_list'])
    panorama_path = f"{output_prefix}_erp.jpg"
    panorama_img.save(panorama_path)
    print(f"✅ ERP图像保存: {panorama_path}")
    
    # Step 5: 投影转换
    t0 = time.time()
    cubemap = panorama2project(panorama_img, zoom=1.0)
    print(f"✅ Cube Map生成完成 [{(time.time()-t0)*1000:.2f}ms]")
    
    # Step 6: 保存结果
    saved_files = []
    for face, img in cubemap.items():
        path = f"{output_prefix}_{face}.jpg"
        img.save(path)
        saved_files.append(path)
    
    print(f"✅ 全部完成! 输出文件: {saved_files}")
    return saved_files

# 执行
if __name__ == "__main__":
    files = full_pipeline(
        lon=121.4543133, 
        lat=31.24018751,
        ak="your_baidu_ak_here",
        output_prefix="shanghai_sample"
    )
```

## 8. 附录

### 8.1 坐标系统对照表

| 坐标系 | 经度范围    | 纬度范围    | 典型值(上海)          |
| :----- | :---------- | :---------- | :-------------------- |
| WGS84  | [-180, 180] | [-90, 90]   | 121.4543, 31.2402     |
| GCJ02  | ~WGS84+偏移 | ~WGS84+偏移 | 121.4587, 31.2431     |
| BD09LL | ~GCJ02+偏移 | ~GCJ02+偏移 | 121.4651, 31.2489     |
| BD09MC | [0, ~2.4亿] | [0, ~2.4亿] | 13524123.6, 3638521.4 |

### 8.2 街景 Zoom 等级详情

| Zoom | 用途       | 文件大小(估算) |
| :--- | :--------- | :------------- |
| 1    | 缩略图预览 | ~200KB         |
| 2    | 快速浏览   | ~1MB           |
| 3    | 标准清晰度 | ~4MB           |
| 4    | 高清晰度   | ~16MB          |

### 8.3 依赖安装

```bash
pip install pillow numpy requests bd09convertor
```

### 8.4 文件清单

| 文件名                        | 行数 | 职责                          |
| :---------------------------- | :--- | :---------------------------- |
| `Baidu_API_Control.py`        | 468  | API封装、多线程下载、图像拼接 |
| `CoordinateTransformation.py` | 169  | 坐标系统转换算法              |
| `panorama_project.py`         | 144  | ERP转Cube Map投影             |

