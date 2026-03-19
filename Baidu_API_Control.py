import requests
from PIL import Image
from io import BytesIO
from functools import wraps
import time

from concurrent.futures import ThreadPoolExecutor, as_completed


def timer(func):
    """打印函数运行时间的装饰器"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()  # 高精度计时
        result = func(*args, **kwargs)  # 执行原函数
        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000  # 转换为毫秒

        print(f"函数 {func.__name__} 执行时间: {execution_time:.4f} 毫秒")
        return result

    return wrapper


class AKClass:
    def __init__(self, ak):
        self.ak = ak
        self.error_times = 0
        self.useful = 1

    def response_error(self):
        self.error_times += 1

    def response_correct(self):
        self.error_times = 0
        self.useful = 1

    def self_check(self):
        response = requests.get(
            f"https://api.map.baidu.com/geoconv/v2/?coords=114.21892734521,29.575429778924&model=1&ak={self.ak}").json()
        if response['status'] == 0:
            self.response_correct()
        else:
            self.response_error()
            self.useful = 0
            print(f"{self.ak}错误。")
        return self.useful


class AKPool:
    def __init__(self, ak_list, max_error_times=5):
        self.AK_list = [AKClass(ak_item) for ak_item in ak_list]

    def self_check(self):
        for AK in self.AK_list:
            AK.self_check()

    def choose_available_ak(self):
        for AK in self.AK_list:
            if AK.useful:
                return AK
        return None


def dict_find(dict_list, key, value):
    return next((item for item in dict_list if item.get(key) == value), None)


# @timer
def combine_picture(panorama_picture_list):
    zoom = panorama_picture_list[0]['z']
    # [f"{i}_{j}" for i in range(2 ** (zoom - 2)) for j in range(2 ** (zoom - 1))]
    pos_matrix = [[f"{i}_{j}" for j in range(2 ** (zoom - 1))] for i in range(2 ** (zoom - 2))]
    new_image_list = []
    for line in pos_matrix:
        pil_images = []
        for item in line:
            panorama_dict_item = dict_find(dict_list=panorama_picture_list, key="pos", value=item)
            img_buffer = BytesIO(panorama_dict_item['picture_file'])  # 将二进制数据转换为内存文件对象
            img = Image.open(img_buffer)  # 从内存文件对象打开图片
            if img.mode != 'RGB':
                img = img.convert('RGB')
            pil_images.append(img)
        new_image = Image.new('RGB', (512 * (2 ** (zoom - 1)), 512))
        x_offset = 0
        for img in pil_images:
            new_image.paste(img, (x_offset, 0))
            x_offset += img.width
        new_image_list.append(new_image)

    # 竖向拼接
    y_offset = 0
    final_image = Image.new('RGB', (512 * (2 ** (zoom - 1)), 512 * (2 ** (zoom - 2))))
    for img in new_image_list:
        final_image.paste(img, (0, y_offset))
        y_offset += img.height

    return final_image


class BaiduAPI:
    def __init__(self, ak_pool: AKPool, max_connect_number=5):
        self.ak_pool = ak_pool
        # self.ak_pool.self_check()
        self.web_url = 'https://mapsv0.bdimg.com/'
        self.v1_api_url = 'https://api.map.baidu.com/geoconv/v1/'
        self.max_connect_number = max_connect_number

    def get_bd09mc(self, lon, lat):
        for i in range(self.max_connect_number):
            available_AK = self.ak_pool.choose_available_ak()
            params = {
                "coords": f"{lon},{lat}",
                "from": "1",
                "to": "6",
                "ak": available_AK.ak,
            }
            response = requests.get(url=self.v1_api_url, params=params).json()
            if response['status'] == 0:
                available_AK.response_correct()
                return {
                    "code": 200,
                    "status": response['status'],
                    "bd09mc_lon": response['result'][0]['x'],
                    "bd09mc_lat": response['result'][0]['y']
                }
            else:
                available_AK.response_error()
                if available_AK.error_times >= 5:
                    available_AK.useful = 0
        return {"code": 400, "message": "获取坐标错误"}

    def get_brief_road_message(self, bd09mc_lon, bd09mc_lat):
        params = {
            "qt": "qsdata",
            "x": f"{bd09mc_lon}",
            "y": f"{bd09mc_lat}",
            "mode": 'day'
        }
        try:
            response = requests.get(url=self.web_url, params=params).json()['content']
            org_return = {
                'code': 200,
                'RoadID': response['RoadId'],
                'RoadName': response['RoadName'],
                'panorama_sid': response['id'],
                'panorama_x': response['x'],
                'panorama_y': response['y'],
            }
            return org_return
        except Exception as e:
            return {"code": 400, "message": "get_road_message error"}

    def get_road_message(self, bd09mc_lon, bd09mc_lat, date=None):
        params = {
            "qt": "qsdata",
            "x": f"{bd09mc_lon}",
            "y": f"{bd09mc_lat}",
            "mode": 'day'
        }
        try:
            response = requests.get(url=self.web_url, params=params).json()['content']
        except Exception as e:
            return {"code": 400, "message": "get_road_message error"}

        history_params = {
            "qt": "sdata",
            'pc': '1',
            "sid": response['id'],
        }
        history_response = requests.get(url=self.web_url, params=history_params).json()['content'][0]
        org_return = {
            'code': 200,
            'RoadID': response['RoadId'],
            'RoadName': response['RoadName'],
            'panorama_sid': response['id'],
            'panorama_x': response['x'],
            'panorama_y': response['y'],
            'Date': history_response['Date'],
            'DeviceHeight': history_response['DeviceHeight'],
            'Heading': history_response['Heading'],
            'TimeLine': history_response['TimeLine']

            # TimeLine有的字段如下
            # "ID": "0900030012200226101439932HH",
            # "IsCurrent": 1,
            # "Time": "day",
            # "TimeDir": "",
            # "TimeLine": "202002",
            # "Year": "2020"
        }

        # 下面开始讨论如果有data的情况
        if date:
            date_response = None
            date_sid = None
            for timeline_message in history_response['TimeLine']:
                if date == timeline_message['TimeLine']:
                    date_sid = timeline_message['ID']
                    date_params = {
                        "qt": "sdata",
                        'pc': '1',
                        "sid": date_sid,
                    }
                    date_response = requests.get(self.web_url, params=date_params).json()['content'][0]

            if date_response and date_sid:
                return {
                    'code': 200,
                    'RoadID': response['RoadId'],
                    'RoadName': response['RoadName'],
                    'panorama_sid': date_sid,
                    'panorama_x': response['x'],
                    'panorama_y': response['y'],
                    'Date': date_response['Date'],
                    'DeviceHeight': date_response['DeviceHeight'],
                    'Heading': date_response['Heading'],
                    'TimeLine': date_response['TimeLine']
                }
            else:
                return org_return
        else:
            return org_return

    def get_small_panorama(self, bd09mc_lon, bd09mc_lat):
        road_message = self.get_road_message(bd09mc_lon=bd09mc_lon, bd09mc_lat=bd09mc_lat)
        params = {
            "qt": "pdata",
            "sid": road_message['panorama_sid'],
            "pos": "0_0",
            "z": '1',
            "quality": '10',
        }
        response = requests.get(url=self.web_url, params=params)
        if response.content:
            return {
                'code': 200,
                'road_message': road_message,
                'panorama_picture': response.content
            }
        else:
            return {'code': 400, 'message': "图片不存在"}

    # @timer
    def get_all_panorama_segment(self, sid, zoom=3):
        pos_list = [f"{i}_{j}" for i in range(2 ** (zoom - 2)) for j in range(2 ** (zoom - 1))]
        panorama_picture_list = []

        def download_piece(pos):
            """
            下载单个位置的图片
            """
            params = {
                "qt": "pdata",
                "sid": sid,
                "pos": pos,
                "z": str(zoom)
            }
            try:
                response = requests.get(self.web_url, params=params, timeout=5)
                if response.content:
                    return {"pos": pos, "z": zoom, "picture_file": response.content}
                else:
                    return None
            except Exception as e:
                # 如果网络错误或超时，这里返回 None
                print(f"下载失败 {pos}: {e}")
                return None

        # 使用 ThreadPoolExecutor 进行多线程下载
        # max_workers 表示线程数量，一般设置为 5~10 对网络任务比较合适
        with ThreadPoolExecutor(max_workers=8) as executor:
            # 提交所有任务
            futures = {executor.submit(download_piece, pos): pos for pos in pos_list}

            # as_completed 会在每个线程任务完成后立即返回结果，不必等待所有任务结束
            for future in as_completed(futures):
                result = future.result()
                if result:
                    panorama_picture_list.append(result)

        # 判断是否有结果
        if len(panorama_picture_list) != len(pos_list):
            return {'code': 400, 'message': "图片不存在或下载失败"}

        return {'code': 200, 'panorama_picture_list': panorama_picture_list}

    def get_big_panorama(self, bd09mc_lon, bd09mc_lat, zoom=3, brief=True):
        if brief:
            road_message = self.get_brief_road_message(bd09mc_lon=bd09mc_lon, bd09mc_lat=bd09mc_lat)
        else:
            road_message = self.get_road_message(bd09mc_lon=bd09mc_lon, bd09mc_lat=bd09mc_lat)
        try:
            response = self.get_all_panorama_segment(sid=road_message['panorama_sid'], zoom=zoom)
        except Exception as e:
            return {'code': 400, 'message': "图片不存在"}
        if response['code'] == 200:
            panorama_picture_list = response['panorama_picture_list']
            return {
                'code': 200,
                'road_message': road_message,
                'panorama_picture_list': panorama_picture_list
            }
        else:
            return {'code': 400, 'message': "图片不存在"}

    # @timer
    def get_history_message(self, bd09mc_lon, bd09mc_lat):
        history_message_list = []

        params = {
            "qt": "qsdata",
            "x": f"{bd09mc_lon}",
            "y": f"{bd09mc_lat}",
            "mode": 'day'
        }
        try:
            response = requests.get(url=self.web_url, params=params).json()['content']
        except Exception as e:
            return {"code": 400, "message": 'get_history_message error'}

        history_params = {
            "qt": "sdata",
            'pc': '1',
            "sid": response['id'],
        }
        history_response = requests.get(url=self.web_url, params=history_params).json()['content'][0]

        def get_timeline_piece(timeline_message_item):
            timeline_params = {
                "qt": "sdata",
                'pc': '1',
                "sid": timeline_message_item["ID"],
            }
            try:
                timeline_item_response = requests.get(url=self.web_url, params=timeline_params).json()['content'][0]
                item_message = {
                    'RoadID': response['RoadId'],
                    'RoadName': response['RoadName'],
                    'panorama_sid': timeline_message_item["ID"],
                    'panorama_x': response['x'],
                    'panorama_y': response['y'],
                    'Date': timeline_item_response['Date'],
                    'DeviceHeight': timeline_item_response['DeviceHeight'],
                    'Heading': timeline_item_response['Heading'],
                    'TimeLine': timeline_item_response['TimeLine']
                }
                return item_message
            except Exception as e:
                return None

        with ThreadPoolExecutor(max_workers=8) as executor:
            # 提交所有任务
            futures = {executor.submit(get_timeline_piece, timeline_message_item): timeline_message_item for timeline_message_item in history_response['TimeLine']}
            # as_completed 会在每个线程任务完成后立即返回结果，不必等待所有任务结束
            for future in as_completed(futures):
                result = future.result()
                if result:
                    history_message_list.append(result)
        if len(history_message_list) != len(history_response['TimeLine']):
            return {'code': 400, 'message': "图片不存在或下载失败"}
        return {'code': 200, 'history_message_list': history_message_list}
        # 以下为单线程写法
        # for timeline_message in history_response['TimeLine']:
        #     timeline_params = {
        #         "qt": "sdata",
        #         'pc': '1',
        #         "sid": timeline_message["ID"],
        #     }
        #     timeline_item_response = requests.get(url=self.web_url, params=timeline_params).json()['content'][0]
        #
        #     item_message = {
        #         'RoadID': response['RoadId'],
        #         'RoadName': response['RoadName'],
        #         'panorama_sid': timeline_message["ID"],
        #         'panorama_x': response['x'],
        #         'panorama_y': response['y'],
        #         'Date': timeline_item_response['Date'],
        #         'DeviceHeight': timeline_item_response['DeviceHeight'],
        #         'Heading': timeline_item_response['Heading'],
        #         'TimeLine': timeline_item_response['TimeLine']
        #     }
        #     history_message_list.append(item_message)

    # @timer
    def get_history_big_panorama(self, bd09mc_lon, bd09mc_lat, zoom=3):
        history_big_panorama = []
        history_message_response = self.get_history_message(bd09mc_lon=bd09mc_lon, bd09mc_lat=bd09mc_lat)

        def download_panorama_segment(history_message, zoom):
            response = self.get_all_panorama_segment(sid=history_message['panorama_sid'], zoom=zoom)
            if response['code'] == 200:
                return_item = {
                                'road_message': history_message,
                                'panorama_picture_list': response['panorama_picture_list']
                            }
                return return_item
            else:
                return None

        if history_message_response['code'] == 200:
            with ThreadPoolExecutor(max_workers=8) as executor:
                # 提交所有任务
                futures = {executor.submit(download_panorama_segment, history_message, zoom): history_message for
                           history_message in history_message_response['history_message_list']}
                # as_completed 会在每个线程任务完成后立即返回结果，不必等待所有任务结束
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        history_big_panorama.append(result)
            if len(history_big_panorama) != len(history_message_response['history_message_list']):
                return {'code': 400, 'message': "get_all_panorama_segment error"}
            else:
                return {
                        'code': 200,
                        'message_and_picture': history_big_panorama
                    }
        # 以下为单线程写法
        #     for history_message in history_message_response['history_message_list']:
        #         response = self.get_all_panorama_segment(sid=history_message['panorama_sid'], zoom=zoom)
        #         if response['code'] == 200:
        #             return_item = {
        #                 'road_message': history_message,
        #                 'panorama_picture_list': response['panorama_picture_list']
        #             }
        #             history_big_panorama.append(return_item)
        #         else:
        #             return {'code': 400, 'message': "get_all_panorama_segment error"}
        #     return {
        #         'code': 200,
        #         'message_and_picture': history_big_panorama
        #     }
        else:
            return {'code': 400, 'message': "get_history_message error"}


if __name__ == "__main__":
    ak = "YjGjpSlRkdieZyILv0d2vLqj4G5bgygY"
    ak_pool = AKPool([ak])

    start_time = time.time()
    bd_api = BaiduAPI(ak_pool=ak_pool)
    end_time = time.time()
    print(f"BaiduAPI时间为:{end_time - start_time}s")

    lon = 121.4543133
    lat = 31.24018751
    start_time = time.time()
    bd09mc_response = bd_api.get_bd09mc(lon=lon, lat=lat)
    end_time = time.time()
    print(f"get_bd09mc时间为:{end_time - start_time}s")

    x = bd09mc_response['bd09mc_lon']
    y = bd09mc_response['bd09mc_lat']

    start_time = time.time()
    history_response = bd_api.get_history_big_panorama(bd09mc_lon=x, bd09mc_lat=y, zoom=2)
    end_time = time.time()
    print(f"get_history_big_panorama时间为:{end_time - start_time}s")

    if history_response['code'] == 200:
        for history_item in history_response['message_and_picture']:
            history_item_picture = combine_picture(panorama_picture_list=history_item['panorama_picture_list'])
            history_item_road_message = history_item['road_message']
    else:
        print(history_response)
